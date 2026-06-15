import json
import uuid
import asyncio
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler
from core.utils.dialogue import Message
from core.providers.tts.dto.dto import ContentType
from core.handle.helloHandle import checkWakeupWords
from plugins_func.register import Action, ActionResponse
from core.handle.sendAudioHandle import send_stt_message
from core.utils.util import remove_punctuation_and_length
from core.providers.tts.dto.dto import TTSMessageDTO, SentenceType

TAG = __name__

# 不需要查 PowerMem 记忆的关键词模式列表
# 仅用于零延迟的快速预判，不替代意图识别的精准判断
# 兜底策略：宁可多查不漏查，规则应保守
_SKIP_MEMORY_PATTERNS = [
    # 设备控制指令（打开/关闭/调节）
    r'^(打开|关闭|开启|关掉|调高|调低|调大|调小|设置|切换)',
    # 时间日期查询
    r'(几点|几号|星期几|什么日期|今天日期|当前时间|现在时间)',
    # 音乐/媒体控制
    r'^(播放|暂停|停止|下一首|上一首|切歌)',
    # 退出命令
    r'^(退出|再见|拜拜|关闭系统|结束对话)',
    # 音量/亮度/温度调节
    r'^(音量|亮度|温度).*(调|大|小|高|低|上|下)',
]


def _should_skip_memory(text: str) -> bool:
    """快速预判：关键词匹配判断是否需要跳过 PowerMem 记忆查询。

    对于明显不需要记忆的场景（设备控制、时间查询、音乐播放等），
    直接跳过记忆查询，避免不必要的 PowerMem API 调用。

    Args:
        text: 用户输入的文本（已提取 content 后的纯文本）

    Returns:
        True 表示应该跳过记忆查询，False 表示不确定/需要查询
    """
    for pattern in _SKIP_MEMORY_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


async def handle_user_intent(conn: "ConnectionHandler", text):
    # 预处理输入文本，处理可能的JSON格式
    try:
        if text.strip().startswith("{") and text.strip().endswith("}"):
            parsed_data = json.loads(text)
            if isinstance(parsed_data, dict) and "content" in parsed_data:
                text = parsed_data["content"]  # 提取content用于意图分析
                conn.current_speaker = parsed_data.get("speaker")  # 保留说话人信息
    except (json.JSONDecodeError, TypeError):
        pass

    # 每轮新对话前重置 skip_memory 标记
    conn.skip_memory = False

    # 快速预判：关键词匹配（仅对 PowerMem 模式有实际意义，其他模式开销极低无需跳过）
    if _should_skip_memory(text):
        conn.skip_memory = True
        conn.logger.bind(tag=TAG).debug(f"关键词预判：跳过PowerMem记忆查询, text={text[:50]}")

    # 检查是否有明确的退出命令
    _, filtered_text = remove_punctuation_and_length(text)
    if await check_direct_exit(conn, filtered_text):
        return True

    # 检查是否是唤醒词
    if await checkWakeupWords(conn, filtered_text):
        return True

    # 意图识别服务尚未初始化完成（后台初始化竞态），跳过本次意图分析
    # 后续消息到达时初始化已完成，可正常处理
    if conn.intent is None:
        return False

    if conn.intent_type == "function_call":
        # 使用支持function calling的聊天方法,不再进行意图分析
        # 快速预判结果仍然有效
        return False
    # 使用LLM进行意图分析
    intent_result = await analyze_intent_with_llm(conn, text)
    if not intent_result:
        return False

    # 解析意图识别结果中的 need_memory 标记（仅 PowerMem 模式需要关注）
    try:
        intent_data = json.loads(intent_result)
        if "need_memory" in intent_data:
            need_memory = intent_data["need_memory"]
            if not need_memory and not conn.skip_memory:
                # 意图识别判定不需要记忆，且关键词预判也未命中，以意图识别为准
                conn.skip_memory = True
                function_name = ""
                if "function_call" in intent_data:
                    function_name = intent_data["function_call"].get("name", "")
                conn.logger.bind(tag=TAG).debug(
                    f"意图识别判定不需要记忆, intent={function_name}"
                )
            elif need_memory and conn.skip_memory:
                # 意图识别判定需要记忆，覆盖关键词预判的结果（意图识别更精准）
                conn.skip_memory = False
                conn.logger.bind(tag=TAG).debug("意图识别判定需要记忆，覆盖关键词预判结果")
    except (json.JSONDecodeError, TypeError):
        pass

    # 会话开始时生成sentence_id
    conn.sentence_id = str(uuid.uuid4().hex)
    # 处理各种意图
    return await process_intent_result(conn, intent_result, text)


async def check_direct_exit(conn: "ConnectionHandler", text):
    """检查是否有明确的退出命令"""
    _, text = remove_punctuation_and_length(text)
    cmd_exit = conn.cmd_exit
    for cmd in cmd_exit:
        if text == cmd:
            conn.logger.bind(tag=TAG).info(f"识别到明确的退出命令: {text}")
            await send_stt_message(conn, text)
            await conn.close()
            return True
    return False


async def analyze_intent_with_llm(conn: "ConnectionHandler", text):
    """使用LLM分析用户意图"""
    if not hasattr(conn, "intent") or not conn.intent:
        conn.logger.bind(tag=TAG).warning("意图识别服务未初始化")
        return None

    # 对话历史记录
    dialogue = conn.dialogue
    try:
        intent_result = await conn.intent.detect_intent(conn, dialogue.dialogue, text)
        return intent_result
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"意图识别失败: {str(e)}")

    return None


async def process_intent_result(
    conn: "ConnectionHandler", intent_result, original_text
):
    """处理意图识别结果"""
    try:
        # 尝试将结果解析为JSON
        intent_data = json.loads(intent_result)

        # 检查是否有function_call
        if "function_call" in intent_data:
            # 直接从意图识别获取了function_call
            conn.logger.bind(tag=TAG).debug(
                f"检测到function_call格式的意图结果: {intent_data['function_call']['name']}"
            )
            function_name = intent_data["function_call"]["name"]
            if function_name == "continue_chat":
                return False

            if function_name == "result_for_context":
                await send_stt_message(conn, original_text)
                conn.client_abort = False

                def process_context_result():
                    conn.dialogue.put(Message(role="user", content=original_text, memory_user_id=conn.voice_identity.get("memory_user_id")))

                    from core.utils.current_time import get_current_time_info

                    current_time, today_date, today_weekday, lunar_date = (
                        get_current_time_info()
                    )

                    # 构建带上下文的基础提示
                    context_prompt = f"""当前时间：{current_time}
                                        今天日期：{today_date} ({today_weekday})
                                        今天农历：{lunar_date}

                                        请根据以上信息回答用户的问题：{original_text}"""

                    response = conn.intent.replyResult(context_prompt, original_text)
                    speak_txt(conn, response)

                conn.executor.submit(process_context_result)
                return True

            function_args = {}
            if "arguments" in intent_data["function_call"]:
                function_args = intent_data["function_call"]["arguments"]
                if function_args is None:
                    function_args = {}
            # 确保参数是字符串格式的JSON
            if isinstance(function_args, dict):
                function_args = json.dumps(function_args)

            function_call_data = {
                "name": function_name,
                "id": str(uuid.uuid4().hex),
                "arguments": function_args,
            }

            await send_stt_message(conn, original_text)
            conn.client_abort = False

            # 使用executor执行函数调用和结果处理
            def process_function_call():
                conn.dialogue.put(Message(role="user", content=original_text, memory_user_id=conn.voice_identity.get("memory_user_id")))

                # 使用统一工具处理器处理所有工具调用
                try:
                    result = asyncio.run_coroutine_threadsafe(
                        conn.func_handler.handle_llm_function_call(
                            conn, function_call_data
                        ),
                        conn.loop,
                    ).result()
                except Exception as e:
                    conn.logger.bind(tag=TAG).error(f"工具调用失败: {e}")
                    result = ActionResponse(
                        action=Action.ERROR, result=str(e), response=str(e)
                    )

                if result:
                    if result.action == Action.RESPONSE:  # 直接回复前端
                        text = result.response
                        if text is not None:
                            speak_txt(conn, text)
                    elif result.action == Action.REQLLM:  # 调用函数后再请求llm生成回复
                        text = result.result
                        conn.dialogue.put(Message(role="tool", content=text))
                        llm_result = conn.intent.replyResult(text, original_text)
                        if llm_result is None:
                            llm_result = text
                        speak_txt(conn, llm_result)
                    elif (
                        result.action == Action.NOTFOUND
                        or result.action == Action.ERROR
                    ):
                        text = result.result
                        if text is not None:
                            speak_txt(conn, text)
                    elif function_name != "play_music":
                        # For backward compatibility with original code
                        # 获取当前最新的文本索引
                        text = result.response
                        if text is None:
                            text = result.result
                        if text is not None:
                            speak_txt(conn, text)

            # 将函数执行放在线程池中
            conn.executor.submit(process_function_call)
            return True
        return False
    except json.JSONDecodeError as e:
        conn.logger.bind(tag=TAG).error(f"处理意图结果时出错: {e}")
        return False


def speak_txt(conn: "ConnectionHandler", text):
    # 记录文本
    conn.tts_MessageText = text

    conn.tts.tts_text_queue.put(
        TTSMessageDTO(
            sentence_id=conn.sentence_id,
            sentence_type=SentenceType.FIRST,
            content_type=ContentType.ACTION,
        )
    )
    conn.tts.tts_one_sentence(conn, ContentType.TEXT, content_detail=text)
    conn.tts.tts_text_queue.put(
        TTSMessageDTO(
            sentence_id=conn.sentence_id,
            sentence_type=SentenceType.LAST,
            content_type=ContentType.ACTION,
        )
    )
    conn.dialogue.put(Message(role="assistant", content=text))
