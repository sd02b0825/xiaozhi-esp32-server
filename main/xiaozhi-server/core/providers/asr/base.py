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
from typing import Optional, Tuple, List, NamedTuple, TYPE_CHECKING


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
                    await self.handle_voice_stop(conn, asr_audio_task)

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
                speaker_name = ""
            else:
                speaker_name = voiceprint_result

            # 判断 ASR 结果类型
            if isinstance(raw_text, dict):
                # FunASR 返回的 dict 格式
                if speaker_name:
                    raw_text["speaker"] = speaker_name

                # 记录识别结果
                if raw_text.get("language"):
                    logger.bind(tag=TAG).info(f"识别语言: {raw_text['language']}")
                if raw_text.get("emotion"):
                    logger.bind(tag=TAG).info(f"识别情绪: {raw_text['emotion']}")
                if raw_text.get("content"):
                    logger.bind(tag=TAG).info(f"识别文本: {raw_text['content']}")
                if speaker_name:
                    logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")

                # 转换为 JSON 字符串用于下游
                enhanced_text = json.dumps(raw_text, ensure_ascii=False)
                content_for_length_check = raw_text.get("content", "")
            else:
                # 其他 ASR 返回的纯文本
                if raw_text:
                    logger.bind(tag=TAG).info(f"识别文本: {raw_text}")
                if speaker_name:
                    logger.bind(tag=TAG).info(f"识别说话人: {speaker_name}")

                # 构建包含说话人信息的JSON字符串
                enhanced_text = self._build_enhanced_text(raw_text, speaker_name)
                content_for_length_check = raw_text
           
            # 处理用户对声纹确认的回答
            await self._handle_voiceprint_confirm(conn, speaker_name, enhanced_text)

            # 性能监控
            total_time = time.monotonic() - total_start_time
            logger.bind(tag=TAG).debug(f"总处理耗时: {total_time:.3f}s")

            # 检查文本长度
            text_len, _ = remove_punctuation_and_length(content_for_length_check)
            self.stop_ws_connection()

            if text_len > 0:
                # 使用自定义模块进行上报
                await startToChat(conn, enhanced_text)
                audio_snapshot = asr_audio_task.copy()
                enqueue_asr_report(conn, enhanced_text, audio_snapshot)
        except Exception as e:
            logger.bind(tag=TAG).error(f"处理语音停止失败: {e}")
            import traceback

            logger.bind(tag=TAG).debug(f"异常详情: {traceback.format_exc()}")
    
    async def _handle_voiceprint_confirm(self, conn: "ConnectionHandler", speaker_name: str, enhanced_text: str):
        """处理用户对声纹确认的回答"""
        try:
            # ============ 【新增】处理用户对声纹确认的回答 ============
            if getattr(conn, 'waiting_voiceprint_confirm', False):
                total_start_time = time.monotonic()
                logger.bind(tag=TAG).debug("进入询问用户后方法")
                # 用户正在确认流程中，先处理回答
                user_text = enhanced_text

                # 如果是JSON格式，提取content字段
                try:
                    if isinstance(user_text, str) and user_text.startswith('{'):
                        user_json = json.loads(user_text)
                        user_text = user_json.get('content', user_text)
                except json.JSONDecodeError:
                    pass

                confirm_speaker = getattr(conn, 'confirm_speaker', None)
                pending_content = getattr(conn, 'pending_voiceprint_content', None)  # 保存的原始内容

                # 重置状态
                conn.waiting_voiceprint_confirm = False
                conn.confirm_speaker = None
                conn.pending_voiceprint_content = None

                logger.bind(tag=TAG).info(f"用户输入内容: {user_text}, confirm_speaker: {confirm_speaker}, pending_content: {pending_content}")
                from core.handle.sendAudioHandle import send_stt_message

                # 简单关键词匹配
                if any(kw in user_text for kw in ["不", "不是", "no", "否", "换人"]):
                    logger.bind(tag=TAG).info(f"用户否认说话人: {confirm_speaker}, 清理缓存")
                    # 清理当前说话人
                    conn.current_speaker = None
                    # 如果 voiceprint_provider 支持清理缓存，可调用
                    if hasattr(conn.voiceprint_provider, 'clear_session_cache'):
                        await conn.voiceprint_provider.clear_session_cache(conn.session_id)
                    confirm_text = f"好的，那请问您是谁呢？"
                    await self.reinquiry(conn, confirm_text)
                    total_time = time.monotonic() - total_start_time
                    logger.bind(tag=TAG).debug(f"声纹确认回答处理完成（否认），总耗时: {total_time:.3f}s")
                    return
                elif any(kw in user_text for kw in ["是", "对的", "没错", "yes", "对", "继续", "是我"]):
                    logger.bind(tag=TAG).info(f"用户确认说话人: {confirm_speaker}")
                    await send_stt_message(conn, f"好的，继续和{confirm_speaker}聊天~")

                    # 🎯 关键：恢复处理之前保存的用户问题
                    if pending_content:
                        logger.bind(tag=TAG).info(f"恢复处理用户问题: {pending_content}")
                        await startToChat(conn, pending_content)
                    total_time = time.monotonic() - total_start_time
                    logger.bind(tag=TAG).debug(f"声纹确认回答处理完成（确认），总耗时: {total_time:.3f}s")
                    return
                else:
                    # 用户回答不明确，再次询问
                    confirm_text = f"我没听清，您是{confirm_speaker}吗？请回答是或不是~"
                    await self.reinquiry(conn, confirm_text)
                    # 重新设置等待确认标记
                    conn.waiting_voiceprint_confirm = True
                    conn.confirm_speaker = confirm_speaker
                    conn.pending_voiceprint_content = pending_content  # 保留待处理内容
                    total_time = time.monotonic() - total_start_time
                    logger.bind(tag=TAG).debug(f"声纹确认回答处理完成（不明确），总耗时: {total_time:.3f}s")
                    return

            # ============ 确认处理结束 ============
            # ============ 【新增】声纹确认询问处理 ============
            need_confirm = False
            confirm_speaker_name = None
            total_start_time = time.monotonic()

            if speaker_name and speaker_name.startswith("__CONFIRM__:"):
                # 🎯 检测到确认标记，提取真实说话人名称
                confirm_speaker_name = speaker_name.replace("__CONFIRM__:", "")
                need_confirm = True
                logger.bind(tag=TAG).warning(f"触发声纹确认询问: {confirm_speaker_name}")

                # 直接发送确认询问，不调用 startToChat
                confirm_text = f"请问当前还是{confirm_speaker_name}在跟我聊天吗？"

                # 设置等待确认标记（可选：用于后续处理用户回答）
                conn.waiting_voiceprint_confirm = True
                conn.confirm_speaker = confirm_speaker_name
                # 使用自定义模块进行上报
                await self.reinquiry(conn, confirm_text)
                # 记录日志后直接返回，不继续聊天流程
                total_time = time.monotonic() - total_start_time
                logger.bind(tag=TAG).debug(f"声纹确认询问处理完成，总耗时: {total_time:.3f}s")
                conn.pending_voiceprint_content = enhanced_text  # 保留待处理内容
                return  # 🎯 关键：直接返回，不调用 startToChat

        except Exception as e:
            logger.bind(tag=TAG).error(f"处理声纹确认失败: {e}")
            logger.bind(tag=TAG).debug(f"异常堆栈: {traceback.format_exc()}")

    async def reinquiry(self, conn: "ConnectionHandler", confirm_text):
        prompt = f"请你以```{confirm_text}```为开头，不要揣测用户想法，必须按我说的做，用富有感情的话，只发这一句，然后等待用户回答。！"
        await startToChat(conn, prompt)

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
