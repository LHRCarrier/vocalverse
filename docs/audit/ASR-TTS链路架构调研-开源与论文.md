# ASR / TTS 开源链路架构调研报告

> 主题：主流开源项目、论文与工具中 ASR / TTS 链路的**模块划分、数据流、接口约定、可插拔机制**
> 定位：语音链路架构调研（供 VocalVerse 分层决策；配套落地见
> `docs/audit/ASR-TTS链路审计与重构方案.md`）｜落位：`docs/audit/`（音频/语音链路类，AGENTS.md 文档纪律）
> ⚠️ 本报告为**调研结论**而非 ADR：涉及选型的判断须回 `docs/06` 登记后才可用于实现。

---

## 1. 调研范围与方法

**方法。** 全部结论经 `web_search` / `web_fetch` 实检，优先一手来源（官方文档站、PyPI 项目页、
GitHub 仓库页、arXiv `/abs/` 页）。**筛选标准**：① 能核实到「模块名 / 函数签名 / 协议字段」粒度；
② 对本项目（Python/FastAPI + Vue、英语口语练习、云端与本地引擎并存）有迁移价值；③ 部署
形态可查；④ 存在被反复验证的接口约定而非单项目私有实现。

**限制（须与结论一并读）。** `raw.githubusercontent.com` 抓取失败；arXiv/ISCA PDF 返回
`unsupported content type`（改用 `/abs/` 或 ar5iv）；`platform.openai.com` 403（改用 Azure OpenAI
文档核实同一规范）；GitHub 仓库页导航噪声大。凡无法核实者标注**未核实**，不以推测填充。

**覆盖。** ASR 8 项 / TTS 10 项 / 编排层 6 项 / 论文 17 篇。

---

## 2. ASR 链路架构对比表

统一骨架：`解码重采样 → log-Mel → 声学模型 → 分词与时间戳后处理`。差异集中在**分段策略
（VAD / chunk / 流式）**、**签名风格（对象方法 vs C 函数 vs 协议事件）**、**哪些环节被拆成独立件**。

| 项目 | 模块划分 | 数据流 | 接口签名风格 | 可插拔点 | 配置方式 | 许可与部署 |
|---|---|---|---|---|---|---|
| **OpenAI Whisper** | 单模型多任务；**无独立 VAD/对齐/标点模块** | 30s 音频 → `log_mel_spectrogram(audio, n_mels=model.dims.n_mels)` → `whisper.decode(model, mel, DecodingOptions())` → 含 `<\|transcribe\|>`/`<\|nospeech\|>`/时间戳 token 的**单序列**；长音频靠 30s 滑窗 | `whisper.load_model("turbo")`、`model.transcribe(path)`、`detect_language()`；CLI 同参 | 只能换模型规格/任务/语言；**无 VAD、LM、对齐插拔点** | CLI flags + kwargs / `DecodingOptions` dataclass | MIT（代码+权重）· 需系统 ffmpeg｜[PyPI](https://pypi.org/project/openai-whisper/) |
| **faster-whisper** | PyAV 解码 / log-Mel / CTranslate2 / 分段组装；**VAD 独立**（`vad.py` 内嵌 Silero） | 音频 → 16k 单声道 → log-Mel → CT2 → **`Segment` 的 generator**（`.words[]` 需 `word_timestamps=True`）+ `info.language` | `model.transcribe(audio, beam_size=5, word_timestamps=True, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500)) -> (segments, info)`；`BatchedInferencePipeline.transcribe(..., batch_size=16)` 为 **drop-in 替代** | VAD 开关与参数；任意 CT2 模型目录/HF id；`device`、`compute_type` | kwargs（默认 `beam_size=5`，**与 Whisper 的 1 不同**，对比须对齐） | MIT · wheel 1.2.1 · PyAV 免装 ffmpeg · GPU 需 CUDA12/cuDNN9｜[PyPI](https://pypi.org/project/faster-whisper/) |
| **whisper.cpp** | 仅 `whisper.h` + `whisper.cpp`，余为 ggml | 16-bit WAV → f32 PCM（16k / FFT 400 / HOP 160 / CHUNK 30s）→ encoder → segments 与 token 时间戳 | **C 函数式**：`whisper_init_from_file_with_params` / `whisper_full` / `whisper_full_n_segments` / `whisper_full_get_segment_text` / `whisper_free`；结构体 `whisper_full_params`、`whisper_vad_params` | 量化 ggml 模型文件；CoreML / OpenVINO / Vulkan / ROCm 后端 | CLI flags + C struct | MIT · C/C++ · WASM/iOS/Android/RPi｜[whisper.h](https://github.com/ggml-org/whisper.cpp/blob/master/include/whisper.h)；流式示例 `whisper-stream --step 500 --length 5000` |
| **WhisperX** | faster-whisper 批量 ASR → **VAD Cut & Merge** → **wav2vec2 强制音素对齐** → 可选 pyannote 说话人分离 | 长音频 → VAD 切并 → 批量转写 → 词级时间戳 → 按说话人分句 | CLI `whisperx a.wav --model large-v2 --align_model … --batch_size 4`；Python `whisperx.load_model`、`DiarizationPipeline` | VAD 默认开；`--align_model` 逐语言换对齐模型；`--min/max_speakers` | CLI flags + kwargs | PyPI `whisperx`（fast-whisper 后端）· 称 70× 实时｜[PyPI](https://pypi.org/project/whisperx/)；**说话人分离不在论文摘要内** |
| **FunASR**（达摩院） | **AutoModel 流水线**：VAD → ASR → 标点 → 说话人，各段独立模型 | 16k 单声道 → VAD 切段 → ASR → punc → CAM++ 聚类出匿名说话人；`result[0]["sentence_info"]` 含 `start`(ms)/`spk` | `AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc", spk_model="cam++")`；`generate(input=…, batch_size_s=300, hotword="词 20")`；CLI `funasr a.wav --spk --timestamps -f json` | **每段都是可换模型**（`*_model`/`*_kwargs`）；`fsmn-vad` 与 `silero-vad` 可互换 | kwargs + JSON/CLI；流式用 `cache` + `chunk_size=[0,10,5]` + encoder/decoder `chunk_look_back` | **工具包 MIT，权重许可另计** · PyPI/Docker/WebSocket｜[PyPI](https://pypi.org/project/funasr/) |
| **sherpa-onnx**（k2-fsa） | 按**任务族**切（ASR/TTS/VAD/KWS/标点/说话人/语种…）；online 与 offline 各一套 | WAV → 重采样 16k → 特征 → ONNX encoder/decoder/joiner → tokens | **统一 C API + 12 语言绑定**；流式循环 `create_stream() → accept_waveform(sr, samples) → is_ready() → decode_stream() → get_result()` | encoder/decoder/joiner/tokens 逐模型换；`--lm`、`--lodr-fst`、热词；`silero-vad`/`ten-vad` | CLI flags + config struct（`EndpointConfig`、`FeatureExtractorConfig`） | Apache-2.0 · C++/ONNX · 全离线｜[PyPI](https://pypi.org/project/sherpa-onnx/)；**端点规则**：未解码任何内容静音 2.4s / 已解码后 1.2s / 单句 20s 上限（`min_trailing_silence`、`min_utterance_length`）[endpoint.h](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/csrc/endpoint.h) |
| **Vosk / Kaldi** | Kaldi 分层（特征/声学/解码图/FST 解码/在线解码/LM）；Vosk 封装为 `libvosk` | PCM 流 → 特征 → 声学模型 → 解码图 + LM → JSON 假设 | `Model(path)`、`KaldiRecognizer(model, sr[, grammar])` + `AcceptWaveform`/`Result`/`SetWords`/`SetPartialWords`/`SetMaxAlternatives`/**`SetEndpointerMode`**；C 侧 `vosk_model_new` | 模型包为替换单位；可选 JSGF 语法与说话人模型；小模型支持动态词表 | kwargs + 模型目录 | Apache-2.0 · wheel 覆盖 linux/win/armv7/aarch64 · 模型 42MB–1.3GB｜[vosk-api](https://github.com/alphacep/vosk-api/blob/master/python/vosk/__init__.py)、[模型表](https://alphacephei.com/vosk/models)；**Kaldi「HCLG」字面命名未核实** |
| **NVIDIA NeMo**（含 Riva） | `ASRModel` + `TranscribeConfig` + `Hypothesis`；解码策略与 LM 融合为独立策略；模块化 `AudioToMelSpectrogramPreprocessor`/`ConformerEncoder`/`RNNTDecoder`+`RNNTJoint` | 音频（**强制 16k 单声道**）→ Mel → encoder → CTC/RNNT/TDT 解码 → `Hypothesis`（`.timestamp['char'/'word'/'segment']`） | 真实签名 `transcribe(use_lhotse=True, batch_size=4, return_hypotheses=False, num_workers=0, timestamps=None, override_config=None, **kw)`，内部委派 `transcribe_generator()`；`change_decoding_strategy()`、`set_inference_prompt("en-US")` | 解码策略/预处理器/增强器可换；长音频 `change_attention_model(rel_pos_local_attn)`；**Riva 把 AM/LM/标点/ITN 作为独立 artifact**，按 `asr_acoustic_model`+`asr_language_code` 选 | YAML/OmegaConf + dataclass kwargs | Apache-2.0（文件头）· pip / `uv sync --extra cu13` / NGC｜[NeMo inference](https://docs.nvidia.com/nemo/speech/latest/asr/inference.html)、[Riva ASR](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/asr/asr-overview.html) |

> **Silero VAD**（MIT，JIT ~2MB / ONNX，30ms 块单 CPU 线程 <1ms）被 faster-whisper、Pipecat、
> LiveKit、sherpa-onnx **同时选作默认 VAD**——「VAD 可替换」最硬的证据；它**无同行评议论文（未核实）**
> ｜<https://pypi.org/project/silero-vad/>

---

## 3. TTS 链路架构对比表

与 ASR 最大的结构差异：TTS 多出一层**文本前端**，且「音色」是一等公民。综述给出经典三段
**text analysis → acoustic model → vocoder**（[2106.15561](https://arxiv.org/abs/2106.15561)、
[2310.14301](https://arxiv.org/abs/2310.14301)）；工程分歧在**折叠程度**：轻量 ONNX 模型把
「声学模型+声码器」合成一个文件、把前端外置给 espeak-ng / misaki。

| 项目 | ① 文本前端 | ② 声学模型 | ③ 声码器 | 音色与风格控制 | 接口签名 | 配置 | 许可与部署 |
|---|---|---|---|---|---|---|---|
| **edge-tts** | 无（微软服务端；**自定义 SSML 已移除**，只允许单 `<voice>` 包单 `<prosody>`） | 闭源云端 | 云端 | `voice`（`en-US-JennyNeural`）+ `--rate/--volume/--pitch` | CLI `edge-tts --write-media a.mp3 --write-subtitles a.srt`；Python `edge_tts.Communicate` 为**异步事件流**——本仓按 `{"type":"audio"}` 与 `{"type":"WordBoundary"}` 模拟（`tests/test_client_realpath.py`），即天然能吐**词级边界** | 仅 flag/kwargs，无 JSON | **LGPLv3** · 网络客户端 · 输出 **mp3**（`audio-24khz-48kbitrate-mono-mp3`）· 依赖 `WSS + TrustedClientToken + Sec-MS-GEC`（随 Chromium 版本变）→ **上游改协议即失效**｜[PyPI](https://pypi.org/project/edge-tts/) |
| **Azure Speech SDK** | 服务端黑盒（**未核实**） | 服务端 | 服务端 | 音色来自 Voice List API（400+ 声音/140+ 语言）；韵律走 **SSML**（`<prosody>`、`<bookmark>`） | `SpeechSynthesizer(cfg, audio_cfg)` → `speak_text_async()`/`speak_ssml_async() -> SpeechSynthesisResult{audio_data}`；`set_speech_synthesis_output_format(Riff24Khz16BitMonoPcm)`；**流式靠事件** `Synthesizing`（每块触发）/`WordBoundary`/`VisemeReceived`；非流式 `AudioDataStream.save_to_wav_file` | `SpeechConfig` + SSML，无 JSON | 商业条款**未核实** · 自定义声音（`endpoint_id`）与容器化本地端点｜[MS Learn](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis) |
| **Piper**（`piper-tts` 1.8.0） | **内嵌 espeak-ng** 做音素化（README 自述 "embeds espeak-ng"）；也可直接喂音素 | 与声码器**合并为单个 ONNX voice 文件**（`onnxruntime>=1,<2`；内部声码器插拔点**未核实**） | 同上 | **换音色 = 换模型文件**；多说话人由 `speaker_id_map`/`num_speakers`；**无风格控制字段** | CLI / Python / `http`(Flask) / C++ `libpiper` | 同名 **`.onnx.json`** 声明式，字段可枚举：`audio`、`espeak`、`phoneme_type`、`phoneme_map`、**`phoneme_id_map`（音素→u8）**、`num_speakers`、`speaker_id_map`、`piper_version`、`language` | **GPL-3.0-or-later** ⚠️ · abi3 wheels（win/mac/linux/aarch64）· 离线 · 多语言前端是**逐语言 extras**（`zh`=g2pW、`ja`=pyopenjtalk、`th`=tltk）｜[PyPI](https://pypi.org/project/piper-tts/)、[字段表](https://docs.rs/piper1-rs/latest/piper1_rs/json_schemas/data_file/struct.ModelConfig.html) |
| **Kokoro-82M** | **misaki** G2P 为主；**espeak-ng 作 OOD/非英语回退**（Windows 需另装 msi） | Kokoro-82M（**StyleTTS2 架构**，致谢 yl4579） | 内置，不单独暴露 | `voice='af_heart'` 预设名**或直接传 voice tensor**（`torch.load('voice.pt')`）→ 音色与模型解耦；`speed` 控速 | `KPipeline(lang_code='a')`；`pipeline(text, voice=…, speed=1, split_pattern=r'\n+') -> generator of (graphemes, phonemes, audio)`——**逐段暴露「字素/音素/音频」边界** | 构造 `lang_code`（a=en-US、b=en-GB、z=zh…）+ 调用参数 | Apache-2.0（代码+权重）· pip · 24kHz · 离线 · Python 3.10–3.12｜[PyPI](https://pypi.org/project/kokoro/) |
| **KittenTTS** | **前端显式拆三段**：`TextPreprocessor`（数字/货币/时间归一）→ **espeak-ng (FFI→IPA)** → `TextCleaner` | 极小 ONNX（nano 15M≈24MB int8、micro 40MB、**mini 80M/78MB**） | 合并 | 音色 = **声音向量**（`voices.npz`，8 个 `expr-voice-2..5-m/f`）+ `speed`；风格控制**未核实** | `KittenTTS().generate(text=…, voice="expr-voice-2-m", speed=1.0) -> audio`（24kHz Float32），IO 由调用方负责 | 调用参数，无 JSON | 权重 Apache-2.0（据本仓 docs/46）；**PyPI 未列 license、KittenML 主仓许可未核实** · 依赖 `espeakng-loader` · 首次下载后离线｜[PyPI](https://pypi.org/project/kittentts/)、[流水线图](https://pub.dev/packages/flutter_kitten_tts) |
| **Coqui TTS / XTTS** | 未核实为独立字段（各模型自带前端） | **目录结构即模块划分**：`TTS/tts`（Tacotron2/Glow-TTS/FastPitch/VITS…）、`TTS/speaker_encoder`、`TTS/vocoder` 三者并列 | **声码器可换**：MelGAN/MultiBand-MelGAN/ParallelWaveGAN/HiFiGAN/UnivNet/WaveRNN/WaveGrad；CLI `--vocoder_name` 或 `--vocoder_path`+`--vocoder_config_path` | XTTSv2：`speaker_wav` 零样本克隆、16 语言、称 <200ms 流式；另有 `voice_conversion_to_file(source_wav, target_wav, …)` | `tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")`；`tts.tts(text=…, speaker_wav=…, language="en")`；`tts_to_file(…, file_path="out.wav")` | 每模型一份 `config.json`（`--config_path`）+ `speakers_file_path`；自带 Flask(:5002) 与 docker | 代码 **MPL-2.0** · **XTTS 走 CPML（非商用，原文未核实）** · 离线可跑｜[PyPI](https://pypi.org/project/TTS/) |
| **MeloTTS** | **依赖清单直接暴露前端分层**：TN = `num2words`/`inflect`/`unidecode`/`anyascii`；G2P = `g2p_en`/`eng_to_ipa`/`gruut`/`mecab+unidic+fugashi`/`g2pkk`/`jieba+pypinyin+cn2an`；语种 `langid`、分句 `txtsplit`、韵律 `transformers==4.27.4`(BERT) | 未核实 | 未核实 | 未核实 | 未核实 | 未核实 | **license 为空 → 未核实**（未核实前不得引入）｜[PyPI JSON](https://pypi.org/pypi/meloTTS/json) |
| **ChatTTS** | 含 `RefineTextParams`（句级 token 预测） | 自回归语义 token 模型（依赖 `vector_quantize_pytorch`） | **Vocos**（README 致谢） | **风格/韵律用特殊 token 显式编码**：句级 `[oral_0-9]`/`[laugh_0-2]`/`[break_0-7]`，词级 `[uv_break]`/`[laugh]`/`[lbreak]`；音色 = `sample_random_speaker()` 的 `spk_emb`（可存可复用） | `ChatTTS.Chat().load(compile=False)`；`infer(texts, params_refine_text=…, params_infer_code=…)` → 24kHz numpy | Python kwargs，无 JSON | 代码 AGPLv3+ / 模型 CC BY-NC 4.0（**上游声明仅限学术研究**）· 本地 PyTorch ~4GB 显存｜[PyPI JSON](https://pypi.org/pypi/ChatTTS/json) |
| **F5-TTS** | **反向路线：取消文本前端**——无 duration model、无 text encoder、无音素对齐；文本以 filler token 补齐后直接去噪 | flow matching + DiT（ConvNeXt V2 精炼文本）+ Sway Sampling | **Vocos / BigBGAN**（致谢），另有社区 ONNX/MLX | 零样本克隆 = `--ref_audio` + `--ref_text`（`ref_text` 留空则由 ASR 转写） | `f5-tts_infer-cli --model F5TTS_v1_Base --ref_audio … --ref_text … --gen_text …` | **`.toml` 配置文件**（`-c custom.toml`）——与 kwargs 派对照 | 代码 **MIT** / 预训练模型 **CC-BY-NC** ⚠️ · 离线｜[PyPI](https://pypi.org/project/f5-tts/) |
| **GPT-SoVITS** | 未核实 | 两阶段 **GPT（AR 语义 token）→ SoVITS（VITS 声码器）**（二手来源） | 同 SoVITS | 零样本 5 秒 / 少样本 1 分钟微调 / 跨语言 | 未核实（交付形态为 WebUI） | 未核实 | 仓库与「MIT」许可**均为二手来源 → 未核实** |
| **espeak-ng** | 它就是前端本身：**音素/IPA 输出**，另自带共振峰合成可独立发音 | 无 | 无 | `-v <voice>`（`af+m3` 变体）、`-s/-p/-a` 控速/音高/音量 | **可命令行导出音素**（被当 G2P 用的原因）：`-x` 音素助记符、`--ipa`（1/2/3 控连音）、`--pho`、`--phonout`；`-m` 收 SSML；`--voices[=lang]`；`-w` 出 WAV | CLI 参数 | **GPL-3.0 系（具体版本未核实）** ⚠️——**引入 Piper/KittenTTS 时最需法务确认的一环**｜[manpage](https://manpages.debian.org/unstable/espeak-ng-espeak/espeak.1.en.html) |

> 零样本 TTS 的模块划分公共祖先 = **VALL-E**：把 TTS 建模为**离散 codec code 上的条件语言模型**，
> 「声学模型+声码器」被换成「codec tokenizer + AR/NAR LM」，用未见说话人的 **3 秒注册音**零样本克隆
> （[2301.02111](https://arxiv.org/abs/2301.02111)）。**CosyVoice 2** 是当前最完整的公开拆解：文本侧
> 只用 BPE、**显式取消 G2P 前端**；FSQ 语义 tokenizer(25Hz) → 统一 text-speech LM（Qwen2.5-0.5B，
> token 交错 5:15，流式/非流式共用）→ **chunk-aware 因果 flow matching**（Mel 50Hz@24kHz）→ 预训练
> 声码器；v2 **去掉 v1 的 text encoder 与 speaker embedding**；首包延迟写成公式
> `L_TTS = M·d_lm + M·d_fm + M·d_voc`（[2412.10117](https://arxiv.org/abs/2412.10117)）。

---

## 4. 编排层（Agent pipeline）抽象对比表

| 框架 | STT / TTS 服务接口 | 帧 / 流模型 | VAD 与打断 | 引擎注册与选择 | 生命周期 |
|---|---|---|---|---|---|
| **Pipecat** | 子类**必须实现** `async run_stt(audio: bytes) -> AsyncGenerator[Frame\|None, None]` 与 `async run_tts(text, context_id)`——即「引擎只把一段输入变成一串帧」；`STTService`（流式 WS）与 `SegmentedSTTService`（本地 VAD 切段 + HTTP，`wants_wav_segments`、`trailing_silence_secs`）是两种实现 | **一切皆 `Frame` dataclass**，三分类即打断语义：`DataFrame`/`ControlFrame` **打断时丢弃**，`SystemFrame` **不丢弃**；`FrameDirection.DOWNSTREAM/UPSTREAM`；`broadcast_frame()` 双向广播、`broadcast_sibling_id` 配对；帧带 `pts`(ns) | 本地 `SileroVADAnalyzer`（官方称比云端快 150–200ms）；VAD 发 `VADUserStarted/StoppedSpeakingFrame`；打断广播 `InterruptionFrame` → 丢排队数据帧、清 TTS 缓冲、**只有已播出的文本进 assistant context**；`UninterruptibleFrame` mixin 保护不可丢帧 | 无注册表：实例直接进 `Pipeline([...])`；运行期 `*UpdateSettingsFrame`（typed `Service.Settings`）；**切换用 `ServiceSwitcher(services=[…], strategy_type=Manual\|Failover)`**，failover 按 `is_usable` 自动换并触发 `on_service_switched` | `setup()`→`start()`→`stop()`（优雅）/`cancel()`（立即）→`cleanup()`；`keepalive_timeout` 发静音保活；`max_consecutive_zero_audio_contexts`(默认 3) 把连续无音频判为服务失效 |
| **LiveKit Agents** | `stt.STT`(ABC)：`recognize(buffer, *, language, conn_options) -> SpeechEvent`、`stream(...) -> RecognizeStream`（`push_frame/flush/end_input`）、`prewarm()`、`aclose()`；**能力显式声明** `STTCapabilities(streaming, interim_results, diarization, aligned_transcript, …)`；非流式 TTS 自动包 `tts.StreamAdapter`，非流式 STT 需 `stt.StreamAdapter(stt=…, vad=…)` | 上游 `rtc.AudioFrame` 异步流；STT 产 `SpeechEvent`、LLM 产 `ChatChunk`、TTS 产 `rtc.AudioFrame`；结点可覆写 `Agent.stt_node/llm_node/tts_node/transcription_node` | 五种 turn 模式并列：turn detector 模型（默认）/ realtime 内置 / `"vad"` / `"stt"` / `"manual"`（push-to-talk）；打断有 `enabled`、`mode`(`adaptive`/`vad`)、`min_words`、`min_duration`；**假打断**专治：`false_interruption_timeout` + `resume_false_interruption` 从中断处续讲 | 构造注入 + `livekit-plugins-<provider>` 独立包；`Agent.update_options(stt=…, tts=…)` 热插拔；**故障转移有专门适配器 `stt.FallbackAdapter([stt1, stt2], vad=…)`**；realtime 模式禁用打断会**抛 `ValueError`** | `prewarm()`/`aclose()`；重试与超时集中 `APIConnectOptions(max_retry, retry_interval, timeout)` 可逐服务覆盖；`interrupt()`/`clear_user_turn()`/`commit_user_turn()` |
| **Vocode** | 五件套 `Transcriber`/`Agent`/`Synthesizer`/`InputDevice`/`OutputDevice`；provider 以子类区分（`DeepgramTranscriber`、`ElevenLabsSynthesizer`…） | `StreamingConversation` 顶层编排异步音频流、`TranscriptionsWorker`、何时生成回复 | `EndpointingConfig` 可插拔（`DeepgramEndpointingConfig(vad_threshold_ms=500, utterance_cutoff_ms=1000)`）；`AgentConfig.interrupt_sensitivity: low\|high` 忽略 backchannel；`conversation_speed` 按用户 WPM 自适应 | 无注册表：部件实例交给 `Conversation`；每 provider 配 `*Config.from_input_device(...)` 做「设备→配置」适配 | 未核实 |
| **OpenAI Realtime API** | 无独立 STT/TTS：单模型直吃直吐；`session.type` 取 `realtime`/`transcription`；转写需显式开 `input_audio_transcription`，音色由 `session.voice` | 事件协议 `session.update→session.updated`；`input_audio_buffer.append/.commit`；服务端 `.speech_started/.speech_stopped/.committed`；`response.create→response.created→…audio_transcript.delta/audio.delta→.done`。音频 **PCM16/单声道/24kHz**、base64、建议 ~100ms/块，会话上限 60 分钟 | 服务端 VAD：`turn_detection = none\|server_vad\|semantic_vad`；`server_vad` 调 `threshold/prefix_padding_ms/silence_duration_ms/create_response`；打断须**成对** `response.cancel` + `conversation.item.truncate`。LiveKit 实测 `threshold=0.7, silence_duration_ms=400` 适合电话噪声 | 无注册表；`turn_detection=None` 可把 turn 决策交还客户端 | 会话级｜规范经 [Azure 实时音频文档](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/realtime-audio) 核实（OpenAI 站 403） |
| **Home Assistant Assist** | 四段 `wake_word→stt→intent→tts`，由 integration 提供引擎实体 | 单次 WS `assist_pipeline/run`（`start_stage`/`end_stage`/`pipeline`/`input`/`timeout` 默认 300s）；执行期事件流 `run-start`、`stt-vad-start/end`、`stt-end`、`intent-progress`、`tts-start/end`；二进制音频块以 `stt_binary_handler_id` 单字节前缀复用同一连接 | 内部 VAD 产 `stt-vad-start/end`；建议客户端用**本地 VAD** 只在有人说话时推流；wake 阶段静音超时被内部 VAD 持续重置 | **可插拔引擎的教科书范例**：每个 stage 事件带 `engine` 字段（`stt-start.engine`、`tts-start.engine`）；pipeline 定义绑定「引擎+语言+音色」，`assist_pipeline/pipeline/list` 取 ID；缺引擎返回**具名错误码**（`stt-provider-missing`、`stt-provider-unsupported-metadata`、`stt-no-text-recognized`、`tts-not-supported`…） | `run` 级 timeout；`run-start.tts_output.stream_response` 声明该 TTS 能否边生成边播 |
| **Wyoming**（Rhasspy/OHF-voice） | **进程间协议**而非库：ASR/TTS/wake/intent 各自独立进程、语言无关，JSONL + PCM 走 TCP | 帧 = `{"type","data","data_length","payload_length"}\n` + 可选 JSON 附加 + 可选二进制；音频固定 `audio-start → audio-chunk{rate,width,channels,timestamp} → audio-stop` | `voice-started`/`voice-stopped`；**VAD 归属可协商**：ASR 在 `info` 声明 `requires_external_vad`，为 false 时请求方可传 `vad_sensitivity` | **能力协商式注册**：`describe→info` 返回各域 `models[]`（`name`/`languages`/`speakers`/`installed`/`attribution`）+ 能力布尔位（`supports_transcript_streaming`、`supports_synthesize_streaming`、`prefers_auto_gain_enabled`…）；`select-program` 在一次连接内选定端点 | 无重连语义；**无鉴权无加密，官方明确只用于可信网络**｜<https://pypi.org/project/wyoming/> |

**级联 vs 端到端。** LiveKit 分三类：**STT-LLM-TTS 级联**（可换单段、完整文本审计链、interim 转写、
`say()` 播精确脚本；代价是延迟叠加 + 韵律在转写处丢失）、**Realtime 单模型**（延迟最低、输出有表现力、
能听见韵律；代价是转写滞后、无脚本化播报、provider 锁死、难审计）、**Half-cascade**（realtime 只听 +
独立 TTS 说）。官方对多数生产 Agent 仍默认级联（[LiveKit pipeline types](https://docs.livekit.io/agents/models/pipelines.md)）。
对本项目：级联不是落后方案，而是**词级时间戳与可解释评分的前提**。

---

## 5. 共性模式提炼

1. **引擎注册表 + 声明式 spec + 工厂按配置解析**。Wyoming 用 `describe→info` 运行时能力清单；HA 用
   引擎实体 + pipeline 绑定；Pipecat 直接把实例放进 pipeline。本仓已收敛出 `app/audio/registry.py` 的
   `ProviderSpec(name, factory, priority, is_local, media_type, ext)` + `resolve()`。
2. **能力探测先行，而非「先调用再看异常」**。`is_available()` 是通用契约名（本仓 `TTSClient`）；
   Wyoming 协议化为 `installed`/`supports_*`；LiveKit 用 `STTCapabilities`；HA 变成具名错误码。
3. **统一中间表示 dataclass**：NeMo `Hypothesis`、Pipecat `Frame`、Wyoming `transcript` 事件
   ⇔ 本仓 `ASRResult{text, segments, words, duration, no_speech}`。
4. **流式与非流式并存于同一抽象的两个实现**：Pipecat `STTService` vs `SegmentedSTTService`（并把
   `trailing_silence_secs` 默认 0.5s 补静音，防 VAD 截断吞末词）；NeMo buffered vs cache-aware；
   sherpa-onnx `OnlineRecognizer` vs `OfflineRecognizer`；WeNet 用动态 chunk 注意力统一两者。
5. **VAD / 端点检测是独立可换子系统，且默认不外包云端**：Silero 被五个项目同时选为默认；Pipecat
   给出「本地比云端快 150–200ms」的量化理由；sherpa-onnx 把端点规则写成**三个可配阈值**（2.4s/1.2s/20s）。
6. **文本前端独立于声学模型**：Pipecat 在 LLM 与 TTS 间插 `LLMTextProcessor` + `text_transforms`/
   `skip_aggregator_types`，并声明「文本变换只影响 TTS，不污染 LLM 上下文」；Kokoro 的
   `(graphemes, phonemes, audio)` 暴露前端边界；F5-TTS / CosyVoice 2 则**反向取消前端**。
7. **数据/控制/系统三类帧分流，打断按类别施加不变量**：Pipecat 把「打断时丢哪些帧」上升为**类型系统
   约束**，比在每个 processor 手写 `if interrupted: return` 更不易漏。
8. **生命周期显式化：预热/保活/卸载/预算分离**：Pipecat `keepalive_timeout` 发静音、
   `stop_frame_timeout_s` 收尾；LiveKit `prewarm()`/`aclose()`；本仓 `ensure_ready()`/`unload()` 幂等。
9. **缓存键含 provider + 引擎版本，且按 provider 物理隔离容器**：本仓
   `tts_cache_key = sha1(provider|engine_version|voice|rate|text)`，edge→mp3 / kitten→wav 分目录存。
10. **失败显式降级而非静默替换，并把非法组合变成启动期硬错误**：本仓 `auto` 降级留 `degraded`/`notes`，
    显式 provider 不可用抛 `ProviderUnavailable`→503；HA 用错误码枚举；LiveKit 对「realtime 模式禁用
    打断」直接抛 `ValueError`。

---

## 6. 反模式清单

| # | 反模式 | 后果 | 证据 |
|---|---|---|---|
| 1 | **两套并行 provider 选择实现** | 加第三个引擎必漏改一处；strict/auto 语义不一致 | 本仓 `base.get_tts_client`(edge\|azure) 与 `reading.tts_client`(auto\|edge\|kitten) 并存，`registry.py` 记为重构动因 |
| 2 | **provider 判断散落调用点**（`isinstance` 反推） | 漏判即把目录/扩展名/Content-Type 一起带错 | 本仓 `routes/reading_tts.py:_provider_of` |
| 3 | **缓存键漏 provider / 引擎版本** | 换引擎或升 SDK 后仍命中陈旧音频 | 本仓 docs/44 P1-B 整改项 |
| 4 | **音频容器硬编码 mp3 / `audio/mpeg`** | 本地 WAV 被标 MP3，Blob type 错、解码失败 | 本仓 docs/45 §5「防 wav 标 audio/mpeg 播坏」 |
| 5 | **模型权重与代码耦合或入库** | 仓库膨胀、克隆变慢 | 本仓红线：`voice_models_dir` 运行时引用，权重不入库 |
| 6 | **网络客户端无超时/无熔断** | 单次卡死 → 信号量槽不释放 → 全站链路死锁 | 本仓 `vasr-01`：whisper 线程挂起致槽位不释放；`tts.py` 以单句超时兜底 |
| 7 | **同步 CPU 引擎跑在事件循环里** | 阻塞整个 FastAPI worker | 正解 `asyncio.to_thread`（本仓 ASR 与 KittenTTS 均如此） |
| 8 | **静默替换引擎**（显式要 A 却给了 B） | 用户拿到未声明音色；成本与合规口径失真 | 本仓以 `ProviderUnavailable`+503 显式化；未接线 Azure 做成显式 `is_available=False` 客户端 |
| 9 | **把「空转写」当「失败」重试** | 用户静音时反复重试并提示「听不清」 | HA 专设 `stt-no-text-recognized`；本仓 `ASRResult.no_speech` 判别位同理 |
| 10 | **打断语义靠各 processor 自觉实现** | 漏一处即「打断后仍播完旧音频」 | Pipecat 用帧类型系统固化；其文档亦警示终止帧方向推反会导致收尾被抢跑 |
| 11 | **选型只看「能不能跑」，不看部署形态与传递依赖** | 落地后发现体积/显存/网络假设不成立，链路要重做 | 本次实测：「轻量本地 ONNX」普遍还要外挂文本前端（espeak-ng）与自己的权重体积；在线引擎依赖上游私有协议（edge-tts 的 `WSS + TrustedClientToken + Sec-MS-GEC`）**上游一改即失效**；GPU 档（ChatTTS / XTTS）显存需求另计 |
| 12 | **以为「同名的包就是同一个东西」** | 版本/档位口径对不上，容量预算失准 | 本仓记 KittenTTS mini-0.8=78MB，官方 "under 25MB" 指 nano 档(15M)；PyPI `kittentts` 是第三方实现 |

---

## 7. 对本项目的设计建议

目标：**同一套接口同时承载云端引擎（edge-tts）与本地引擎（faster-whisper / Piper / KittenTTS），
替换引擎不改调用点。**

### 7.1 模块分层（四层，依赖单向向下）

```
L4 调用点   app/api/routes/*, app/*/orchestrator.py   只认接口，不认引擎
L3 解析层   app/audio/registry.py  resolve(kind, settings) -> Resolution(client, provider, degraded)
L2 契约层   app/audio/base.py  ASRClient / TTSClient(ABC) + ASRResult / TTSResult dataclass
L1 引擎     asr.py(whisper) · tts.py(edge) · tts_local.py(kitten) · tts_piper.py · asr_sherpa.py
L0 资源     ffmpeg→16k wav · 模型目录 · 磁盘 TTS 缓存 · 信号量
```

契约层已有 `synthesize()`/`is_available()`/`ensure_ready()`/`unload()`，建议只加两项：
① `capabilities() -> frozenset[str]`（如 `{"word_timestamps","streaming"}`），供上层**能力协商**
替代 isinstance；② 把 `synthesize` 返回从裸 `bytes` 升为
`TTSResult{audio_bytes, sample_rate, channels, container, media_type}`——**容器元数据必须由引擎自己
声明**，这是反模式 4 的根治点。L1 每个引擎模块**自注册** `register(ProviderSpec(...))`，由
`app/audio/providers.py` 一次性 import；新增 Piper 只需「一个新文件 + providers 一行 import」。

### 7.2 统一接口抽象与选择语义

保留 `resolve()` 三档：`auto` 按 `priority` 升序探测取首个可用且**降级留痕**（`degraded`/`notes` 进
`/readyz` 与管理端）；显式 provider 不可用 → `ProviderUnavailable` → 503 + 可读原因；未知名 → 告警 +
回退 `auto`（配置漂移不炸服务）。**ASR 需特殊化**：口语练习对词级时间戳与判别位有硬需求，应上
`FallbackASRClient(primary, fallback)` **组合器**而非平级候选（docs/29 §6 已设计），判定语义必须是
「**仅异常/超时降级；成功但空转写（`no_speech`）不降级**」——否则静音会被备用引擎的幻觉文本污染评分。

### 7.3 配置方式

单一配置源 `app/core/config.py`（pydantic-settings），**配置写 provider 名而非类名**：

| 配置项 | 语义 | 建议 |
|---|---|---|
| `tts_provider` | `auto \| edge \| kitten \| piper` | **合并现有 `tts_provider` 与 `reading_tts_provider`**（反模式 1 的根因） |
| `asr_provider` / `asr_model` / `asr_device` / `asr_compute_type` | 已有 | 补 `asr_provider=auto\|whisper\|sherpa` |
| `tts_cache_ttl_s` / `tts_cache_max_mb` | 已有（86400 / 512） | 键含 provider+引擎版本，目录按 provider 分 |
| `voice_models_dir` | 本地模型根目录 | 权重不入库；缺失时 `is_available=False` + 可读原因 |

配置只表达**意图**（要什么引擎、什么优先级），实例化细节归 `ProviderSpec.factory`。前端不感知
provider，仅按后端返回的 `media_type` / `sample_rate` 决定播放方式。

### 7.4 替换与扩展路径（成本递增）

1. **加云端 TTS**（Azure）：新增 `tts_azure.py` + 注册 spec，`tts_provider=azure` 可切；缺密钥时
   `is_available=(False,"key missing")`，调用点走 503 降级。
2. **加本地 TTS**（Piper / Kokoro 之类）：容器是 WAV、采样率与 edge 不同，必须让引擎**自报容器元数据**
   并让缓存按 provider 分目录——**这是唯一需要动 L2 契约的改动**，故建议提前把返回值结构化。
3. **加本地 ASR 降级**（sherpa-onnx 或更大 whisper）：用组合器而非平级候选；预热需「双引擎都预热或
   仅主」，`/readyz` 仅在全缺时 degraded（docs/29 §6）。
4. **未来上流式/打断**（跟读实时反馈）：届时直接借 Pipecat 的帧三分类语义，而非自造「打断标志位」；
   **当前 REST/批式链路不必引入帧模型**——过度设计成本高于收益。

**一句话原则：引擎身份的真相只有一个地方（registry），音频元数据的真相只有一个地方（引擎返回值），
provider 的真相只有一个地方（配置）。**

---

## 8. 参考资料

### 8.1 论文（均为 `/abs/` 页实检；venue 无法从 abs 页确认者从略）

| 论文 | 支撑的架构论断 | URL |
|---|---|---|
| Radford et al., *Robust Speech Recognition via Large-Scale Weak Supervision*, 2022（ICML 2023, PMLR v202） | 多任务 seq2seq 以**单一 token 序列**取代多阶段管线；680k 小时弱监督；30s 块 + 缓冲滑窗 | <https://arxiv.org/abs/2212.04356> |
| Bain et al., *WhisperX*, INTERSPEECH 2023 | VAD Cut&Merge 预分段 + 强制音素对齐；**说话人分离不在摘要内** | <https://arxiv.org/abs/2303.00747> |
| Silero VAD（项目文档，非论文） | 30ms 块 <1ms/单 CPU 线程，MIT；**无同行评议论文（未核实）** | <https://pypi.org/project/silero-vad/> |
| Tan et al., *A Survey on Neural Speech Synthesis*, 2021 | TTS 三段分解（text analysis / acoustic model / vocoder） | <https://arxiv.org/abs/2106.15561> |
| Hasanabadi, *An overview of text-to-speech systems and media applications*, 2023 | 同三段分解 + 主流模型对比 | <https://arxiv.org/abs/2310.14301> |
| Wang et al., *Neural Codec Language Models are Zero-Shot TTS Synthesizers*（VALL-E）, 2023 | TTS 作为**离散 codec code 上的条件语言模型**；3 秒未见说话人零样本克隆 | <https://arxiv.org/abs/2301.02111> |
| Du et al., *CosyVoice*, 2024 | 监督语义 token + LLM 生成 token + 条件 flow matching | <https://arxiv.org/abs/2407.05407> |
| Du et al., *CosyVoice 2*, 2024 | 取消 G2P 前端；FSQ tokenizer + 统一 LM + chunk-aware flow matching + 声码器；首包延迟公式 | <https://arxiv.org/abs/2412.10117> |
| Ji et al., *WavChat: A Survey of Spoken Dialogue Models*, 2024 | 口语对话按**级联 vs 端到端**两大范式分类；覆盖 streaming/duplex | <https://arxiv.org/abs/2411.13577> |
| Cui et al., *Recent Advances in Speech Language Models: A Survey*（ACL 2025 缩减版） | 点名 ASR+LLM+TTS 级联三大代价：模态转换信息损失、管线延迟、**跨阶段误差累积** | <https://arxiv.org/abs/2410.03751> |
| Gupta et al., *Direct Speech-to-Speech NMT: A Survey*, 2024 | 直接 S2ST 延迟更优，但**性能仍落后级联**（量化取舍） | <https://arxiv.org/abs/2411.14453> |
| He et al., *Streaming End-to-end Speech Recognition For Mobile Devices*, 2018 | RNN-T 流式实时解码，延迟与精度双优 | <https://arxiv.org/abs/1811.06621> |
| Ekstedt & Skantze, *How Much Does Prosody Help Turn-taking?*（VAP）, SIGDIAL 2022 最佳论文 | 用 VAP **增量**建模双方语音活动做端点/轮次预测，无需显式标注 | <https://arxiv.org/abs/2209.05161> |
| Inoue et al., *Real-time and Continuous Turn-taking Prediction Using VAP*, IWSDS 2024 | VAP 轮次预测可 **CPU 实时**运行且衰减极小 | <https://arxiv.org/abs/2401.04868> |
| Chen et al., *F5-TTS*, 2024 | flow matching + DiT，**取消 duration model/text encoder/音素对齐** | <https://arxiv.org/abs/2410.06885> |
| *Moonshine*, 2024 | 计算量随音频长度伸缩，**不做固定 30s padding** | <https://arxiv.org/abs/2410.15608> |
| Zhang et al., *WeNet*, 2021 | **动态 chunk 注意力**统一流式与非流式 + 两遍解码 | <https://arxiv.org/abs/2102.01547> |

### 8.2 项目与文档

- Whisper <https://pypi.org/project/openai-whisper/>｜faster-whisper <https://pypi.org/project/faster-whisper/>｜whisper.cpp <https://github.com/ggml-org/whisper.cpp>（[头文件契约](https://github.com/ggml-org/whisper.cpp/blob/master/include/whisper.h)）｜WhisperX <https://pypi.org/project/whisperx/>
- FunASR <https://pypi.org/project/funasr/>、<https://modelscope.github.io/FunASR/>｜sherpa-onnx <https://pypi.org/project/sherpa-onnx/>（[模型表](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/index.html)、[端点规则](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/csrc/endpoint.h)）
- Vosk [API](https://github.com/alphacep/vosk-api/blob/master/python/vosk/__init__.py)、[模型](https://alphacephei.com/vosk/models)｜Kaldi <https://kaldi-asr.org/doc/index.html>
- NeMo [ASR 推理](https://docs.nvidia.com/nemo/speech/latest/asr/inference.html)、[ASR API](https://github.com/NVIDIA-NeMo/Speech/blob/main/docs/source/asr/api.rst)｜Riva <https://docs.nvidia.com/deeplearning/riva/user-guide/docs/asr/asr-overview.html>｜Silero VAD <https://pypi.org/project/silero-vad/>
- edge-tts <https://pypi.org/project/edge-tts/>｜Azure 语音合成 <https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis>
- Piper <https://pypi.org/project/piper-tts/>（[`.onnx.json` 字段](https://docs.rs/piper1-rs/latest/piper1_rs/json_schemas/data_file/struct.ModelConfig.html)、[音素输入示例](https://github.com/thewh1teagle/piper-onnx/blob/main/examples/with_phonemes.py)）｜Kokoro <https://pypi.org/project/kokoro/>、[权重卡](https://huggingface.co/hexgrad/Kokoro-82M)｜KittenTTS <https://pypi.org/project/kittentts/>、[流水线图](https://pub.dev/packages/flutter_kitten_tts)
- Coqui TTS <https://pypi.org/project/TTS/>｜MeloTTS <https://pypi.org/pypi/meloTTS/json>｜ChatTTS <https://pypi.org/pypi/ChatTTS/json>｜F5-TTS <https://pypi.org/project/f5-tts/>｜espeak-ng [manpage](https://manpages.debian.org/unstable/espeak-ng-espeak/espeak.1.en.html)
- Pipecat [帧模型](https://docs.pipecat.ai/api-reference/server/frames/overview.md)、[STT](https://docs.pipecat.ai/pipecat/learn/speech-to-text.md)、[TTS](https://docs.pipecat.ai/pipecat/learn/text-to-speech.md)、[ServiceSwitcher](https://docs.pipecat.ai/api-reference/server/utilities/service-switchers/service-switcher.md)、[STTService](https://reference-server.pipecat.ai/en/latest/api/pipecat.services.stt_service.html)
- LiveKit [pipeline types](https://docs.livekit.io/agents/models/pipelines.md)、[turns](https://docs.livekit.io/agents/logic/turns.md)、[STT 参考](https://docs.livekit.io/reference/python/livekit/agents/stt/index.html)｜Vocode [how it works](https://docs.vocode.dev/open-source/how-it-works)、[conversation mechanics](https://docs.vocode.dev/open-source/conversation-mechanics)
- OpenAI Realtime 规范（经 Azure 文档核实）<https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/realtime-audio>｜Home Assistant Assist pipeline <https://developers.home-assistant.io/docs/voice/pipelines/>｜Wyoming 协议 <https://pypi.org/project/wyoming/>

---

<!--
落位说明：
- 所有 URL 均来自本次 web_search / web_fetch 实检；未核实项已在正文与表格内显式标注。
- 本文件由 `local/research/asr-tts-oss-survey.md`（个人过程稿）整理入 `docs/audit/` 供团队长期引用。
- 已知未核实清单：Kaldi「HCLG」字面命名；Riva 类级流水线抽象；Moonshine ONNX/CT2 支持；
  CosyVoice 的 HiFiGAN 声码器一说；GPT-SoVITS 的仓库；MeloTTS/KittenTTS 的上游归属；各商业服务条款。
-->
