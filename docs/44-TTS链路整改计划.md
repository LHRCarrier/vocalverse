# docs/44- TTS 链路整改计划（对抗拷问产出 · 待评审稿）

> 依据：`local/grill-voice-tts.json`（9 项对抗拷问，P0×3 / P1×5 / P2×1）+ `docs/audit/语音链路现状与风险清单-V2.0.md`（K02 / R-04 / R-06 / R-07 / R-15 / TTS-01/02/08/09 / NR-5）。
> 定位：**TTS 优先**的整改执行计划。非 TTS 的语音/评分/前端问题不在本计划范围（见 §8 遗留项）。
> 原则：借鉴不拷代码。VS 本体 AGPL-3.0；只取**协议形状 / 算法模式**，算法依据上游 MIT（Patter `sentence_chunker`、voicebox `chunked_tts`），依赖走 MIT/Apache 库（`num2words`、`ffmpeg`、`azure-cognitiveservices-speech`）。

---

## 1. 总判（为什么要改）

我们 TTS 是「**单一在线 edge-tts + 零前处理 + 脆弱句切分 + 无缓存过期/无响度归一**」的单点结构。四类硬伤：

| 类 | 痛点 | 用户可感 | 等级 |
|---|---|---|---|
| 切分 | 缩写点/小数点当句号 → 错位停顿、半句被单独合成 | 是（听感明显） | P0 |
| 生命周期 | 单引擎、无 is_available/ensure_ready/unload；Azure 备胎零代码 | 是（edge-tts 一挂即整链静默） | P0 |
| 前处理 | 原文透传，无归一/发音词典/语速控制 | 是（数字/缩写读错） | P1 |
| 交付 | /tts 回 hex×2、与热路径 URL 机制不自洽；无响度归一 | 部分（体积/响度） | P1 |

---

## 2. 整改目标与不变量

- **TTS-first**：先做 0~3 期，4~5 期（表达/听读）后置。
- **可测不变量**：CI 不打真 TTS/Azure（无密钥/无网络）。凡逻辑改成**纯函数** + 依赖注入，用 `FakeTTSClient` 测。
- **契约警示**：改 `/tts` 返回形态是契约变更（当前 `Envelope[TTSResult]`，`TTSResult.audio_bytes: str(hex)`，base.py:36-40）→ 必须同步 `docs/21` 双快照对账 + 前端适配；涉及新前后端联动功能须按 `AGENTS.md` §3 提供联调测试页（dev-only，可删无影响）。
- **每次改动=独立 commit**，代码/测试/文档分开（`AGENTS.md` 提交纪律），门槛跑 `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`。

---

## 3. 优先级矩阵

| 优先级 | 主题 | grill id | Severity | 风险/成本 | 依赖 |
|---|---|---|---|---|---|
| 🥇 P0-A | 句切分缩写/小数点修复 | vtts-03 | P0 | 低/中 | 无 |
| 🥇 P0-B | 引擎生命周期 + 兜底 | vtts-01 | P0 | 中/中 | P4 的 provider 拆分 |
| 🥈 P0-C | Azure 接线（或删假配置） | vtts-02 | P0 | 中/高 | SDK、密钥、许可 |
| 🥉 P1-A | 文本归一化（数字/缩写/清洗） | vtts-05 | P1 | 低/中 | 无 |
| 🥉 P1-B | 缓存键扩容 + TTL | vtts-06 | P1 | 低/低 | P1-A 之后 |
| 🥉 P1-C | 拼接：缺句上报 + duration | vtts-04 | P1 | 低-中/中 | 无 |
| 🥉 P1-D | /tts 统一 URL + 响度归一 | vtts-07 | P1 | 低-中/中 | 契约、前端 |
| 🟡 P1-E | 语速/停顿/节奏（ssml-lite 子集） | vtts-08 | P1 | 中/中 | P1-A |
| ⚪ P2 | 听读逐词时间轴 | vtts-09 | P2 | 中/中 | P1-E 之后 |
| ⚪ 后置 | crossfade / m4b 章节目录 | vtts-04/07 | P1 | 高/高 | 见 §6（待评估） |

---

## 4. 分期执行清单（TTS 优先）

> 每项给出：目标 / 改什么 / 怎么做 / 验收（含修复前必失败测试）/ 风险回退 / 建议 PR。

### P0-A · vtts-03 句切分：缩写点 / 小数点 / 网址不再当句号（✅ 已实现）

- **目标**：`Mr.`、`St.`、`Dr.`、`U.S.`、`3.5`、`Ph.D`、`f(x)=2.` 不被拆成独立句子；长句不再被 300 字符硬切到词中间。
- **改什么（已解耦）**：新增纯模块 `services/python/app/audio/textproc/sentence_splitter.py`（**架构解耦**：把句切分从 1000+ 行 `app/practice/orchestrator.py` 抽出，engine-agnostic 纯逻辑，后续归一/发音/ssml 同归 `app/audio/textproc/`）；`orchestrator.py` 改为 import；`tests/test_stream_sentence.py` 改导入并加 8 例回归。
- **怎么做（借鉴自写）**：
  1. 把句界判定抽成**纯函数** `find_sentence_end(text) -> int`（便于单测；已实现于 `app/audio/textproc/sentence_splitter.py`，另导出 `StreamSentenceSplitter` / `MAX_SENTENCE_CHARS`）。
  2. 加**守卫**：`a-zA-Z.[a-zA-Z]`（`U.S.`）、缩写表（`Mr/St/Dr/Prof/Mrs/Ms/Inc/Ltd/vs/etc/e.g/i.e/…`，词前大写缩写 `cap` 守卫同 VS chunked_tts.py:35-39/216-243）、`数字.数字`（小数点）、网址 `.com/.net/…`、`[...]` 括号内不切。
  3. 超长句：优先按 **分句边界**（`;:,—`/破折号）切，回落 `rfind(' ')`，再回落**避开括号 tag 的硬切**（VS `_find_last_clause_boundary` / `_safe_hard_cut` 思路）；`_MAX_SENTENCE_CHARS` 300 保留为上限。
  4. 首版只需 en 数据（我们产品对话为英语），honorific 表放 `app/audio/`（或 `app/textproc/`）供后续扩展。
- **验收 / 回归（修复前必失败）**：`tests/test_stream_sentence.py` 新增 8 例（实现于 2026-09-07，17 passed + 全量 238 passed / 4 skipped + ruff 全绿）：`"Mr. Smith went to the store."` → 1 句；`"It's 3.5 miles away."` → 1 句；`"The U.S. economy grew."` → 1 句；`"Dr. Smith and Prof. Lee left."` → 1 句；`"I scored 98. Good."` → 2 句；当前实现的 `_SENTENCE_END_RE` 对这些**全部失败**。
- **风险/回退**：低。真 `TTSProbe` 无关，纯字符串逻辑。回归失败则回退到 no-op（不切=整段合成），保持正确性优先于细分。
- **建议 PR**：纯 Python + 测试，1 PR，`chore(test) + fix(tts)`。

### P0-B · vtts-01 引擎生命周期：is_available / ensure_ready / unload + provider 分派

- **目标**：TTS 不再是「静默单点」；至少能**提前探测 + 明确降级**。
- **改什么**：`services/python/app/audio/base.py:58-65`（`TTSClient`）`get_tts_client:116-124`；`services/python/app/audio/tts.py`；`core/config.py:54-57`。
- **怎么做（借鉴自写）**：
  1. `TTSClient` 增：`is_available() -> tuple[bool, str]`（默认 True+""）、`ensure_ready()`（默认 no-op）、`unload()`（默认 no-op）；`synthesize` 保持（backward compatible，所有子类/`FakeTTSClient` 无需改即兼容——都是默认实现）。
  2. `get_tts_client` 按 `settings.tts_provider` 分派：`edge`→`EdgeTTSClient`、`azure`→`AzureTTSClient`（P0-C 实现，未实现时报 `is_available=False`+安装/配置提示，与 VS `is_available` 三态一致）。
  3. `EdgeTTSClient`：加**超时 + 单发重试**（参考 VS `_retry_once_with_fresh_hf_client` 的"单发重试+明确失败"思想），超时/异常由 `_tts_url_from_bytes` 返回 `None` 并**打「该句无音频」日志**（不是静默）。
  4. `/api/v1/tts` 与对话热路径在调用前**先查 `is_available()`**，不可用返回可读错误而非 500。
- **验收**：`FakeTTSClient` 派生场景下：`is_available=False` → orchestration 返回可读错误/降级（非静默）；`get_tts_client` 在 `tts_provider="azure"` 且无实现时返回 `(False,"azure not wired")` 不崩溃。
- **风险/回退**：中。ABC 增加方法是**向后兼容**（默认实现），不改子类签名 → 低破坏；若动静大，先只加 `is_available` 不加 `ensure_ready/unload`。
- **建议 PR**：`feat(tts): lifecycle + provider dispatch`，含 `FakeTTSClient` 适配 + 测试。

### P0-C · vtts-02 Azure 接线（或删假配置兜底）

- **目标**：edge-tts 被限流/改协议时有一台备用引擎；或至少**把「Azure 备胎」的假承诺去掉**。
- **改什么**：`core/config.py:54-57`（provider/`azure_tts_key`）；`audio/base.py:116-124`；新增 `audio/tts_azure.py`。
- **怎么做（直接引库 + 借鉴自写）**：
  1. 引 `azure-cognitiveservices-speech`（开源，规避 edge-tts GPL/微软服务条款争议，`docs/audit:261`）。在 `audio/tts_azure.py` 实现 `AzureTTSClient(TTSClient)`：`is_available()` 检查 `azure_tts_key` + `region`；`synthesize` 用 `SpeechSynthesizer` 输出 bytes。
  2. `get_tts_client` 分支接 `azure`；`health.py:26` 的 `tts` 字段改为**真实探测** `is_available()` 而非回读配置。
  3. 若**短期不接**：删掉 `tts_provider='azure'`/`azure_tts_key` 假字段，把 `docs/06:117/251` 的「Azure 备胎」措辞坦白改成「预合成 mp3 保底」，别让风险表列一条**从不存在的缓解**。
- **验收**：`settings.tts_provider="azure"` 无密钥时 `is_available=(False,"key/region missing")`；接好密钥后 `synthesize` 返回非空 bytes（本地无密钥则跳过，CI 走 Fake）。**Leak 检查**：`azure_tts_key` 不得进日志/response（读 `docs/audit` 密钥安全红线）。
- **风险/回退**：高（需要密钥/许可/新依赖）。**建议本步放在 P0-A/P0-B 之后**；最低成本路径是「先删假配置 + 改文档措辞」，Azure 真接线列为独立后续 PR。
- **建议 PR**：`chore(tts): drop dead azure config`（若接线则 `feat(tts): azure backend`，含 `.env.example` 占位符）。

### P1-A · vtts-05 文本前处理：归一化（数字/缩写/清洗）·发音词典·ssml-lite 子集（✅ 归一化已实现）

- **目标**：`I'll`/`We're`/`50%`/`3.5`/`the U.S.`/`St.` 读对；拼写/专名可词典纠音。
- **改什么（已解耦）**：新增纯模块 `services/python/app/audio/textproc/normalize.py`（engine-agnostic，与 `sentence_splitter.py` 同归 `app/audio/textproc/`）；已接线到两个 choke point——`orchestrator.py` `_tts_url_from_bytes`（归一化在缓存键前）与 `routes/audio.py` `/tts`（合成前归一化）。依赖 `num2words>=0.5`（MIT）。
- **怎么做（借鉴自写，引 MIT `num2words`）**：
  1. `normalize_for_tts(text, language)`：**幂等、绝不 raise**（任何异常回退原文）。做：零宽/连续标点清理、缩写展开（`Dr./Mr./St./vs./etc./e.g.`，带 cap/digit 守卫）、数字→单词（`50%`→`fifty percent`、年份/序数/货币/小数/整数）。**已完成**。
  2. `apply_lexicon(text, dict)`：词边界整词替换 + 最长优先（处理专名读错）；可选 `[[term|replacement]]` 内联覆盖。**未做（后置）**。
  3. **不做**（后置）：完整 SSML-lite 解析也放 P1-E；本步只做引擎无关的文本清洗。
- **验收（已达成）**：纯函数测试：`normalize_for_tts("50%")=="fifty percent"`、`"3.5"`→`three point five`、`"Dr."`→`"Doctor "`；`normalize(normalize(x))==normalize(x)`（幂等）；`[pause 300ms]`/`[[…]]` 不破坏（括号内跳过）。
- **风险/回退**：低。纯函数、可回退（异常回退原文）。走 `textproc/` 独立模块，不对 `TTSClient` 动刀。
- **建议 PR**：`feat(tts): text normalization`（含 num2words 依赖 + 纯函数测试）。已按此实现。

### P1-B · vtts-06 缓存确定性：键扩容 + TTL + /tts 复用

- **目标**：不命中陈旧音色；`/tts` 与热路径缓存语义一致。
- **改什么**：`audio/tts.py:69-73`（key）、`:49-52`（path）、`orchestrator.py:120-128`；`routes/audio.py:91-92`。
- **怎么做（借鉴自写）**：
  1. 键扩成 `sha1(provider|engine_version|voice|rate|text)`（加 provider + 依赖版本 + 采样率外部戳，参考 VS `segment_cache_key` 把「影响成品的维度」都进键）。
  2. 加 TTL（如 24h）或进程重启清空：`cached_audio_path` 检查 mtime 过期即重取。
  3. `/tts` 复用同一缓读取数（现为每次现合成，见 `audio.py:91`）。
- **验收**：同参数两次 → 命中；改 provider/版本 → key 变化 → 重取；跨 TTL → 失效。
- **风险/回退**：低。只动键与命中逻辑。
- **建议 PR**：`fix(tts): cache key + ttl + reuse on /tts`。

### P1-C · vtts-04 拼接：缺句上报 + AudioChunk 带 duration

- **目标**：句失败**不再静默**；前端有能力做 Gap-less 排播。
- **改什么**：`orchestrator.py:112-132`（`_tts_url_from_bytes` 失败分支加日志/上报）、`events.py:40-42`（`AudioChunk` 增 `duration` 可选字段）。
- **怎么做（借鉴自写 + 待评估项）**：
  1. `_tts_url_from_bytes` 失败：`logger.warning("sentence no audio: %r", text)` + 埋点 `events`（vs VS `report_dropped_chunks` 思路）。
  2. `AudioChunk` 加 `duration: float | None`（edge-tts 单句时长近似可得），前端据此做连续播放。
  3. **crossfade 本轮不做**（见 §6 待评估）：对话短句+网络 TTS 价值低，且需 mp3→PCM 解码在服务端拼接，成本高。
- **验收**：单测模拟一次合成失败 → 触达日志/埋点，且不 crash。
- **风险/回退**：低。
- **建议 PR**：`fix(tts): report dropped sentences + duration`。

### P1-D · vtts-07 输出封装：/tts 统一 URL + 响度归一

- **目标**：消除 hex×2 与「热路径 URL / 独立 /tts hex」两套机制；响度一致。
- **改什么**：`routes/audio.py:78-92`；`base.py:36-40`（TTSResult 契约）；`orchestrator.py:135-146`（`save_audio_bytes`）。
- **怎么做（借鉴自写/直接引库）**：
  1. `/tts` 改走 `save_audio_bytes` 返回 URL（复用热路径），`TTSResult.audio_bytes` 改为 `str`(URL) 或新增 `url` 字段；二进制返回（`Response(content, media_type="audio/mpeg")`）为备选（但打破 `Envelope` 泛型）。
  2. 响度：落盘前用 ffmpeg `-af loudnorm`（**直接引库**）归一；`save_audio_bytes` 增加可选 loudnorm 步骤。
- **⚠️ 契约变更**：改返回形态 = 破坏 `Envelope[TTSResult]` → 必须同步 `docs/21` 双快照对账 + 前端调用点（`free_chat`/前端 `/tts` 消费方）；按 `AGENTS.md` 需**联调测试页 + 删除清单**（dev-only）。
- **验收**：`/tts` 返回 URL（或 audio bytes）；两次同文本响度一致（loudnorm 生效）；OpenAPI 快照**零 diff**（已在 docs/21 同步）。
- **风险/回退**：中（契约 + 前端）。**建议在 P1-A~C 之后**，独立 PR。
- **建议 PR**：`refactor(tts): /tts to URL + loudnorm`（含契约同步 + 联调页）。

### P1-E · vtts-08 语速/停顿/节奏：ssml-lite 子集 → 逐句 rate + [pause]

- **目标**：LLM 能表达停顿/放慢/强调。
- **改什么**：`orchestrator.py:397-400` 前加一轻量解析层；`audio/tts.py:29`（`rate` per-sentence）。
- **怎么做（借鉴自写，只取解析模式）**：
  1. 文本入口解析 `[slow]/[fast]/[emphasis]/[spell]/[pause Nms]` → 分段 `{text, rate_delta, spell, pause_ms}`（最内层覆盖外层，未闭合到行尾）。
  2. 逐句把 `rate` 传给 `synthesize`（edge-tts 支持 `rate` 参数，近似实现 slow/fast）；`[pause]` 在句间插静音（合成静音段或 `AudioChunk` 之间加 pause）。
- **验收**：`"[pause 300ms] ok"` → 解析出 pause 段；`[slow]` → 该 segment rate 下调。
- **风险/回退**：中。若 LLM 输出含 `[` 干扰，需白名单严格；解析一律宽松降级（未知 tag 当原文）。
- **建议 PR**：`feat(tts): ssml-lite pause/slow subset`。

### P2 · vtts-09 听读逐词时间轴（后置）

- **目标**：听读时逐词高亮。
- **怎么做（借鉴自写）**：按句长/词数与句时长均分（`audiobookLyrics.js evenSplitWords` 思路自写）；**勿用 ASR 反推**（多一次转写且误差放大）。
- **验收**：`[ {word,start,end} ]` 与 `AudioChunk.duration` 对齐。
- **建议 PR**：`feat(tts): word-level timeline`（后置）。

---

## 5. 测试策略（TTS 不碰真服务）

- **纯函数优先**：`StreamSentenceSplitter` 的句界判定、`textproc.normalize_for_tts`、`apply_lexicon`、`parse_ssml_lite` 均做成**纯函数**（不 import edge_tts / azure / 网络）。
- **依赖注入**：`run_turn` / `/tts` 已走 `TTSClient` 接口；新测试全部用 `FakeTTSClient`（`app/audio/stubs.py:34-38`），扩展它支持「可配置失败/延迟」以测降级。
- **CI 口径**：不打真 TTS/Azure/edge-tts。新增 `pytest` 用例只覆盖逻辑；`edge_tts`/`azure` 用 `monkeypatch`/接口 fake。`ruff check`/`ruff format` 必过。
- **契约快照**：凡动 `OpenAPI` 契约（P1-D）卡 `docs/21` 双对账快照零 diff。

---

## 6. 待评估项（明确后置，不进本期 TTS 主线）

| 项 | 理由 | 建议 |
|---|---|---|
| **50ms crossfade** | 对话短句 + edge-tts 网络 TTS，拼接毛刺价值低；需 mp3→PCM 服务端拼接，成本高 | **后置**；短对话先靠 `AudioChunk.duration` + 前端 Gap-less |
| **m4b 章节目录** | 对「对话练习」偏重 | **不引入**；仅当有整篇读回/听力材料时再议 |
| **speech_rate「读时长预估 + LLM 增删词填槽」** | 仅「对齐某句示范音高/填时间槽」场景有价值 | **后置**；对话优先级低 |
| **发音词典(DB 持久化)** | 需 DB/设置 UI，成本高 | **后置**；先用纯函数 `apply_lexicon` 覆盖专名即可 |

---

## 7. 验收与门禁

1. **P0-A~C 完成后**：`pytest -q` 全绿（含新增回归测试）+ 手动复现 `Mr./3.5/U.S./Ph.D` 不再被错误切分。
2. **P1-A~E 完成后**：样例长句（含数字/缩写/停顿标记）听感合格；`/tts` 返回形态与 `docs/21` 一致；缓存命中/失效符合预期。
3. **每步**：`ruff check && ruff format --check` 通过；**每步独立 commit + worklog 置顶记录带署名**（`AGENTS.md` 记录纪律）。
4. **契约类改动**：`docs/21` 双快照零 diff + 联调测试页（dev-only，含删除清单）。

---

## 8. 不在本期范围（遗留项，另立）

- ASR 侧词级时间戳质量 / whisper 排队降级（`R-04`/`R-22` 相关）。
- edge-tts **GPL-3.0 + 微软服务条款**法律评审（`docs/audit:143/261`，与 Azure 接线联动）。
- 前端音频队列鉴权 / `onended` 双播 bug（`NR-5`/`R-07`，前端侧）。

---

## 9. 时间线（建议）

| 序 | 主题 | 人日估 | 谁 | 前置 |
|---|---|---|---|---|
| 1 | P0-A 切分修复 + 回归 | 0.5~1 | TTS | 无 |
| 2 | P0-B 生命周期 | 1~1.5 | TTS | 1 |
| 3 | P1-A 文本归一 | 1~1.5 | TTS | 无（可与 2 并行） |
| 4 | P1-B 缓存 + P1-C 缺句/duration | 0.5~1 | TTS | 3 |
| 5 | P0-C Azure（或删假配置） | 1~2 | TTS | 2 |
| 6 | P1-D /tts URL+loudnorm（契约） | 1~2 | TTS+前端 | 3 |
| 7 | P1-E ssml-lite 子集 | 1~1.5 | TTS | 3 |
| 8 | P2 词级时间轴 | 1~2 | TTS+前端 | 7 |

> 建议先交付 1+3（错误切分 & 文本归一，两个高可感低风险 fix），稳定后推进生命周期/兜底与契约类改造。
