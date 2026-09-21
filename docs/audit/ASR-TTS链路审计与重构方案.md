# ASR / TTS 链路审计与可插拔重构方案

> 定位：语音链路（ASR / TTS）的**现状审计 + 目标架构 + 落地记录**。
> 配套调研：`docs/audit/ASR-TTS链路架构调研-开源与论文.md`（8 个 ASR 项目 / 11 个 TTS 项目 /
> 6 个编排框架 / 17 篇论文的模块划分、数据流、接口约定、可插拔机制横向对比，含 10 条共性模式
> 与 12 条反模式）。
> 相关既有文档：`docs/44-TTS链路整改计划.md`（P0/P1 整改，本次是其**结构性收尾**）、
> `docs/28-开源语音音频能力借鉴落地计划.md` §3.2（sherpa-onnx 降级引擎，本次落地）、
> `docs/audit/语音链路现状与风险清单-V2.0.md`、`docs/46-英文小说阅读拷问报告.md`（B-3/B-7/M-10）。

---

## 0. TL;DR

重构前语音链路的病根**不是缺功能，而是同一个真相有三份**：

| 真相 | 重构前的散落处 | 后果 |
|---|---|---|
| 「有哪些引擎」 | `base.get_tts_client`（edge\|azure）、`reading/tts_client`（auto\|edge\|kitten）两套 | 加第三个引擎必漏改一处 |
| 「这个实例是谁」 | `isinstance(tts, KittenTTSClient)` 反推 | 漏判即把缓存目录/扩展名/Content-Type 一起带错 |
| 「音频是什么容器」 | `save_tts_audio_bytes` 硬编码 `.mp3`、`mp3_duration_seconds` 只认 MP3、`/tts` 只回 hex | 本地 WAV 引擎被当 MP3 播坏、热路径 duration 恒为 `None` |

本次重构把这三点各自收敛到**一处**：`app/audio/registry.py`（引擎真相）、
`TTSClient.provider_id`（实例真相）、`TTSClient.media_type/ext` + `app/audio/duration.py`（容器真相），
并补齐本地 ASR（sherpa-onnx）与本地 TTS（KittenTTS 复用 + OmniVoice 参考件音色）两条本地路径。

**调用点零改动即可换引擎**：新增引擎 = 新写一个模块 + 模块末 `register(ProviderSpec(...))` +
在 `app/audio/providers.py` 的 `_MODULES` 加一行。

---

## 1. 调研结论（摘要）

完整报告见 `docs/audit/ASR-TTS链路架构调研-开源与论文.md`。对本次重构直接起作用的五条：

1. **引擎注册表 + 声明式 spec + 按配置解析**是跨项目反复出现的收敛点：Wyoming 协议用
   `describe→info` 运行时能力清单、Home Assistant Assist 用「引擎实体 + pipeline 绑定 +
   具名错误码」、LiveKit 用 `livekit-plugins-<provider>` 独立包 + `update_options()` 热插拔。
   → 对应本仓 `ProviderSpec` + `resolve()`。
2. **能力探测必须先行**（`is_available()` / Wyoming `installed` / LiveKit `STTCapabilities`），
   而不是「先调用再看异常」——否则不可用引擎会在用户脸上变成 500。
   → 对应本仓 `is_available()` 与 `strict` 语义。
3. **统一中间表示 dataclass**（NeMo `Hypothesis`、Pipecat `Frame`）⇔ 本仓既有
   `ASRResult{text, segments, words, duration, no_speech}` —— 这部分重构前已达标，本次不动。
4. **容器元数据必须由引擎自己声明**。Kokoro 逐段暴露 `(graphemes, phonemes, audio)`、
   Piper 用同名 `.onnx.json` 声明 `audio`/`phoneme_id_map`、Azure 用
   `set_speech_synthesis_output_format(...)`：**没有一家让调用方猜容器**。
   → 这是本仓「WAV 被标 `audio/mpeg`」的根治点。
5. **本地引擎选型要看依赖链**：轻量本地 ONNX 引擎常把文本前端外包给 `espeak-ng`
   （Piper/KittenTTS/Kokoro 的英文 G2P 都依赖它）。选型时把**这一层传递依赖**一并算进
   部署体积与可移植性，本项目因此**不引入 Piper**（与既有本地引擎能力重叠，
   且要额外背一套模型/音色管理）。

> 与本方案的偏差说明：调研建议把 `TTSClient.synthesize()` 的返回从裸 `bytes` 升级为
> `TTSResult{audio_bytes, sample_rate, channels, media_type}`。本次采用**等价但破坏面更小**的做法——
> 把容器元数据放在**引擎类属性**（`provider_id` / `media_type` / `ext`）上，并在**对外 API**
> （`/api/v1/tts`）的 `TTSResult` 里补 `media_type` / `provider`。理由：`synthesize()` 有 5 个调用点
> 与 6 个测试替身，改返回值形态是纯机械改动却会污染 diff；而「引擎声明容器」这一不变量已经拿到。
> 未来若需要 `sample_rate`/`channels`（例如前端做 PCM 拼接），再按调研建议升级即可——
> 升级点已经收敛在 `app/audio/base.py` 一处。

---

## 2. 现状审计：与 ASR / TTS 相关的零散代码

范围：`services/python/app/**`（后端全部）、`apps/web/src/**`（前端音频侧）、
`scripts/**`（健康检查与 POC）。

### 2.1 逐文件职责与问题

| # | 位置 | 重构前职责 | 问题（证据） |
|---|---|---|---|
| 1 | `app/audio/base.py` | 抽象接口 **+ 三个工厂函数** | 接口与装配同文件；TTS 工厂只认 `edge\|azure`，与 #5 的 `auto\|edge\|kitten` **枚举都不一致**；ASR 无 provider 概念（硬编码 whisper） |
| 2 | `app/audio/asr.py` | faster-whisper 引擎 | 预热方法叫 `warm()` 而 TTS 叫 `ensure_ready()` → **只有鸭子类型**，`main.py` 直接 `client.warm`；换成没有 `warm` 的引擎会静默不预热 |
| 3 | `app/audio/tts.py` | edge-tts 引擎 **+ 缓存 + 键 + TTL + 裁剪 + 预热**（334 行） | 引擎与缓存基础设施混在一个模块；缓存路径硬编码 `cache/tts/<key>.tts.mp3`（**不按 provider 分目录、扩展名写死 mp3**） |
| 4 | `app/audio/tts_local.py` | KittenTTS 本地引擎 | 只有读书域可达；引擎身份无法自报 → 只能被 `isinstance` 识别 |
| 5 | `app/reading/tts_client.py` | **第二套** provider 选择（`auto\|edge\|kitten`） | 与 #1 重复；`app/reading/tts_cache.py` 里还有 `provider_format()`（provider→扩展名/媒体类型）——**引擎元数据放在读书域，分层倒置** |
| 6 | `app/reading/tts_cache.py` | **第二套**缓存（按 provider 分目录） | 与 #3 重复；两套只有一套是对的（#6 对、#3 错），于是「练习热路径 + `/tts`」用错的那套 |
| 7 | `app/api/routes/reading_tts.py` | 听书路由 | `_provider_of()` 用 `isinstance(tts, KittenTTSClient)` 反推 provider；新增引擎必漏判 |
| 8 | `app/api/routes/reading.py:list_voices` | 音色目录 | 硬编码 5 个 edge 音色 + 路由层直接 `import KittenTTSClient` 探测；加本地音色要改路由 |
| 9 | `app/practice/orchestrator.py` | 回合热路径合成/落盘/时长 | `save_tts_audio_bytes` 扩展名写死 `.mp3`；`_tts_url_from_bytes` 只调 `mp3_duration_seconds`；provider 取自 `settings.tts_provider`（**可能不是实际客户端**） |
| 10 | `app/api/routes/audio.py:/tts` | 裸端点 | `TTSResult` 只回 hex，**无容器信息** → 消费方只能一律按 mp3 猜 |
| 11 | `app/audio/warmup.py` | 预合成预热 | 只预热「按 `settings.tts_provider` 解析出的客户端」，本地引擎在听书域被选中时预热不到 |
| 12 | `app/main.py:_prewarm_asr` | ASR 预热 | 直接调 `client.warm`（非接口方法，见 #2） |
| 13 | `app/core/config.py` | 配置 | `tts_provider`（edge\|azure）与 `reading_tts_provider`（auto\|edge\|kitten）**两套枚举**；无 `asr_provider`；`voice_models_dir` 是单引擎专用语义 |
| 14 | `apps/web/src/composables/useChapterTts.ts`、`useReaderTts.ts`、`MobileTtsBar.vue` 等 | 默认音色 `'en-US-JennyNeural'` 硬编码在各处 | 换默认音色要改 N 处；前端也不知道后端实际 provider |

### 2.2 四类耦合点（本次重构的靶子）

1. **装配与接口耦合**：工厂函数与 ABC 同文件、工厂里写 `if provider == "azure"` 分支树。
2. **身份靠类型反推**：`isinstance` 判引擎 → 与「加一个引擎」天然冲突。
3. **容器假设泄漏到调用点**：`.mp3` / `audio/mpeg` 出现在落盘、时长估算、路由响应三处。
4. **领域边界倒置**：读书域持有「provider → 容器」表与「provider 选择链」，而这两件事对
   练习域同样成立 → 只能复制。

### 2.3 重复部分清单（已删除）

| 重复项 | 处置 |
|---|---|
| `app/reading/tts_client.py`（第二套选择链） | **删除**，统一到 `app/audio/base.py:get_tts_client(provider, strict=)` → `registry.resolve()` |
| `app/reading/tts_cache.py`（第二套缓存 + `provider_format`） | **删除**，统一到 `app/audio/tts_cache.py`；`provider_format` 上收为 `registry.tts_format()` |
| `app/audio/tts.py` 内的缓存段（键/TTL/裁剪/预热） | **移出**到 `app/audio/tts_cache.py`；时长估算移出到 `app/audio/duration.py` |
| `list_edge_voices()`（路由内音色硬编码） | **移出**到 `app/audio/voices.py` |
| `_provider_of()`（isinstance 反推） | **删除**，改用 `TTSClient.provider_id` |

---

## 3. 目标分层

```
L4 调用点   app/api/routes/*           只认接口 + 领域模型，不认引擎
            app/practice/orchestrator.py
            app/reading/orchestrator.py
                  │  get_tts_client(provider, strict=) / get_asr_client(...)
                  ▼
L3 装配层   app/audio/base.py      依赖注入入口（FastAPI Depends 用）
            app/audio/providers.py 内置引擎一次性导入（import = 注册）
            app/audio/registry.py  ProviderSpec / resolve() / auto 链 / ProviderUnavailable
                  │
                  ▼
L2 契约层   app/audio/base.py      ASRClient / TTSClient(ABC)
                                   + provider_id / media_type / ext / is_local（类属性）
                                   + is_available() / ensure_ready() / unload()
                                   ASRResult / TTSResult / ScoreResult dataclass
                  │
                  ▼
L1 引擎     asr.py(whisper) · asr_sherpa.py(sherpa-onnx) · stubs.py(fake)
            tts.py(edge/azure) · tts_local.py(kitten) · tts_omnivoice.py(omnivoice)
                  │
                  ▼
L0 资源     app/audio/ffmpeg_utils.py（转码/时长探测）
            app/audio/duration.py（容器时长纯函数）
            app/audio/tts_cache.py（磁盘缓存：键/TTL/裁剪/预热）
            app/audio/voices.py（音色目录）
            app/audio/textproc/*（引擎无关文本前端：归一化/切句/长句收敛）
            app/audio/upload.py（容器嗅探/媒体类型）
```

**依赖单向向下**，且 L1 不 import L3/L4；L2 不知道任何具体引擎（`base.get_*_client` 内的
import 是**函数体内延迟导入**，保证模块导入期无环）。

---

## 4. 统一接口抽象

### 4.1 引擎身份（新增，替代 `isinstance`）

```python
class TTSClient(abc.ABC):
    provider_id: ClassVar[str] = "unknown"   # edge | azure | kitten | omnivoice | fake
    media_type:  ClassVar[str] = "audio/mpeg"  # 实际输出容器
    ext:         ClassVar[str] = "mp3"
    is_local:    ClassVar[bool] = False
    langs:       ClassVar[tuple[str, ...]] = ("en",)
```

`ASRClient` 同款（`provider_id` / `is_local` / `langs`），并把生命周期与 TTS 对齐：

```python
def is_available(self) -> tuple[bool, str]   # 探测先行，默认 (True, "")
def ensure_ready(self) -> None               # 预热（阻塞，调用方负责进线程），默认 no-op
def unload(self) -> None                     # 释放，幂等，默认 no-op
```

> `FasterWhisperClient.warm()` 保留为 `ensure_ready()` 的兼容别名，但 `main.py` 已改调
> `ensure_ready()`——旧名字不再是链路唯一入口。

### 4.2 `TTSResult`（对外契约，纯增量）

```python
@dataclass
class TTSResult:
    audio_bytes: str   # hex
    length: int
    media_type: str = "audio/mpeg"   # ← 新增：消费方不再一律按 mp3 猜
    provider: str = "edge"           # ← 新增：实际合成引擎
```

`/api/v1/tts` 的 `provider` 取自 **`tts.provider_id`（实际客户端）**，不再读
`settings.tts_provider`——配置写 `auto`/降级时，读配置会让缓存键与响应头撒谎。

---

## 5. 可插拔机制

### 5.1 声明式 spec

```python
# app/audio/asr.py 末尾
register(ProviderSpec(
    name="whisper", kind=ASR, label="faster-whisper（本地 · small/int8/CPU）",
    factory=lambda s: FasterWhisperClient(s.asr_model, s.asr_device, s.asr_compute_type),
    priority=10, is_local=True, aliases=("faster-whisper", "faster_whisper"),
))
```

字段语义：

| 字段 | 作用 |
|---|---|
| `name` / `aliases` | 配置里可写的名字（别名不进 auto 链，避免同引擎出现两次） |
| `factory(settings)` | **只构造，不判断可用性**（判断交给 `is_available()`） |
| `priority` | `auto` 链顺序，小者优先 |
| `is_local` | 本机推理（运维面板/健康检查分组） |
| `ext` / `media_type` | 输出容器（TTS；缓存目录与 Content-Type 从它派生） |
| `strict_when_explicit` | 显式选中但不可用时是否直接抛错 |
| `in_auto_chain` | 是否参与 `auto`（**Fake 置 False**：生产的自动选择绝不允许落到打桩引擎） |

### 5.2 选择与降级语义

`resolve(kind, settings, requested, strict=?)`：

| 配置值 | 行为 |
|---|---|
| `auto` | 按 `priority` 逐个 `is_available()`，取第一个可用；**降级留痕**（`Resolution.degraded` / `notes`）；全不可用 → `ProviderUnavailable` |
| 具体名字 | 直接构造返回；`strict=True`（或该 spec 声明 `strict_when_explicit`）且不可用 → `ProviderUnavailable` |
| 未知名 | 告警 + 回退 `auto`（配置漂移不炸服务，docs/46 B-7） |

调用侧策略：

- **听书域**：`APP_READING_TTS_PROVIDER` 非空 → `strict=True`，不可用即 503
  （**绝不静默换云引擎**——用户以为在用本地音色却听到 edge 是最坏的失败模式）；
- **`/api/v1/tts`**：非 strict，先 `is_available()` 再合成，不可用 503（原有语义）；
- **`azure`**：`AzureNotWiredClient` 显式 `is_available()==(False, 原因)`（docs/44 P0-C 语义不变）。

### 5.3 现有引擎清单（`registry.registered()`）

| kind | name | 本地 | priority | 容器 | 说明 |
|---|---|---|---|---|---|
| asr | `whisper`（别名 faster-whisper） | ✅ | 10 | — | 主 ASR；词级时间戳/`no_speech` |
| asr | `sherpa`（别名 sherpa-onnx） | ✅ | 20 | — | 轻量降级；**无词级时间戳**（见 §7.1） |
| asr | `fake` | ✅ | 999 | — | **不进 auto 链** |
| tts | `omnivoice`（别名 omnivoice-sidecar） | ✅ | 10 | wav | auto 链首位：参考件零样本克隆（英语音色来源，见 §7.2） |
| tts | `kitten`（别名 kittentts） | ✅ | 20 | wav | KittenTTS mini，8 个英文音色 |
| tts | `edge` | ❌ | 30 | mp3 | 云端兜底（默认档，本地不可用时使用） |
| tts | `azure` | ❌ | 90 | mp3 | 未接线占位（显式 `is_available=False`） |
| tts | `fake` | ✅ | 999 | mp3 | **不进 auto 链** |

---

## 6. 配置方式

配置只表达**意图**（要哪个引擎），实例化细节归 `ProviderSpec.factory`。全部经
`app/core/config.py`（`.env` 前缀 `APP_`）。

### 6.1 新增/变更

| 配置项 | 默认 | 语义 |
|---|---|---|
| `APP_ASR_PROVIDER` | `auto` | `auto \| whisper \| sherpa` |
| `APP_ASR_SHERPA_MODEL_DIR` | 空 | sherpa 模型目录；**空 = 不探测该引擎** |
| `APP_ASR_SHERPA_MODEL_TYPE` | `sense_voice` | `transducer \| sense_voice \| paraformer \| whisper` |
| `APP_ASR_SHERPA_NUM_THREADS` | `2` | onnxruntime 线程数 |
| `APP_TTS_PROVIDER` | `auto` | `auto \| omnivoice \| kitten \| edge \| azure`（`auto` 链本地优先，见 §5.3/§7.3） |
| `APP_KITTEN_VOICE` | `Jasper` | KittenTTS 默认音色 |
| `APP_TTS_OMNIVOICE_ENDPOINT` | `http://127.0.0.1:8765` | 本地 OmniVoice 边车地址 |
| `APP_TTS_OMNIVOICE_VOICE` | `anchor-en` | `anchor-en`（英文男声）/ `podcaster-en`（英文女声） |
| `APP_TTS_OMNIVOICE_SEED` | 空 | 空 = 用 `VOICES.json` 里的 seed |
| `APP_TTS_OMNIVOICE_TIMEOUT_S` | `120` | GPU 冷合成可达 10s+，给足余量 |
| `APP_VOICE_REFS_DIR` | 空 | 音色参考件目录；**空 = 自动用仓库内 `data/seed/voices`**（随仓库分发，零配置可用） |
| `APP_READING_TTS_PROVIDER` | `auto` | **空 = 跟随 `APP_TTS_PROVIDER`**；非空 = 读书域覆盖 |

> `APP_TTS_PROVIDER` 与 `APP_READING_TTS_PROVIDER` **保留两个键但共用一套机制与同一枚举**
> ——前者是全局默认，后者是读书域覆盖。反模式 1 的病根是「两套实现 + 两套枚举」，
> 不是「两个默认值」。

### 6.2 常见组合

```dotenv
# ① 默认（推荐）：本地优先，不具备条件时自动回落 edge —— 无需任何配置
# ② 强制走本地克隆音色（缺条件时 503，而不是悄悄用云端）
APP_TTS_PROVIDER=omnivoice
APP_VOICE_REFS_DIR=<xiaohaishi>/apps/server/assets/voices
# ③ 强制走云端（本地引擎有问题时的排障开关）
APP_TTS_PROVIDER=edge
# ④ ASR 增加本地轻量降级
APP_ASR_PROVIDER=auto
APP_ASR_SHERPA_MODEL_DIR=<sherpa sense-voice 模型目录>
```

---

## 7. 本地 ASR / 本地 TTS

### 7.1 本地 ASR：faster-whisper（主）+ sherpa-onnx（轻量）

- **faster-whisper**（原有，MIT）是默认本地引擎：整段解码、`word_timestamps=True`、
  `vad_filter=True`、`condition_on_previous_text=False`（抑制幻觉），并发信号量 2，
  300s 墙钟超时。
- **sherpa-onnx**（新增，Apache-2.0，docs/28 §3.2 P0-B）：`app/audio/asr_sherpa.py`，
  onnxruntime 后端、模型目录按 `model_type` 校验必需文件、可选依赖（`uv sync --extra local-asr`）。
  **能力边界诚实声明**：不产出词级时间戳 → `ASRResult.words == []` → 流利度 wpm/停顿特征为空；
  下游既有「无时间戳 → `wpm=None`」的降级路径（`tests/test_shadow.py` 已覆盖），不会报错。
- 二者用 `APP_ASR_PROVIDER=auto` 组成**平级候选链**（whisper 优先）。若后续需要
  「主引擎异常时降级、但成功空转写不降级」的组合器语义（调研建议 §7.2），在
  `registry.resolve` 之上加 `FallbackASRClient(primary, fallback)` 即可，无需动调用点。

### 7.2 本地 TTS：KittenTTS + OmniVoice 参考件音色

**KittenTTS**（原有，Apache-2.0 权重）：`tts_local.py`，24kHz mono WAV，8 个英文音色。
其英文 G2P 依赖 `espeak-ng`（文本前端外包），部署时把这一层传递依赖一并算进体积。

**OmniVoice 参考件音色**（新增，`app/audio/tts_omnivoice.py`）——复用参考项目
`F:\WorkingL\HainnuP\xiaohaishi` 的**英语两把嗓子**：

| voice id | 参考件 | 口碑名 | 特点 |
|---|---|---|---|
| `anchor-en`（默认） | `male-en.wav`（354,318 B） | The Anchor | 美音中年男 |
| `podcaster-en` | `female-en.wav`（389,838 B） | The Podcaster | 澳音年轻女 |

关键契约（照抄上游的纪律，**每条都有代价**）：

1. **音色不是 id，而是「参考件 wav 字节 + 参考文本 + seed」**。参考件按 **sha256 校验**后才使用：
   字节就是嗓子的身份，参考件被改动必须**大声失败**（否则会静默换成另一把嗓子）；
2. **参考文本必须来自清单 `VOICES.json`，禁止自动转写**（ASR 模型漂移会让音色每天变）；
3. clone 模式**不下发 instruct**（上游对 clone+instruct 直接 400）；
4. **语速不走引擎**：`rate` 被忽略，倍速由前端 `playbackRate` 承担（与 KittenTTS 同口径）；
5. 合成走边车 `POST {endpoint}/synthesize`，body
   `{text, language, mode:"clone", ref:{audioBase64,text}, seed, format:"wav"}`；返回 24kHz WAV；
6. **可用性包含连通性**：`is_available()` 额外探测 `GET {endpoint}/health`（10s TTL 缓存），
   边车不在就让位给 kitten/edge —— 这是它能安全放在 `auto` 链首位的前提。

### 7.2.1 边车服务（`services/omnivoice-sidecar/`，本仓自带）

边车**不是**外部依赖，而是本仓的一个独立服务（纯标准库 `http.server`，无 fastapi/uvicorn）：
主服务是 CPU 运行时（要能在 CI/演示容器里起），OmniVoice 是 torch + GPU，两者只能走进程边界。
细节与运维口径见 `services/omnivoice-sidecar/README.md`；两条关键事实：

- **契约一致性由测试锁住**：`tests/test_omnivoice_sidecar.py` 用同一份请求体同时喂
  「客户端 `build_request()`」与「服务端 `validate()`」，两端漂移即红（无需 GPU）；
- **`--fake` 模式**：占位引擎只出可解析的静音 WAV，用于没有 GPU 的机器与 CI 冒烟整条链路。

**启用（三步，零代码改动）**：

```powershell
# 1) 下权重（约 3.28 GB，不入库）：默认走 hf-mirror.com 镜像下到 <仓库>/data/models
pwsh -File scripts/fetch-omnivoice-weights.ps1
#    本机已有缓存就别下了：-FromLocal <HF 缓存根>；只验链路：-Only "config.json"

# 2) 建独立环境装 omnivoice + torch + soundfile，并用 OMNIVOICE_PYTHON 指过来
#    （不装在 services/python/.venv —— 那是 CPU 运行时）

# 3) 起边车：一键启动**默认就带上它**（起不来只提示不阻塞）
pwsh -File scripts/dev-up.ps1 start        # 不想起加 -NoVoice
#    也可单独起：pwsh -File scripts/start-omnivoice-sidecar.ps1（无 GPU 加 -Fake）

# 音色参考件已随仓库分发在 data/seed/voices/，APP_VOICE_REFS_DIR 留空即自动指向它。
```

**权重查找顺序**（边车 / `dev-up.ps1` / 启动器三者一致）：`OMNIVOICE_MODEL_DIR` →
`OMNIVOICE_HF_CACHE` → **`<仓库>/data/models`**（fetch 脚本落点，下完即零配置）→ HF 默认缓存 →
仓库 id。判据含「快照需有 `config.json` + 至少一个 `*.safetensors`」——
**下载到一半的目录不会被当成可用权重**（否则表现成"边车起了但 loadError"）。

> 边车默认监听 `127.0.0.1:8765`（`APP_TTS_OMNIVOICE_ENDPOINT` 默认同值）。容器形态下
> `127.0.0.1` 指容器自己，需要边车时把该键指向宿主（如 `http://host.docker.internal:8765`）；
> 不指也能跑 —— 探测失败即回落 edge。

### 7.3 默认档位与回退

`APP_TTS_PROVIDER` 默认 `auto`，`auto` 链顺序 **omnivoice(10) → kitten(20) → edge(30) → azure(90)**：
本地引擎优先，任一环缺条件时 `is_available()` 返回可读原因并被跳过，自动回落到下一档，
**不阻塞任何链路**；显式写死引擎名则严格按该引擎（不可用 → 503，不静默换引擎）。

> **omnivoice 的可用性不只查配置**：它在链首，若只看「参考件目录配了没」，
> 就会出现「配了目录但边车没起 → 被选中 → 每次合成都失败」。故 `is_available()` 额外做
> `GET {endpoint}/health` 探测（结果按 **5s TTL 缓存**，避免每个请求打一次网络）；
> 边车不在即让位给 kitten/edge。
> ⚠️ 判据是响应体里的 **`ok == true`，不是 HTTP 200**：边车进程起来后模型还要加载约 **10s**，
> 这期间 `/health` 已返 200 但 `ok=false`（设计如此，好让调用方区分「没起」与「起了但还在加载」）。
> 只认 200 会让主服务在加载窗口内选中它 —— 真机实测边车日志里连着三条 `POST /synthesize 503`。
> 这两条已由 `tests/test_tts_omnivoice.py` 的用例锁住（边车在线 → 选 omnivoice；
> 边车离线 → 落 edge；**200 但 ok=false → 落 edge**）。

权重**不入库**（红线：模型权重，约 3.3 GB），只做运行时路径引用；
**参考件入库**（`data/seed/voices/`，约 1.9 MB，`.gitignore` 开了窄豁免）—— 音色 = 参考件字节
+ 参考文本 + seed，参考件就是音色身份本体，不入库则队友 clone 下来边车合成不出任何声音。

---

## 8. 替换与扩展路径

### 8.1 新增一个引擎（三步）

1. 新建 `app/audio/<engine>.py`，实现 `ASRClient` / `TTSClient` 子类，声明
   `provider_id` / `media_type` / `ext` / `is_local`，实现 `is_available()`（返回**可读原因**）
   与 `ensure_ready()`；
2. 同文件末尾 `register(ProviderSpec(name=..., kind=..., factory=..., priority=..., ext=..., media_type=...))`；
3. 把模块名加进 `app/audio/providers.py` 的 `_MODULES`。

**调用点零改动**。若要让用户可选到它的音色，在 `app/audio/voices.py` 加一个
`_<engine>_voices(settings)` 聚合函数（参考 `_kitten_voices` / `_omnivoice_voices`）。

### 8.2 成本递增的替换场景

| 场景 | 改动面 | 备注 |
|---|---|---|
| 换/加云端 TTS | 新引擎模块 + spec（~80 行） | 缺密钥时 `is_available=False` → 503 降级 |
| 换/加本地 TTS（新容器） | 同上；容器经 `ext`/`media_type` 自动贯通缓存/落盘/响应 | 无需再改 `save_tts_audio_bytes` / `/tts` |
| 换 ASR | 新引擎模块 + spec | 若新引擎无词级时间戳，流利度特征自动降级为 `None` |
| 开启引擎降级链 | `APP_*_PROVIDER=auto` | 降级留痕在 `Resolution.notes` |
| 上流式/打断 | 需引入帧模型（借 Pipecat 的数据/控制/系统三分类） | **当前 REST/批式链路不必做**——过度设计成本高于收益 |

---

## 9. 本次实施记录

### 9.1 新增文件

| 文件 | 职责 |
|---|---|
| `app/audio/registry.py` | ProviderSpec / register / catalog / auto_chain / resolve / tts_format / health_summary |
| `app/audio/providers.py` | 内置引擎一次性导入（import = 注册） |
| `app/audio/tts_cache.py` | 全站唯一 TTS 缓存出入口（键含 provider+引擎版本；按 provider 分目录） |
| `app/audio/duration.py` | 容器时长纯函数（MP3 帧头 / WAV RIFF 头 / 按容器分派） |
| `app/audio/voices.py` | 音色目录单一真源（`DEFAULT_VOICE` + edge 清单 + 本地引擎聚合） |
| `app/audio/asr_sherpa.py` | sherpa-onnx 本地 ASR 引擎 |
| `app/audio/tts_omnivoice.py` | 参考件零样本克隆引擎（英语音色来源，含 sha256 校验、边车 health 探测、`build_request()` 契约出口） |
| `services/omnivoice-sidecar/server.py` | **本地 GPU 合成边车**（纯标准库 `http.server`；`--fake` 支持无 GPU 冒烟） |
| `services/omnivoice-sidecar/README.md` | 边车运维口径（依赖、权重、契约、设计取舍、验收） |
| `scripts/start-omnivoice-sidecar.ps1` | 边车启动器（依赖自检 + 端口占用探测 + 权重探测） |
| `data/seed/voices/` | 音色参考件（`VOICES.json` + 4 个 wav，约 1.9 MB，随仓库分发） |
| `tests/test_omnivoice_sidecar.py` | 边车校验逻辑 + **客户端↔服务端契约对账**（无需 GPU） |

### 9.2 修改（要点）

- `app/audio/base.py`：接口加身份/生命周期类属性与 `ensure_ready/unload`；
  `get_asr_client()` / `get_tts_client(provider=None, *, strict=False)` 改为注册表解析；
  `TTSResult` 增 `media_type` / `provider`。
- `app/audio/asr.py`：`provider_id="whisper"`、`is_available`、`ensure_ready`（`warm` 留别名）、`unload`、注册 spec。
- `app/audio/tts.py`：**瘦身**为纯引擎（edge/azure）+ 注册 spec；缓存与时长移出。
- `app/audio/tts_local.py` / `stubs.py`：声明身份 + 注册 spec（`FakeTTSClient(provider=...)` 让打桩也带真实 provider 维度）。
- `app/audio/warmup.py`：预热走统一缓存模块。
- `app/practice/orchestrator.py`：`save_tts_audio_bytes` 扩展名按**魔数嗅探**；
  `_tts_url_from_bytes` 用 `audio_duration_seconds`（容器自适应）；provider 由客户端自报。
- `app/api/routes/audio.py`：`/tts` 走统一缓存；响应带 `media_type` / `provider`。
- `app/api/routes/reading_tts.py`：删 `_provider_of`（isinstance）→ `provider_of(client)`；
  `ProviderUnavailable` → 503；缓存走统一出入口。
- `app/api/routes/reading.py`：`list_voices` 改为读 `app/audio/voices.py`。
- `app/reading/orchestrator.py`：批量预合成走统一缓存。
- `app/main.py`：`_prewarm_asr` 调 `ensure_ready()`。
- `app/core/config.py`：见 §6.1。

### 9.3 删除

- `app/reading/tts_client.py`、`app/reading/tts_cache.py`（两套重复实现）。

### 9.4 契约影响

- **OpenAPI 变更**：`TTSResult` 增 `media_type` / `provider` 两个**带默认值的可选字段**
  → 快照 `apps/web/src/api/specs/python-openapi.json` 与生成类型
  `apps/web/src/api/generated/python-api.d.ts` 已同步刷新（CI 有零 diff 门禁）。
- **无破坏性变更**：既有消费方可忽略新字段；`/api/v1/reading/voices` 响应形状不变
  （`id/label/engine/langs` 完全一致，仅数据来源改变）。

---

## 10. 验证与门禁

### 10.1 新增/更新的测试

| 测试 | 覆盖 |
|---|---|
| `tests/test_audio_registry.py`（新） | spec 注册/别名/auto 链顺序/Fake 不进 auto/显式 strict 抛错/未知名回退/`tts_format` 兜底 |
| `tests/test_tts_omnivoice.py`（新） | 清单解析/sha256 校验失败即拒（**静默换嗓子守卫**）/clone 请求体不含 instruct/is_available 可读原因 |
| `tests/test_asr_sherpa.py`（新） | 模型文件缺失清单/未装依赖时的可读原因/`is_available` 不抛 |
| `tests/test_audio_voices.py`（新） | edge 清单稳定/本地引擎未就绪不暴露/去重 |
| `tests/test_tts_cache.py`（改） | 全部改用 `app.audio.tts_cache`；新增「按 provider 分目录」「provider 源自客户端」 |
| `tests/test_audio_chunk_duration.py`（改） | 新增 WAV 时长、按容器分派、**WAV 引擎热路径 duration 非 None** |
| `tests/test_tts_client.py` / `test_reading_tts.py` | 适配新工厂签名，断言语义不变 |

### 10.2 门禁

```powershell
# Python（services/python）
uv run ruff check . && uv run ruff format --check .
uv run pytest -q -m "not gpu"

# 契约快照对账（CI 同款）
uv run python -c "import json;from pathlib import Path;from app.main import app;snap=json.loads(Path('../../apps/web/src/api/specs/python-openapi.json').read_text(encoding='utf-8'));assert snap==app.openapi(),'契约快照需刷新'"

# 前端（apps/web）
pnpm gen:api && git diff --exit-code -- src/api/generated/
pnpm lint && pnpm typecheck && pnpm test:run && pnpm build
```

> **本地环境注记（非仓库问题）**：本机 DSH 沙箱下**以 mode 0o700 创建的目录创建后即不可访问**，
> 而 `tempfile.mkdtemp`（pytest `tmp_path` 与 pytest 缓存原子写都用它）正是 0o700 →
> 测试会成片 `PermissionError`。临时绕法：
> `$env:PYTHONPATH='<repo>\local\pytestfix'; uv run pytest -p sandbox_tmpfix -p no:cacheprovider`。
> CI（ubuntu）无此策略。同类现象：`ruff format --check .` 遍历到不可访问目录时会 panic，
> 本地可改用 `ruff format --check app tests`；受限沙箱下 `pnpm test:run`/`pnpm build` 会因
> esbuild 子进程 `spawn EPERM` 而失败，需在无管道限制的环境执行。

### 10.3 本次实测结果

| 门禁 | 结果 |
|---|---|
| `ruff check .` / `ruff format --check app tests` | 全绿 / 220 文件已格式化 |
| `pytest -q -m "not gpu"` | **726 passed, 4 skipped**（4 skipped = 需 Docker 的 PG/Redis 集成测试） |
| `pipeline_bench.py --fake --runs 3 --check-budget` | 通过（各阶段均在预算内） |
| `check_single_writer.py` / `check_feature_flags.py` | ok / 12 项全 ok |
| 契约快照 == `app.openapi()` | True |
| `pnpm lint` / `pnpm typecheck` | 通过 |
| `pnpm test:run` | **295 passed（50 files）** |
| `pnpm build` / `check-bundle.mjs` | 成功 / 通过 |

---

## 11. 残余风险与未决项

| 项 | 等级 | 说明 / 建议 |
|---|---|---|
| edge-tts 上游协议稳定性 | 🟠 | 依赖 `WSS + TrustedClientToken + Sec-MS-GEC`，上游改协议即失效；Azure 备胎仍未接线（docs/44 P0-C）。本地引擎已就位，可作为其失效时的实际兜底 |
| sherpa-onnx 未产出词级时间戳 | 🟡 | 选它做 ASR 时流利度特征为空；若要词级时间戳需换模型或开 `enable_timestamps`（未验证） |
| ASR 降级组合器语义 | 🟡 | 当前是平级候选链；若启用需按「仅异常降级、空转写不降级」实现 `FallbackASRClient` |
| `/tts` 仍回 hex（未改 URL） | 🟡 | docs/44 P1-D 未做；本次只补了容器元数据。改 URL 是破坏性契约变更，需联调页 + 删除清单 |
| 前端默认音色双份 | 🟡 | `apps/web/src/audio/tts-config.ts` 与后端 `voices.py:DEFAULT_VOICE` 各一份（已有跨端一致性用例锁住）；彻底消灭需 `/reading/voices` 下发默认值（一次契约变更） |
| 本地边车未做端到端冒烟 | 🟡 | 本次以 `is_available()` 探测 + Fake 单测覆盖；真实边车链路需在具备 GPU 的机器上补一次冒烟 |
