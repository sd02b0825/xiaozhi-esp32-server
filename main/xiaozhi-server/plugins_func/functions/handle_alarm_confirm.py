import asyncio
from core.handle.alarmConfirmHandler import (
    post_alarm_response,
    DEFAULT_CONFIRM_REPLY,
    DEFAULT_CANCEL_REPLY,
)
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from typing import TYPE_CHECKING
from core.handle.sendAudioHandle import send_stt_message

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()

handle_alarm_confirm_function_desc = {
    "type": "function",
    "function": {
        "name": "handle_alarm_confirm",
        "description": (
            "联系前文，如果有询问用户是否确认告警或通知家人时，调用此函数。"
            "如果用户确认需要通知家人，confirmed设为true，系统会调用接口通知后端。"
            "如果用户表示不需要通知，confirmed设为false，直接退出对话。"
            "如果用户既不确认也不否认，confirmed设为false。"
            "调用此函数后会结束当前对话。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirmed": {
                    "type": "boolean",
                    "description": "用户是否确认告警、需要通知家人。true表示确认告警需要通知，false表示不需要通知。",
                }
            },
            "required": ["confirmed"],
        },
    },
}


@register_function(
    "handle_alarm_confirm", handle_alarm_confirm_function_desc, ToolType.SYSTEM_CTL
)
def handle_alarm_confirm(conn: "ConnectionHandler", confirmed: bool):
    """处理告警确认：用户确认告警则调用接口通知后端，否则直接退出对话。"""
    try:
        pending = getattr(conn, "pending_alarm_confirm", None)

        if confirmed and pending and pending.get("waiting_confirm"):
            # 用户确认告警，调用接口通知后端
            session_id = pending["session_id"]
            api_base_url = pending["api_base_url"]
            reply = pending.get("confirm_reply", DEFAULT_CONFIRM_REPLY)

            logger.bind(tag=TAG).info(
                f"告警确认: session={session_id}, 调用post_alarm_response"
            )

            # 使用 asyncio.run_coroutine_threadsafe 桥接异步调用
            future = asyncio.run_coroutine_threadsafe(
                post_alarm_response(
                    api_base_url, session_id, True, "用户确认告警"
                ),
                conn.loop,
            )
            try:
                result = future.result(timeout=5)
                logger.bind(tag=TAG).info(
                    f"告警确认回调成功: session={session_id}, result={result}"
                )
            except Exception as e:
                logger.bind(tag=TAG).error(f"告警确认回调失败: {e}")
        else:
            # 用户不确认或没有待确认的告警，直接退出
            reply = DEFAULT_CANCEL_REPLY
            logger.bind(tag=TAG).info("告警取消或无需处理，直接退出对话")


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
