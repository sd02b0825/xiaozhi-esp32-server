import os
import io
import wave
import uuid
import json
import time
import queue
import shutil
import asyncio
import tempfile
import traceback
import threading
import opuslib_next

from abc import ABC, abstractmethod
from config.logger import setup_logging
from core.providers.asr.dto.dto import InterfaceType
from core.handle.receiveAudioHandle import startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.utils.util import remove_punctuation_and_length
from core.handle.receiveAudioHandle import handleAudioMessage
from core.providers.tts.dto.dto import ContentType, TTSMessageDTO, SentenceType
from typing import Optional, Tuple, List, NamedTuple, TYPE_CHECKING
from core.handle.sendAudioHandle import send_tts_message

if TYPE_CHECKING:
    from core.connection import ConnectionHandler

TAG = __name__
logger = setup_logging()


class ASRProviderBase(ABC):
    def __init__(self):
        pass

    # 打开音频通道
    async def open_audio_channels(self, conn: "ConnectionHandler"):
        conn.asr_priority_thread = threading.Thread(
            target=self.asr_text_priority_thread, args=(conn,), daemon=True
        )
        conn.asr_priority_thread.start()

    # 有序处理ASR音频
    def asr_text_priority_thread(self, conn: "ConnectionHandler"):
        while not conn.stop_event.is_set():
            try:
                message = conn.asr_audio_queue.get(timeout=1)
                future = asyncio.run_coroutine_threadsafe(
                    handleAudioMessage(conn, message),
                    conn.loop,
                )
                future.result()
            except queue.Empty:
                continue
            except Exception as e:
                logger.bind(tag=TAG).error(
                    f"处理ASR文本失败: {str(e)}, 类型: {type(e).__name__}, 堆栈: {traceback.format_exc()}"
                )
                continue

    # 接收音频
    async def receive_audio(self, conn: "ConnectionHandler", audio, audio_have_voice):
        if conn.client_listen_mode == "manual":
            # 手动模式：缓存音频用于ASR识别
            conn.asr_audio.append(audio)
        else:
            # 自动/实时模式：使用VAD检测
            conn.asr_audio.append(audio)

            # 如果没有语音，且之前也没有声音，缓存部分音频
            if not audio_have_voice and not conn.client_have_voice:
                conn.asr_audio = conn.asr_audio[-10:]
                return

            # 自动模式下通过VAD检测到语音停止时触发识别
            if conn.asr.interface_type != InterfaceType.STREAM and conn.client_voice_stop:
                asr_audio_task = conn.asr_audio.copy()
                conn.reset_audio_states()

                if len(asr_audio_task) > 15:
                    # 发送有说话声结束消息
                    await conn.websocket.send(json.dumps({
                        "session_id": conn.session_id,
                        "type": "voiceprint",
                        "action": "end"
                    }))
                    await self.handle_voice_stop(conn, asr_audio_task)
                else:
                    # 发送失败消息，重置声纹标记
                    await conn.websocket.send(json.dumps({
                        "session_id": conn.session_id,
                        "type": "voiceprint",
                        "action": "fail"
                    }))

    # 处理语音停止
    async def handle_voice_stop(self, conn: "ConnectionHandler", asr_audio_task: List[bytes]):
        """并行处理ASR和声纹识别"""
        try:
            total_start_time = time.monotonic()

            # 准备音频数据
            if conn.audio_format == "pcm":
                pcm_data = asr_audio_task
            else:
                pcm_data = self.decode_opus(asr_audio_task)

            combined_pcm_data = b"".join(pcm_data)

            # 预先准备WAV数据
            wav_data = None
            if conn.voiceprint_provider and combined_pcm_data:
                wav_data = self._pcm_to_wav(combined_pcm_data)

            # 定义ASR任务
            asr_task = self.speech_to_text_wrapper(
                asr_audio_task, conn.session_id, conn.audio_format
            )

            if conn.voiceprint_provider and wav_data:
                voiceprint_task = conn.voiceprint_provider.identify_speaker(
                    wav_data, conn.session_id
                )
                # 并发等待两个结果
                asr_result, voiceprint_result = await asyncio.gather(
                    asr_task, voiceprint_task, return_exceptions=True
                )
            else:
                asr_result = await asr_task
                voiceprint_result = None

            # 记录识别结果 - 检查是否为异常
            if isinstance(asr_result, Exception):
                logger.bind(tag=TAG).error(f"ASR识别失败: {asr_result}")
                raw_text = ""
            else:
                raw_text, _ = asr_result

            if isinstance(voiceprint_result, Exception):
                logger.bind(tag=TAG).error(f"声纹识别失败: {voiceprint_result}")
                voiceprint_result = None

            # 提取用户原话，先交给连接级声纹状态机处理
            if isinstance(raw_text, dict):
                if raw_text.get("language"):
                    logger.bind(tag=TAG).info(f"识别语言: {raw_text['language']}")
                if raw_text.get("emotion"):
                    logger.bind(tag=TAG).info(f"识别情绪: {raw_text['emotion']}")
                if raw_text.get("content"):
                    logger.bind(tag=TAG).info(f"识别文本: {raw_text['content']}")
                user_text = raw_text.get("content", "")
            else:
                if raw_text:
                    logger.bind(tag=TAG).info(f"识别文本: {raw_text}")
                user_text = raw_text
           
            if not await self._handle_voice_identity(conn, voiceprint_result, user_text):
                return

            speaker_name = conn.current_speaker

            # 判断 ASR 结果类型
            if isinstance(raw_text, dict):
                # FunASR 返回的 dict 格式
                if speaker_name:
                    raw_text["speaker"] = speaker_name
                    logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")

                # 转换为 JSON 字符串用于下游
                enhanced_text = json.dumps(raw_text, ensure_ascii=False)
                content_for_length_check = raw_text.get("content", "")
            else:
                # 其他 ASR 返回的纯文本
                if speaker_name:
                    logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")

                # 构建包含说话人信息的JSON字符串
                enhanced_text = self._build_enhanced_text(raw_text, speaker_name)
                content_for_length_check = raw_text

            # 性能监控
            total_time = time.monotonic() - total_start_time
            logger.bind(tag=TAG).debug(f"总处理耗时: {total_time:.3f}s")

            # 检查文本长度
            text_len, _ = remove_punctuation_and_length(content_for_length_check)
            self.stop_ws_connection()

            

            if text_len > 0:
                # 灵芯声纹模式，不调用大模型
                if conn.lingxin_sdk:
                    try:
                        # 发送声纹识别开始消息
                        await conn.websocket.send(json.dumps({
                            "session_id": conn.session_id,
                            "type": "voiceprint",
                            "action": "success",
                            "speaker": speaker_name or ""
                        }))
                        await send_tts_message(conn, "start")
                        conn.client_is_speaking = True
                        logger.bind(tag=TAG).info(f"灵芯声纹识别结束: speaker={speaker_name or ''}")
                        
                    except Exception as e:
                        logger.bind(tag=TAG).error(f"发送声纹识别结束消息失败: {e}")
                    finally:
                        return

                # 处理确认
                from core.handle.alarmConfirmHandler import (
                    try_handle_alarm_confirm_response,
                )
                if await try_handle_alarm_confirm_response(conn, enhanced_text):
                    audio_snapshot = asr_audio_task.copy()
                    enqueue_asr_report(conn, enhanced_text, audio_snapshot)
                    return

                # 使用自定义模块进行上报
                await startToChat(conn, enhanced_text)
                audio_snapshot = asr_audio_task.copy()
                enqueue_asr_report(conn, enhanced_text, audio_snapshot)
            else:
                # 发送声纹识别失败
                await conn.websocket.send(json.dumps({
                    "session_id": conn.session_id,
                    "type": "voiceprint",
                    "action": "fail",
                }))

        except Exception as e:
            logger.bind(tag=TAG).error(f"处理语音停止失败: {e}")
            import traceback

            logger.bind(tag=TAG).debug(f"异常详情: {traceback.format_exc()}")
    
    async def _handle_voice_identity(self, conn: "ConnectionHandler", voiceprint_result, user_text: str) -> bool:
        """维护连接级说话人身份状态。"""
        try:
            identity = getattr(conn, "voice_identity", None)
            if identity is None:
                return True

            if conn.is_voice_identity_expired():
                logger.bind(tag=TAG).info("说话人身份已过期，清空当前身份")
                await self._flush_last_speaker_memory(conn)
                conn.clear_voice_identity()
                identity = conn.voice_identity

            status = getattr(voiceprint_result, "status", None)
            if status == "RECOGNIZED":
                speaker_name = getattr(voiceprint_result, "speaker", "")
                score = getattr(voiceprint_result, "score", 0.0)
                speaker_profile_id = getattr(voiceprint_result, "speaker_profile_id", "")
                voiceprint_id = getattr(voiceprint_result, "speaker_id", "")
                if speaker_name and speaker_profile_id:
                    # 检测说话人切换：按姓名比对（同人多声纹共享记忆，不因 profile_id 变化而 flush）
                    old_speaker = identity.get("current_speaker")
                    if old_speaker and old_speaker != speaker_name and conn.memory is not None:
                        old_muid = identity.get("memory_user_id")
                        if old_muid:
                            asyncio.create_task(self._flush_dialogue_memory(conn, old_muid))
                        # 说话人切换后，新说话人的首次对话跳过记忆查询
                        # 刚切换过来没有相关记忆需要检索，跳过可节省2-5秒
                        conn.skip_memory = True
                        logger.bind(tag=TAG).info(
                            f"说话人切换({old_speaker}→{speaker_name})，跳过首次记忆查询"
                        )

                    conn.set_voice_identity(
                        speaker_name, "VOICEPRINT", confidence=score, ttl_seconds=600,
                        speaker_profile_id=speaker_profile_id,
                        voiceprint_id=voiceprint_id or speaker_profile_id,
                    )
                    logger.bind(tag=TAG).info(f"声纹身份更新: {speaker_name}, 分数: {score:.3f}, profile_id: {speaker_profile_id}")
                elif speaker_name and not speaker_profile_id:
                    # 特殊情况：有名字但无声纹ID（兼容旧格式）
                    conn.set_voice_identity(speaker_name, "VOICEPRINT", confidence=score, ttl_seconds=600)
                return True

            if identity.get("waiting_name_confirm"):
                name = self._parse_name_from_confirm_reply(user_text)

                if not name:
                    await self._speak_fixed_text(conn, "我没听清，请问您怎么称呼？")
                    return False

                conn.set_voice_identity(name, "MANUAL_CONFIRM", confidence=0.5, ttl_seconds=300)
                logger.bind(tag=TAG).info(f"用户手动确认说话人: {name}")
                await self._speak_fixed_text(conn, f"好的，后续我会默认您是{name}。")
                return False

            if status is None:
                return True

            if status == "SERVICE_ERROR":
                logger.bind(tag=TAG).warning(f"声纹服务异常，不更新身份: {getattr(voiceprint_result, 'reason', '')}")
                return True

            if identity.get("manual_confirmed") and identity.get("current_speaker"):
                logger.bind(tag=TAG).debug(f"声纹未命中，沿用手动确认身份: {identity.get('current_speaker')}")
                return True

            identity["fail_count"] = identity.get("fail_count", 0) + 1
            logger.bind(tag=TAG).info(f"连续声纹识别失败计数: {identity['fail_count']}")

            if identity["fail_count"] >= 3:
                identity["fail_count"] = 0
                identity["waiting_name_confirm"] = True
                await self._speak_fixed_text(conn, "我没能识别出当前说话人，请问您怎么称呼？")
                return False

            return True
        except Exception as e:
            logger.bind(tag=TAG).error(f"处理声纹身份状态失败: {e}")
            logger.bind(tag=TAG).debug(f"异常堆栈: {traceback.format_exc()}")
            return True

    async def _flush_dialogue_memory(self, conn: "ConnectionHandler", memory_user_id: str):
        """将增量对话片段保存到指定 memory_user_id 的空间（说话人切换时调用）。

        优化：改为异步后台任务执行，不阻塞说话人切换流程。
        记忆保存由连接关闭时的 _save_and_close 兜底，即使后台任务失败也不影响对话。
        """
        try:
            if not conn.memory or not memory_user_id:
                return

            # 获取上次为该用户保存的对话索引
            last_idx = conn._last_saved_dialogue_index_by_user.get(memory_user_id, -1)
            dialogue = conn.dialogue.dialogue
            total = len(dialogue)

            if total <= last_idx + 1:
                logger.bind(tag=TAG).debug(f"无新对话需要保存: {memory_user_id}, last_idx={last_idx}")
                return

            # 只保存自上次保存后的新消息
            new_msgs = dialogue[last_idx + 1:]
            if len(new_msgs) >= 2:
                # 异步后台保存：使用独立线程 + 独立事件循环，不占用主事件循环
                # save_memory 可能因 NaN 错误降级逐条保存，耗时较长
                # 放在主事件循环上会阻塞对话流程（LLM推理、TTS等）
                threading.Thread(
                    target=self._run_flush_in_thread,
                    args=(conn, new_msgs, memory_user_id, total),
                    daemon=True,
                ).start()
                conn._last_saved_dialogue_index_by_user[memory_user_id] = total - 1
                logger.bind(tag=TAG).info(
                    f"说话人切换 flush 记忆(异步): {memory_user_id}, 新增{len(new_msgs)}条消息"
                )
        except Exception as e:
            logger.bind(tag=TAG).error(f"flush 记忆失败: {e}")

    async def _do_flush_memory(self, conn, new_msgs, memory_user_id, total):
        """后台执行记忆保存（由 _flush_dialogue_memory 通过 create_task 调用）。"""
        try:
            await conn.memory.save_memory(
                new_msgs, conn.session_id, user_id=memory_user_id
            )
            logger.bind(tag=TAG).info(
                f"说话人切换 flush 记忆(后台完成): {memory_user_id}, 新增{len(new_msgs)}条消息"
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"flush 记忆(后台)失败: {e}")

    def _run_flush_in_thread(self, conn, new_msgs, memory_user_id, total):
        """在独立线程 + 独立事件循环中执行记忆保存，不占用主事件循环。

        save_memory 可能因 NaN 错误降级为逐条保存，耗时较长。
        放在主事件循环上会阻塞对话流程（LLM推理、TTS等），因此使用独立线程。
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self._do_flush_memory(conn, new_msgs, memory_user_id, total)
                )
            finally:
                loop.close()
        except Exception as e:
            logger.bind(tag=TAG).error(f"flush 记忆(独立线程)失败: {e}")

    async def _flush_last_speaker_memory(self, conn: "ConnectionHandler"):
        """Flush 当前说话人的记忆（身份过期/连接关闭时调用）。"""
        last_muid = conn.voice_identity.get("memory_user_id")
        if last_muid:
            await self._flush_dialogue_memory(conn, last_muid)

    async def reinquiry(self, conn: "ConnectionHandler", confirm_text):
        prompt = f"请你以```{confirm_text}```为开头，不要揣测用户想法，必须按我说的做，用富有感情的话，只发这一句，然后等待用户回答。！"
        await startToChat(conn, prompt)

    async def _speak_fixed_text(self, conn: "ConnectionHandler", text: str):
        """直接播报固定提示，避免只发送 start 状态导致客户端卡住。"""

        
        if conn.lingxin_sdk:
            # 发送声纹识别结束消息
            await conn.websocket.send(json.dumps({
            "session_id": conn.session_id,
            "type": "voiceprint",
            "action": "end",
            "speaker": "",
            "message": text
            }))
            return


        conn.sentence_id = str(uuid.uuid4().hex)
        conn.tts_MessageText = text

        await send_tts_message(conn, "start")
        conn.client_is_speaking = True
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

    def _parse_name_from_confirm_reply(self, text: str) -> str:
        """仅在等待姓名确认状态下解析姓名。"""
        text = (text or "").strip()
        if not text:
            return ""

        for prefix in ["我是", "我叫", "叫我", "我的名字是", "我名字叫"]:
            if prefix in text:
                name = text.split(prefix, 1)[1].strip(" ，,。.!！?？")
                return name[:20]

        if 1 <= len(text) <= 20:
            return text.strip(" ，,。.!！?？")
        return ""

    def _build_enhanced_text(self, text: str, speaker_name: Optional[str]) -> str:
        """构建包含说话人信息的文本（仅用于纯文本ASR）"""
        if speaker_name and speaker_name.strip():
            return json.dumps(
                {"speaker": speaker_name, "content": text}, ensure_ascii=False
            )
        else:
            return text

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """将PCM数据转换为WAV格式"""
        if len(pcm_data) == 0:
            logger.bind(tag=TAG).warning("PCM数据为空，无法转换WAV")
            return b""

        # 确保数据长度是偶数（16位音频）
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]

        # 创建WAV文件头
        wav_buffer = io.BytesIO()
        try:
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16位
                wav_file.setframerate(16000)  # 16kHz采样率
                wav_file.writeframes(pcm_data)

            wav_buffer.seek(0)
            wav_data = wav_buffer.read()

            return wav_data
        except Exception as e:
            logger.bind(tag=TAG).error(f"WAV转换失败: {e}")
            return b""

    def stop_ws_connection(self):
        pass

    async def close(self):
        pass

    class AudioArtifacts(NamedTuple):
        pcm_frames: List[bytes]
        """PCM音频帧列表"""
        pcm_bytes: bytes
        """合并后的PCM音频字节数据"""
        file_path: Optional[str]
        """WAV文件路径"""
        temp_path: Optional[str]
        """临时WAV文件路径"""

    def get_current_artifacts(self) -> Optional["ASRProviderBase.AudioArtifacts"]:
        return self._current_artifacts

    def requires_file(self) -> bool:
        """是否需要文件输入"""
        return False

    def prefers_temp_file(self) -> bool:
        """是否优先使用临时文件"""
        return False

    def build_temp_file(self, pcm_bytes: bytes) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
            with wave.open(temp_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(pcm_bytes)
            return temp_path
        except Exception as e:
            logger.bind(tag=TAG).error(f"临时音频文件生成失败: {e}")
            return None

    def save_audio_to_file(self, pcm_data: List[bytes], session_id: str) -> str:
        """PCM数据保存为WAV文件"""
        module_name = __name__.split(".")[-1]
        file_name = f"asr_{module_name}_{session_id}_{uuid.uuid4()}.wav"
        file_path = os.path.join(self.output_dir, file_name)

        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 2 bytes = 16-bit
            wf.setframerate(16000)
            wf.writeframes(b"".join(pcm_data))

        return file_path

    async def speech_to_text_wrapper(
        self, opus_data: List[bytes], session_id: str, audio_format="opus"
    ) -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        temp_path = None
        try:
            if audio_format == "pcm":
                pcm_data = opus_data
            else:
                pcm_data = self.decode_opus(opus_data)
            combined_pcm_data = b"".join(pcm_data)

            # free_space = shutil.disk_usage(self.output_dir).free
            # if free_space < len(combined_pcm_data) * 2:
            #     raise OSError("磁盘空间不足")

            if self.requires_file() and self.prefers_temp_file():
                temp_path = self.build_temp_file(combined_pcm_data)

            if (hasattr(self, "delete_audio_file") and not self.delete_audio_file) or (
                self.requires_file() and not self.prefers_temp_file()
            ):
                file_path = self.save_audio_to_file(pcm_data, session_id)

            if len(combined_pcm_data) == 0:
                artifacts = None
            else:
                artifacts = ASRProviderBase.AudioArtifacts(
                    pcm_frames=pcm_data,
                    pcm_bytes=combined_pcm_data,
                    file_path=file_path,
                    temp_path=temp_path,
                )

            text, _ = await self.speech_to_text(
                opus_data, session_id, audio_format, artifacts
            )
            return text, file_path
        except OSError as e:
            logger.bind(tag=TAG).error(f"文件操作错误: {e}")
            return None, None
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return None, None
        finally:
            try:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                if (
                    hasattr(self, "delete_audio_file")
                    and self.delete_audio_file
                    and file_path
                    and os.path.exists(file_path)
                ):
                    os.remove(file_path)
            except Exception as e:
                logger.bind(tag=TAG).error(f"文件清理失败: {e}")

    @abstractmethod
    async def speech_to_text(
        self,
        opus_data: List[bytes],
        session_id: str,
        audio_format="opus",
        artifacts: Optional[AudioArtifacts] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本

        :param opus_data: 输入的Opus音频数据
        :param session_id: 会话ID
        :param audio_format: 音频格式，默认"opus"
        :param artifacts: 音频工件，包含PCM数据、文件路径等
        :return: 识别结果文本和文件路径（如果有）
        """
        pass

    @staticmethod
    def decode_opus(opus_data: List[bytes]) -> List[bytes]:
        """将Opus音频数据解码为PCM数据"""
        decoder = None
        try:
            decoder = opuslib_next.Decoder(16000, 1)
            pcm_data = []
            buffer_size = 960  # 每次处理960个采样点 (60ms at 16kHz)

            for i, opus_packet in enumerate(opus_data):
                try:
                    if not opus_packet or len(opus_packet) == 0:
                        continue

                    pcm_frame = decoder.decode(opus_packet, buffer_size)
                    if pcm_frame and len(pcm_frame) > 0:
                        pcm_data.append(pcm_frame)

                except opuslib_next.OpusError as e:
                    logger.bind(tag=TAG).warning(f"Opus解码错误，跳过数据包 {i}: {e}")
                except Exception as e:
                    logger.bind(tag=TAG).error(f"音频处理错误，数据包 {i}: {e}")

            return pcm_data

        except Exception as e:
            logger.bind(tag=TAG).error(f"音频解码过程发生错误: {e}")
            return []
        finally:
            if decoder is not None:
                try:
                    del decoder
                except Exception as e:
                    logger.bind(tag=TAG).debug(f"释放decoder资源时出错: {e}")
