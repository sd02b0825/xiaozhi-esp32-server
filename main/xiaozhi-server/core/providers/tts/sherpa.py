import asyncio
import io
import os
import tarfile
import urllib.request
import wave

import numpy as np
import sherpa_onnx
from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

DEFAULT_MODEL_DIR = "models/sherpa-tts"
DEFAULT_ACOUSTIC_DIRNAME = "matcha-icefall-zh-en"
DEFAULT_ACOUSTIC_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
    "matcha-icefall-zh-en.tar.bz2"
)
DEFAULT_VOCODER_NAME = "vocos-16khz-univ.onnx"
DEFAULT_VOCODER_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/"
    "vocos-16khz-univ.onnx"
)


def _download_file(url: str, dest_path: str) -> None:
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    logger.bind(tag=TAG).info(f"正在下载: {url} -> {dest_path}")
    urllib.request.urlretrieve(url, dest_path)
    if not os.path.isfile(dest_path):
        raise FileNotFoundError(f"下载完成但文件不存在: {dest_path}")


def _extract_tar_bz2(tar_path: str, dest_dir: str) -> None:
    os.makedirs(dest_dir, exist_ok=True)
    with tarfile.open(tar_path, "r:bz2") as tar:
        tar.extractall(path=dest_dir)


def _generated_audio_to_wav_bytes(audio) -> bytes:
    samples = audio.samples
    sample_rate = int(audio.sample_rate)
    arr = np.asarray(samples)
    if arr.dtype in (np.float32, np.float64):
        arr = np.clip(arr, -1.0, 1.0)
        int_samples = (arr * 32767.0).astype(np.int16)
    else:
        int_samples = arr.astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(int_samples.tobytes())
    return buf.getvalue()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.audio_file_type = "wav"

        self.model_dir = config.get("model_dir", DEFAULT_MODEL_DIR)
        self.acoustic_dirname = config.get("acoustic_model_dirname", DEFAULT_ACOUSTIC_DIRNAME)
        self.acoustic_url = config.get("acoustic_model_url", DEFAULT_ACOUSTIC_URL)
        self.vocoder_name = config.get("vocoder_filename", DEFAULT_VOCODER_NAME)
        self.vocoder_url = config.get("vocoder_url", DEFAULT_VOCODER_URL)

        self.num_threads = int(config.get("num_threads", 2))
        self.debug = bool(config.get("debug", False))
        self.speed = float(config.get("speed", 1.0))
        self.sid = int(config.get("sid", 0))
        self.max_num_sentences = int(config.get("max_num_sentences", 1))

        os.makedirs(self.model_dir, exist_ok=True)

        self._ensure_models()
        self.tts = self._build_tts()

    def _acoustic_dir(self) -> str:
        return os.path.join(self.model_dir, self.acoustic_dirname)

    def _vocoder_path(self) -> str:
        return os.path.join(self.model_dir, self.vocoder_name)

    def _ensure_models(self) -> None:
        acoustic_dir = self._acoustic_dir()
        marker = os.path.join(acoustic_dir, "model-steps-3.onnx")
        tarball_name = os.path.basename(self.acoustic_url.split("/")[-1])
        tarball_path = os.path.join(self.model_dir, tarball_name)

        if not os.path.isfile(marker):
            if not os.path.isfile(tarball_path):
                _download_file(self.acoustic_url, tarball_path)
            _extract_tar_bz2(tarball_path, self.model_dir)
            if os.path.isfile(tarball_path):
                os.remove(tarball_path)
            if not os.path.isfile(marker):
                raise FileNotFoundError(
                    f"声学模型未就绪，缺少: {marker}，请检查下载与解压是否成功"
                )

        vocoder_path = self._vocoder_path()
        if not os.path.isfile(vocoder_path):
            _download_file(self.vocoder_url, vocoder_path)
            if not os.path.isfile(vocoder_path):
                raise FileNotFoundError(f"声码器下载失败: {vocoder_path}")

    def _build_tts(self):
        acoustic_dir = self._acoustic_dir()
        vocoder_path = self._vocoder_path()

        rule_fsts = ",".join(
            [
                os.path.join(acoustic_dir, "phone-zh.fst"),
                os.path.join(acoustic_dir, "date-zh.fst"),
                os.path.join(acoustic_dir, "number-zh.fst"),
            ]
        )

        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                matcha=sherpa_onnx.OfflineTtsMatchaModelConfig(
                    acoustic_model=os.path.join(acoustic_dir, "model-steps-3.onnx"),
                    vocoder=vocoder_path,
                    lexicon=os.path.join(acoustic_dir, "lexicon.txt"),
                    tokens=os.path.join(acoustic_dir, "tokens.txt"),
                    data_dir=os.path.join(acoustic_dir, "espeak-ng-data"),
                ),
                num_threads=self.num_threads,
                debug=self.debug,
            ),
            max_num_sentences=self.max_num_sentences,
            rule_fsts=rule_fsts,
        )

        if not cfg.validate():
            raise ValueError("Sherpa OfflineTtsConfig 校验失败，请检查模型路径与文件完整性")

        return sherpa_onnx.OfflineTts(cfg)

    def _text_to_speak_sync(self, text, output_file):
        audio = self.tts.generate(text, sid=self.sid, speed=self.speed)
        wav_bytes = _generated_audio_to_wav_bytes(audio)
        if output_file:
            os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
            with open(output_file, "wb") as f:
                f.write(wav_bytes)
            return None
        return wav_bytes

    async def text_to_speak(self, text, output_file):
        return await asyncio.to_thread(self._text_to_speak_sync, text, output_file)
