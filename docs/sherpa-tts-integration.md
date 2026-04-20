# SherpaTTS（sherpa-onnx 本地离线）集成说明

## 说明

- 使用 `sherpa-onnx` 的 Matcha 声学模型 + Vocos 声码器，在服务器本地推理。
- Python 依赖：项目已在 `main/xiaozhi-server/requirements.txt` 中包含 `sherpa_onnx`，与 Sherpa ASR 共用该包，无需额外安装同名依赖。
- 模型默认目录：`models/sherpa-tts`。若缺少声学模型包或声码器文件，**首次启动**时会自动从 GitHub Release 下载并解压（需可访问外网）。

## 配置

1. 在 `config.yaml`（或覆盖配置 `data/.config.yaml`）的 `TTS` 下启用 `SherpaTTS` 段，示例见仓库内默认配置。
2. 将 `selected_module.TTS` 设为 `SherpaTTS`。

可选配置项：

| 配置项 | 含义 |
|--------|------|
| `model_dir` | 模型根目录，默认 `models/sherpa-tts` |
| `acoustic_model_dirname` | 解压后的声学模型目录名，默认 `matcha-icefall-zh-en` |
| `acoustic_model_url` | 声学模型压缩包 URL（一般无需改） |
| `vocoder_filename` | 声码器文件名，默认 `vocos-16khz-univ.onnx` |
| `vocoder_url` | 声码器下载地址（一般无需改） |
| `num_threads` | 推理线程数，默认 `2` |
| `speed` | 语速，默认 `1.0` |
| `sid` | 说话人 id，默认 `0` |
| `debug` | 是否打印 sherpa 调试信息，默认 `false` |
| `max_num_sentences` | 与官方示例一致时可设为 `1` |

## 目录结构（下载完成后）

在 `model_dir` 下应包含：

- `matcha-icefall-zh-en/`：声学模型及相关资源（lexicon、tokens、FST、espeak-ng-data 等）。
- `vocos-16khz-univ.onnx`：声码器。

## 更多资料

- 官方文档与模型发布：<https://github.com/k2-fsa/sherpa-onnx>
