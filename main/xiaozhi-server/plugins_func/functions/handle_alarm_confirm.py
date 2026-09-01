import asyncio
import random
import time
from typing import TYPE_CHECKING, Optional

from core.handle.alarmConfirmHandler import (
    post_alarm_response,
    DEFAULT_CONFIRM_REPLY,
    DEFAULT_CANCEL_REPLY,
    CONFIRM_STATE_TTL,
)
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

# 答非所问时的友好提示文案（核心意思：目前只能处理告警确认，其他任务无法处理）
DEFAULT_REASK_REPLIES = [
    "抱歉，目前检测到异常情况，我现在只能帮您给家人发送消息或者不发送，其他事情暂时没法处理。请问需要通知您的家人吗？",
    "不好意思，当前处于异常告警状态，我只能帮您处理通知家人这件事，暂时不能做其他事情。需要我帮您通知家人吗？",
    "我现在只能帮您确认一件事：要不要通知您的家人，其他任务暂时无法处理。请问需要通知家人吗？",
]

handle_alarm_confirm_function_desc = {
    "type": "function",
    "function": {
        "name": "handle_alarm_confirm",
        "description": (
            "【强制调用】当本对话中出现过询问用户是否需要通知家人的告警，"
            "且用户对此做出了任何回应（肯定或否定）时，你必须调用本函数，禁止直接文字回复。"
            "用户表示要/可以/好的/是/通知 → confirmed=true；"
            "用户表示不要/不用/不需要/别/取消 → confirmed=false；"
            "用户答非所问、没听清或没有正面回应 → confirmed=null。"
            "示例：用户说『不要。』→ handle_alarm_confirm(confirmed=false)；"
            "用户说『好的，快通知吧』→ handle_alarm_confirm(confirmed=true)；"
            "用户说『嗯？你说什么？』→ handle_alarm_confirm(confirmed=null)。"
            "confirmed=true 或 false 时调用本函数后会结束当前对话；"
            "confirmed=null 时本函数会提示用户当前仅能处理告警确认，并等待用户重新回答。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirmed": {
                    "type": ["boolean", "null"],
                    "description": "用户是否确认告警、需要通知家人。true表示确认需要通知；false表示用户明确表示不需要通知；null表示用户答非所问或无法判断。",
                }
            },
            "required": ["confirmed"],
        },
    },
}


def _post_alarm_response_async(
    conn: "ConnectionHandler",
    api_base_url: str,
    session_id: str,
    confirmed: bool,
    text: str,
    action_label: str,
) -> None:
    """异步提交 post_alarm_response 到事件循环，不阻塞当前线程，结果通过回调记录日志。"""
    future = asyncio.run_coroutine_threadsafe(
        post_alarm_response(api_base_url, session_id, confirmed, text),
        conn.loop,
    )

    def _done(fut):
        try:
            result = fut.result()
            logger.bind(tag=TAG).info(
                f"{action_label}回调成功: session={session_id}, result={result}"
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"{action_label}回调失败: {e}")

    future.add_done_callback(_done)


def _normalize_confirmed(confirmed) -> Optional[bool]:
    """归一化 LLM 传出的布尔值或 null，返回 True / False / None（None=无法判断）。"""
    if confirmed is None:
        return None
    if isinstance(confirmed, str):
        stripped = confirmed.strip().lower()
        if stripped in ("", "null", "none", "unknown", "unclear", "不确定", "无法判断", "没听清", "答非所问"):
            return None
        return stripped in (
            "true",
            "yes",
            "1",
            "是",
            "要",
            "对",
            "好",
            "确认",
            "通知",
        )
    if isinstance(confirmed, (int, float)):
        return confirmed != 0
    return bool(confirmed)


@register_function(
    "handle_alarm_confirm", handle_alarm_confirm_function_desc, ToolType.SYSTEM_CTL
)
def handle_alarm_confirm(conn: "ConnectionHandler", confirmed: Optional[bool] = None):
    """处理告警确认：确认则通知后端；明确否定则取消退出；答非所问则友好提示并保持等待。"""
    try:
        # 归一化 LLM 可能传出的非标准布尔值（如字符串 "false"）或 null
        confirmed = _normalize_confirmed(confirmed)
        pending = getattr(conn, "pending_alarm_confirm", None)
        pending_active = (
            pending
            and pending.get("waiting_confirm")
            and time.time() <= pending.get("expire_at", 0)
        )

        if confirmed is True and pending_active:
            # 用户确认告警，调用接口通知后端（原逻辑不变）
            session_id = pending["session_id"]
            api_base_url = pending["api_base_url"]
            reply = pending.get("confirm_reply", DEFAULT_CONFIRM_REPLY)
            logger.bind(tag=TAG).info(
                f"告警确认: session={session_id}, 调用post_alarm_response"
            )
            # 异步提交，不阻塞当前线程
            _post_alarm_response_async(
                conn, api_base_url, session_id, True, "用户确认告警", "告警确认"
            )

        elif confirmed is None and pending_active:
            # 用户答非所问：保持等待，交由大模型结合上下文生成友好追问
            pending["expire_at"] = time.time() + CONFIRM_STATE_TTL

            # 防循环：连续多次答非所问时降级为固定文案，避免 REQLLM 反复触发
            reask_count = pending.get("reask_count", 0) + 1
            pending["reask_count"] = reask_count
            if reask_count > 2:
                reply = random.choice(DEFAULT_REASK_REPLIES)
                logger.bind(tag=TAG).info("用户连续答非所问，降级为固定文案")
                return ActionResponse(
                    action=Action.RESPONSE,
                    result="用户答非所问，已提示当前仅能处理告警确认",
                    response=reply,
                )

            logger.bind(tag=TAG).info("用户答非所问，交由大模型生成追问文案")
            return ActionResponse(
                action=Action.REQLLM,
                result=(
                    "【系统状态】设备处于异常告警状态，系统正在等待用户确认是否通知家人。"
                    "用户刚才的回答没有正面回应。"
                    "请用一句话，以亲切、自然、简洁的口吻，向用户说明：当前只能帮用户处理『是否通知家人』这一件事，"
                    "其他任务暂时无法处理，并追问用户是否需要通知家人。"
                    "你可以稍微呼应一下用户刚才说的话，但不要跑题，不要聊其他话题。"
                    "请直接输出最终回复文本，禁止再次调用任何工具。"
                ),
                response=None,
            )

        elif confirmed is False and pending_active:
            # 用户明确否定：回调后端通知用户拒绝，再退出
            session_id = pending["session_id"]
            api_base_url = pending["api_base_url"]
            reply = pending.get("cancel_reply", DEFAULT_CANCEL_REPLY)
            logger.bind(tag=TAG).info(
                f"告警拒绝: session={session_id}, 调用post_alarm_response"
            )
            # 异步提交，不阻塞当前线程
            _post_alarm_response_async(
                conn, api_base_url, session_id, False, "用户拒绝告警", "告警拒绝"
            )

        else:
            # 没有待确认的告警，直接退出
            reply = DEFAULT_CANCEL_REPLY
            logger.bind(tag=TAG).info("无待确认的告警，直接退出对话")

        # 清理告警状态
        conn.pending_alarm_confirm = None
        # 设置退出标志
        conn.close_after_chat = True

        logger.bind(tag=TAG).info(f"告警确认流程结束，退出对话: {reply}")
        return ActionResponse(
            action=Action.RESPONSE, result="告警确认流程已完成", response=reply
        )

    except Exception as e:
        logger.bind(tag=TAG).error(f"处理告警确认错误: {e}")
        # 即使出错也确保退出
        conn.close_after_chat = True
        conn.pending_alarm_confirm = None
        return ActionResponse(
            action=Action.RESPONSE,
            result="告警确认处理异常",
            response="好的，我知道了。",
        )
