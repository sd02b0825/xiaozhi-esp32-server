"""
异常声音告警确认：解析询问前缀、匹配用户肯定/否定、回调 PaddleSpeech-api。
"""
import json
import re
import time
import asyncio
from typing import Any, Dict, Optional, TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

from core.utils.util import remove_punctuation_and_length
from core.utils.dialogue import Message
from core.handle.reportHandle import enqueue_asr_report
from core.handle.abortHandle import handleAbortMessage

TAG = __name__

# [ALARM_CONFIRM:session_id|api_base_url]询问正文
ALARM_CONFIRM_PATTERN = re.compile(
    r"^\[ALARM_CONFIRM:([^|\]]+)\|([^\]]+)\](.*)$",
    re.DOTALL,
)

# 否定词优先匹配；长词在前避免「不用」被拆散
NEGATIVE_KEYWORDS = [
    "不需要", "不用", "不要", "别通知", "别联系", "取消", "算了", "不是", "否", "没事",
]
# 肯定词：覆盖「通知」「联系家人」等自然回应（询问语为「需要我帮您通知一下家人吗？」）
AFFIRMATIVE_KEYWORDS = [
    "通知", "联系", "告诉", "说一声", "带个话", "帮忙", "赶紧", "快点",
    "好的", "确认", "可以", "发送", "是的", "对", "行", "嗯",
]
# 短词放最后，且要求整句匹配，避免误触
AFFIRMATIVE_SHORT_EXACT = ["是", "要"]

DEFAULT_CONFIRM_REPLY = "好的，我已经帮您通知家人了。"
DEFAULT_CANCEL_REPLY = "好的，那我就不打扰了，您有需要随时叫我。"
CONFIRM_STATE_TTL = 60


def parse_alarm_confirm_text(text: str) -> Optional[Dict[str, str]]:
    match = ALARM_CONFIRM_PATTERN.match(text or "")
    if not match:
        return None
    return {
        "session_id": match.group(1),
        "api_base_url": match.group(2).rstrip("/"),
        "inquiry_text": match.group(3).strip(),
    }


def _extract_plain_text(text: str) -> str:
    try:
        stripped = (text or "").strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            data = json.loads(stripped)
            content = data.get("content")
            if content:
                return str(content).strip()
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return (text or "").strip()


def _normalize_confirm_text(text: str) -> str:
    """提取纯文本并去除标点，便于关键词匹配。"""
    plain = _extract_plain_text(text)
    if not plain:
        return ""
    _, normalized = remove_punctuation_and_length(plain)
    return normalized or plain.strip()


def classify_user_confirm(text: str) -> Optional[bool]:
    """否定优先；无法判断返回 None。"""
    normalized = _normalize_confirm_text(text)
    if not normalized:
        return None
    # 「是不是」等模糊表述不当作确认
    if "是不是" in normalized:
        return None
    for kw in NEGATIVE_KEYWORDS:
        if kw in normalized:
            return False
    for kw in AFFIRMATIVE_KEYWORDS:
        if kw in normalized:
            return True
    # 短肯定词仅整句匹配（如「是」「要」），避免子串误触
    if normalized in AFFIRMATIVE_SHORT_EXACT:
        return True
    return None


async def post_alarm_response(
    api_base_url: str,
    session_id: str,
    confirmed: bool,
    text: str = "",
) -> Dict[str, Any]:
    url = f"{api_base_url.rstrip('/')}/alarm/response"
    payload = {
        "session_id": session_id,
        "confirmed": confirmed,
        "text": text,
    }
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            return await resp.json()


async def speak_fixed_text(conn: "ConnectionHandler", text: str) -> None:
    """直接 TTS 播报固定文案，不走 LLM。"""
    await conn.asr._speak_fixed_text(conn, text)


async def handle_alarm_inquiry_detect(conn: "ConnectionHandler", raw_text: str) -> bool:
    """处理 listen/detect 中的告警询问命令。"""
   
    parsed = parse_alarm_confirm_text(raw_text)
    if not parsed:
        return False

    inquiry_text = parsed["inquiry_text"]
    if not inquiry_text:
        return False
    
     

    conn.pending_alarm_confirm = {
        "session_id": parsed["session_id"],
        "api_base_url": parsed["api_base_url"],
        "waiting_confirm": True,
        "expire_at": time.time() + CONFIRM_STATE_TTL,
        "confirm_reply": DEFAULT_CONFIRM_REPLY,
        "cancel_reply": DEFAULT_CANCEL_REPLY,
    }

    conn.logger.bind(tag=TAG).info(
        f"进入告警确认等待: session={parsed['session_id']}"
    )

    # 等待 ASR 初始化完成
    for _ in range(50):  # 最多等 5 秒
        if conn.asr is not None:
            break
        await asyncio.sleep(0.1)

    if conn.asr is None:
        conn.logger.bind(tag=TAG).error("等待 ASR 初始化超时，跳过告警播报")
        conn.pending_alarm_confirm = None
        return True

    # ===== 告警抢占：中止 LLM 对话播报，避免与询问语冲突 =====
    # 1. 先置持久标志，让 chat 线程在 LLM 响应返回后自查退出，不再写入 TTS
    conn.abort_llm_playback = True
    # 2. 再打断并清空队列：置 client_abort、清 TTS/音频/报告队列、通知设备端停止播放
    await handleAbortMessage(conn)
    # 3. 重申持久标志（handleAbortMessage 只动 client_abort，不会清掉本标志，此处重申以防竞态）
    conn.abort_llm_playback = True
    conn.logger.bind(tag=TAG).info("告警抢占：已中止 LLM 对话播报，开始播报询问语")

    await speak_fixed_text(conn, inquiry_text)
    conn.dialogue.put(Message(role="assistant", content=inquiry_text))
    enqueue_asr_report(conn, inquiry_text, [])
    return True


async def try_handle_alarm_confirm_response(
    conn: "ConnectionHandler", user_text: str
) -> bool:
    """ASR 完成后尝试处理用户的肯定/否定回应。"""
    pending = getattr(conn, "pending_alarm_confirm", None)
    if not pending or not pending.get("waiting_confirm"):
        return False

    if time.time() > pending.get("expire_at", 0):
        conn.pending_alarm_confirm = None
        return False

    confirmed = classify_user_confirm(user_text)
    if confirmed is None:
        plain = _normalize_confirm_text(user_text)
        conn.logger.bind(tag=TAG).info(
            f"告警确认未匹配关键词，走正常对话: text={plain!r}, session={pending.get('session_id')}"
        )
        return False

    session_id = pending["session_id"]
    api_base_url = pending["api_base_url"]
    plain_text = _normalize_confirm_text(user_text)

    try:
        result = await post_alarm_response(
            api_base_url, session_id, confirmed, plain_text
        )
        conn.logger.bind(tag=TAG).info(
            f"告警确认回调: session={session_id}, confirmed={confirmed}, result={result}"
        )
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"告警确认回调失败: {e}")

    conn.pending_alarm_confirm = None

    reply = (
        pending.get("confirm_reply", DEFAULT_CONFIRM_REPLY)
        if confirmed
        else pending.get("cancel_reply", DEFAULT_CANCEL_REPLY)
    )
    await speak_fixed_text(conn, reply)
    return True
