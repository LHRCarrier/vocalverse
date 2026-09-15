# 24 · InternalBeyond（IB）借鉴落地计划 v3（三官拷问修订版）

> 依据：`local/InternalBeyond对比与借鉴分析.md`（调研笔记；行号已核验，基线 `Sui-IB/InternalBeyond@79e1f4b` V2.6.2）。
> 许可红线（已核验）：代码 PolyForm Noncommercial 1.0.0 / 素材 CC BY-NC-SA 4.0 —— **只借算法与思路，不拷任何代码/素材**（见 §9 答辩口径）。
> 版本：v2（2026-09-03 单人执行版）→ 经三官（技术/算法/范围）火力拷问 → **v3 修订定稿**。拷问结论全文见 `docs/25-InternalBeyond落地计划拷问报告.md`。
> **⚠️ 组长拍板（2026-09-03 追加）**：LLM 部分改为**对齐 ai4u 的分层框架**（见 `docs/26-LLM框架对齐ai4u评估与实施计划.md`）——本文档 A 系列（⑤⑥）实现方式由 docs/26 §8「P0 内核最小切片」**取代**（ContextBuilder 抽取即拆条的归宿，目标不变）；B 系列（韵律引擎）继续按本文档 §8 顺延；许可红线与禁止项继续有效。
> 执行框架：**今日 = 2026-09-03**；**组长拍板（2026-09-03）：LLM 框架优先**——今日范围 = **A 系列全量（上下文层 + 画像注入 + 真 Key 验证）**，B 系列**整体顺延**（不做骨架；理由：B 今日无 UI 消费方，且 LLM 链路从未真 Key 实跑，先立框架比先做无消费方的引擎优先）；**今日 PR「就绪待审」，不自审自合**（docs/05 红线，见 §3/§4）。

---

## 0. 目标与完成定义（DoD）

- [ ] **A 系列**（今日硬底线）：
  - `build_llm_context` 静态/动态拆条（**重写**，非「仅调序」——保留 `set conclude=true` 行为指令与 corpus/hits `(none)` 兜底）；
  - `learner.py` 画像注入（短语/词，≤3 条、可开关、TTL 900s、`_post_session_skills` 收尾失效）；
  - A 系列 **6 个 pytest 红→绿**：P1（**修正版锚点，见 §1-B3**）/ P2（动态后置）/ P3（渲染+省略双态）/ P4（画像聚合排序）/ P7（开关关闭）/ P8（收尾失效）；
  - POC 脚本 `scripts/poc/llm_cache_hit.py`（无 Key skip 路径走通，**不实跑**）；
  - Fake 链路冒烟：会话→turn→收尾→报告全链路，画像注入行在 system 尾部可见；**PR 描述如实标注「Fake 链路验证 + 真 Key 待实跑」**（无 Key 无法证明缓存命中——F1-1）。
- [ ] **B 系列**：**整体顺延**（组长拍板，2026-09-03）。原「引擎骨架 + 2 vitest」→ 全部移入 §8；仅保留设计定稿（§2 原文即 B 官修订后的最终口径，实施时按此执行）。
- [ ] **文档同步**：docs/14 §3.4 prompt 模板回写（prompt_version 2）+ docs/06 §7 登记一行（成本策略）+ README + docs/25 拷问报告 + worklog 置顶署名（≥2 次，执行人 LHRCarrier）。
- [ ] **门禁**：Python `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`；前端 `pnpm lint && pnpm typecheck && pnpm test:run && pnpm build`。
- [ ] **PR 纪律**：PR1（A）/PR2（B 骨架）push + CI 绿 + **组长自评 comment（非 approve，见 §4）** + 挂 reviewer 待审；**今日不合并**。

**明确不做/顺延**：④ 运行摘要、⑦ 报告导出、② 双路 ASR、③ barge-in（前瞻登记）；B 完整 8 例 / f0 细节 / 降采样 44.1k 用例 / `blobToMonoBuffer`；A 真 Key 冒烟与契约评审合并；speechRate（SSE 不下发用户转写，A 阶段是死输出——B 官 P1#4）。

---

## 1. A 系列：LLM 上下文层（⑤ + ⑥）

### A1. `build_llm_context` 拆分（`services/python/app/practice/service.py:356`）

**现状**：单条 system 混装静态+动态（难度/语料/hits/轮次/滚动摘要都进 system）→ 每轮变化点太靠前，前缀缓存几乎不可命中。

**⚠️ 定性（A 官 F01）**：新布局对原 system 是**重写**——「语义与现版完全等价、仅调整语序」**不成立**；所谓「等价」是**目标**，须靠冒烟核验。原 `If the conversation reached the limit or user ends, set conclude=true.` 是**行为指令**，必须保留（放入静态块——它本身逐字稳定）；`corpus_text or '(none)'`、`hits_so_far or '(none)'` 的兜底也要保留。

**目标消息布局**（仍 2 条消息：1 system + 1 user；不新增 system 条数）：

```
system:
  ── STATIC（逐字稳定）──
  {scenario_prompt}
  You are role-playing in an English speaking practice app.
  Keep sentences short (≤3 sentences), simple words, natural and encouraging.
  If the conversation reached the limit or user ends, set conclude=true.   ← 保留（原行为指令，逐字稳定）
  Output contract: reply as plain English text ONLY, then finish with a single line:
  [-META-]{}
  META JSON fields: grammar:{score:0-100,errors:[{word,fix}]}, coach_note(≤15 words),
  corpus_hits:[{phrase,state:'ok'|'fix'}], difficulty_delta:-1|0|1, conclude(bool).
  ── DYNAMIC BEGIN（此后内容逐轮可变）──
  Target language level: difficulty {difficulty}
  Naturally steer the topic toward these target expressions WITHOUT reading them aloud: {corpus_text or '(none)'}
  {learner_profile}            ← A2 渲染块（空则整行省略；放「会话级稳定段」，见 tradeoff）
  Already used expressions — rephrase instead: {hits_so_far or '(none)'}
  Turn limit reached: {concluded_by_turn}
  Recent turns:
  {digest 3 行}
user:
  user said (ASR): {user_text}
  action: {action}
  word_errors: {n}
```

- **动态块内两级**：会话级稳定字段（difficulty / corpus_text / 画像行）在前，逐轮变化字段（hits / concluded / Recent turns）在后——最大化命中前缀（DeepSeek 按请求前缀匹配）。
- **Tradeoff（A 官 F07，注明即可）**：画像行是用户专属 → 跨用户同场景共享前缀只到 corpus 为止（不穿 learner 行）。切换策略需 POC 数据支撑，本期不做判断。
- 函数签名：增加可选参 `learner_profile: str = ""`（保持纯函数，不接 db）；
- `orchestrator.py:360` `"prompt_version": 1` → **2**（语义：v2=稳定前缀+画像注入；docs/14 §3.4 回写）；`_dialog_turn` 调 `build_llm_context` 前取一次画像；defense 路径**不动**（`_defense_turn` 不用本函数）；
- **改动面前置确认（C 官 F1-2）**：开工 step ① 先 `grep prompt_version / build_llm_context / messages` 全仓——A 官实测**无既有测试断言**这些（零破坏），但必须当场复核；若命中 → A 顺延。

### A2. 学习者画像 `services/python/app/practice/learner.py`（新文件）

```python
@dataclass(frozen=True)
class LearnerProfile:
    weak_phrases: list[str]   # user_corpus_mastery.status=='not_mastered'，last_practiced_at 降序，≤learner_max_items
    weak_words: list[str]     # Python 侧聚合（见下），≤learner_max_items
    est_level: str | None     # user_skill_state.est_level（confidence>=skill_confidence_min 才给；今日可先不做此行——C 官 F0-1 砍项）

def render(profile) -> str:  # 纯函数；输出 "Learner profile (internal only): weak phrases: [...]; frequent word errors: [...]; level: L2. Gently address these, do not overcorrect."
def build_profile(db, user_id) -> LearnerProfile
def get_rendered(user_id) -> str   # 进程内 TTL 900s + learner_injection_enabled=False → ""
def invalidate(user_id) -> None
```

- **数据源（只读，零迁移）**：
  - `UserCorpusMastery`：`status == NOT_MASTERED` → `.phrase` 快照；
  - `Attempt.details['word_level']`：**Python 侧聚合**（A 官 F03——PG 专属 JSONB 函数在 SQLite 单测跑不起来）：`select(Attempt.details).where(user_id==?, kind==DIALOG_SPEECH).order_by(Attempt.id.desc()).limit(learner_word_error_window)`，Python 遍历 `details.get('word_level', [])`（**非 list/None 防御**，F08）按词频降序取 top-N；
  - 词级判断谓词（F04）：**显式白名单** `error_type in ('substitution','omission','insertion','mispronunciation','stress','intonation')` **且** `score < 60`（均可不命中时降级为词频前 N）；**注明**：ISE 词级 error_type 取的是词首音素（ise.py:97-99），属试探性判定，真 Key 冒烟核验后回写；
  - `UserSkillState`：`est_level`（confidence 门槛 0.35，复用 skill_confidence_min）。
- **失效挂钩**：`practice/service.py _post_session_skills`（L192）末尾 `learner.invalidate(session.user_id)`（异常吞掉，沿用现有风格）；TTL 兜底。
- **单进程注记（F09）**：本服务现为单进程模型（会话状态/锁在进程内 StateStore）；若未来多 worker，本缓存需迁 Redis——在代码注释注明。
- **Settings 新增**（`app/core/config.py`）：`learner_injection_enabled=True` / `learner_max_items=3` / `learner_cache_ttl_s=900` / `learner_word_error_window=20`。
- **既有问题注记（F10，A 系列范围外）**：`word_errors` 读 `state.assembled.get('last_errors')` 但该值从未写入（orchestrator 只在局部定义）→ 恒为 0。今日顺手修复：`_dialog_turn` 把 `last_errors` 写入 `state.assembled`（1 行，含测试则 P0；不测则记 §8 待办）。

### A3. POC：`scripts/poc/llm_cache_hit.py`（新文件）

- **`.env` 加载（A 官 F06——deepseek_meta.py 实为只读 `os.environ`，全仓无 load_dotenv）**：脚本内 `from dotenv import load_dotenv; load_dotenv()`（python-dotenv 已是依赖）或 `os.environ['DEEPSEEK_API_KEY']` 手动读取 `.env`；无 Key → print skip + 正常退出；
- 固定「静态前缀+动态占位」messages **连续 5 次**非流式调用（`max_tokens=32`），解析 `usage.prompt_cache_hit_tokens / prompt_cache_miss_tokens`，输出命中率；
- **桶说明（F11）**：POC 直连 DeepSeek，**不触** app 的 30/h per-user 桶（桶只在 /turns 扣），仅消耗共享 key 账户配额；另注：conclud 轮 `_conclude_summary` 的 `llm.chat` 也未另计桶（既有行为，本期不处理）；
- **判定口径**：第 2 次起命中率 >0 即「机制成立」；实跑记录回写本节（无 Key →「待实跑」）。

---

## 2. B 系列：浏览器端韵律特征引擎（①，今日 = 骨架）

### B1. `apps/web/src/audio/prosody.ts`（纯函数零 DOM）

```ts
export interface ProsodyOptions { frameMs?: number /*30*/; hopMs?: number /*15*/; targetRate?: number /*16000*/;
  f0Min?: number /*80：30ms 帧≈2.4 周期，60Hz 仅 1.8 周期不可靠*/; f0Max?: number /*400*/; pauseThresholdS?: number /*0.35*/ }
export interface ProsodyFeatures { durationS; sampleRateUsed; meanDb /*全帧均值 dB 钳 -100*/;
  energyCv /*全帧，全静音=0 禁止 NaN*/; tailDeltaDb /*后 20% 全帧-前 20% 全帧*/; pauseRatio; longPauses; voicedRatio;
  f0MedianHz|null; f0SpreadHz|null; f0TailDeltaHz|null; f0Jitter|null }
export function analyzeProsody(samples: Float32Array, sampleRate: number, opts?): ProsodyFeatures
export function downmixTo16k(samples: Float32Array, sampleRate: number): Float32Array   // 分块均值抽（步长=rate/16000）
export async function blobToMonoBuffer(blob: Blob): Promise<{samples: Float32Array; sampleRate: number}>  // 今日可不做（单测不需要）
```

**作用域规则（B 官 P0#1/#2）**：VAD 与 f0 全部在**线性 RMS 帧能量域**（p10/p90、×4、×0.5、1e-4 是线性语义）；**dB 只出现在报告端**（`20·log10`，钳 -100），绝不用 dB 帧值喂 VAD。能量类特征（meanDb/tailDeltaDb/energyCv）按**全帧**统计；VAD/f0 按**语音帧**。

**算法要点（IB 思路独立重写；文件头注释按 §9 合规口径写明来源）**：
- 帧能量：线性 RMS = sqrt(mean(x²))；hop 推进；
- VAD（线性域）：`noise=p10`，`thresh=min(max(noise*4,1e-4), p90*0.5)`；`p90<1e-4` → 全静音；
- 停顿：语音帧间隙 ≥0.35s → `longPauses+=1`；`pauseRatio=静音帧/总帧`；
- f0（只对语音帧）：**去均值 → Hann 窗 → 归一化自相关**（延迟区间 `[fs/400, fs/80]`）→ 取**最小滞后**且 r>0.3 的局部峰（Hann 窗使窗自相关随 τ 单调递减 → 自然选中最高 f0，防 200Hz 纯音在 τ=80/160/240 平局取到 66.7Hz；r>0.3 不防倍频，防倍频靠最小滞后规则）；
- 统计：f0 中位数/IQR/首尾段差/相邻抖动（今日骨架 **只做 f0MedianHz**，其余返回 null 顺延 §8）；
- 确定性：无随机/无 await/无外部 API。

**边界注记（C 官 F2-6 / F2-5）**：prosody = **语音韵律**（口语流利度/节奏/力度），唱歌音准 = 后端 pyin+DTW（M3），**勿混用、勿拿 prosody 当唱歌/硬评分指标**；与 docs/23 前端重构选型 **pitchy（实时 F0 反馈）** 的分工 = 离线分析 vs 实时反馈，今日交付的 engine 独立资产待 docs/23 phase5 接入。

### B2. 测试：`apps/web/src/audio/__tests__/prosody.test.ts`（今日 2 例，其余 6 例顺延 §8）

| # | 用例 | 构造 | 断言 | 修复前必失败原因 |
|---|---|---|---|---|
| 1 | 全静音 | 1s 全 0 | pauseRatio≈1、meanDb≈-100（钳制）、f0MedianHz=null、energyCv=0（非 NaN）| 引擎尚不存在 |
| 2 | 纯音高 | 1s 100Hz 正弦（幅 0.5），fs=16000 | f0MedianHz ∈ 98~102 | 防「f0 主频错 1~2 倍 / 平局取错滞后」——本批最易翻车的点 |

> 顺延（§8）：停顿计数、能量包络 tailDeltaDb、降采样长度断言（**===16000 精确 + 44.1k 非整数步用例**，B 官 P1#6）、200Hz 倍频用例、downmix 边界、blobToMonoBuffer（happy-dom 无 Web Audio，B2 只用 Float32Array——B 官已核实）。

---

## 3. 单人执行顺序（2026-09-03，按 C 官裁决重排）

| 时间 | 步骤 | 交付/验收 |
|---|---|---|
| 09:30–09:45 | ① 基线快照（pytest/test:run/typecheck 绿）+ **grep prompt_version/build_llm_context/messages 确认改动面零命中** | 基线绿 + 改动面清单 |
| 09:45–11:30 | ② A1 拆条（保留 conclude 指令与 `(none)` 兜底）+ P1/P2 红→绿（**先写测试见红**） | 前缀子串一致（核心锚点） |
| 11:30–12:30 | ③ A2 learner.py（Python 侧聚合 + 白名单谓词 + 防御）+ Settings + 收尾失效挂钩 + P3/P4/P7/P8 红→绿；顺手修 word_errors（F10） | 画像注入 ≤3 条/可开关/收尾失效 |
| 12:30–13:30 | 午休 | — |
| 13:30–14:00 | ④ A3 POC 脚本（dotenv 加载 + 无 Key skip 走通） | 脚本可跑 |
| 14:00–15:00 | ⑤ **LLM 真验证（LLM 框架最关键一步）**：POC-2 `scripts/poc/deepseek_meta.py` 真 Key 实跑（META 成功率 ≥90% 判定一次调用方案）+ `llm_cache_hit.py` 命中率实测（≥5 轮；第 2 次起 >0 即机制成立）；无 Key → 如实标注「Fake 验证 + 待真 Key 实跑」 | 真 Key 冒烟报告（回写 §5 与 docs/14 POC 状态） |
| 15:00–16:00 | ⑥ Fake 链路冒烟（会话→turn→收尾→报告；日志确认画像行在 system 尾部）；有 Key 则再加 5 轮真对话冒烟（META/风格/教练笔记） | 冒烟通过（PR 标注实跑状态） |
| 16:00–16:40 | ⑦ 全量门禁（Python ruff/format/pytest；前端 lint/typecheck/test:run/build） | 全绿 |
| 16:40–17:20 | ⑧ 提交：PR1（A：代码/测试/docs 3 commits）；push + CI；**组长自评 comment（非 approve）+ 挂 reviewer 待审** | PR1 就绪待审（不合并） |

**超时裁决（C 官 F0-1 + 组长 LLM 优先拍板）**：今日只收 A 系列；B 整体顺延（无砍项负担）。A 内部砍项：真 Key 实跑 → 无 Key 则只走 Fake + 标注；冒烟 5 轮真对话 → 无 Key 则略；A 的 est_level 行 → 砍；P5/P6（窗口超限/invalidate monkeypatch）→ 顺延（P6 由 ⑧ 挂钩 Mock P8 覆盖）。**测试与门禁不可砍**。

## 4. PR 拆分与提交规范（今日不合并）

| PR | 分支 | 内容 | Commit | 今日终点 |
|---|---|---|---|---|
| PR1 | `feat/agent-stable-prefix-learner` | A1+A2+A3+F10 顺手修 | 3 commits（代码/测试/docs）分开 | push + CI 绿 + **自评 comment + 挂 reviewer** |
| ~~PR2~~ | ~~`feat/audio-browser-prosody`~~ | B 系列**整体顺延**（组长拍板），随 docs/23 前端重构波次实施 | — | — |

- **合规通道**：A 改 M2 冻结契约（docs/18 §2 冻结后改动走 review）→ 属「实现」非新架构决策，**无需 docs/06 新增 ADR**（C 官 F2-2），但三件必做：docs/18 §2 review 通道 + docs/14 §3.4 回写 + `prompt_version=2` 语义登记（docs/06 §7 补一行成本策略，建议非阻断）；
- **自评 comment 模板**：scope / 触发路径 / CI conclusion（含 jobs.total_count 防「工作流启动失败」假绿）/ 冒烟状态（Fake 链路过、真 Key 待实跑）/ 待评审项；**不 `--approve`、不 merge**；合并等次日 reviewer（docs/05「另一名成员评审，不要自审自合」）；
- PR 描述声明：**无新增/变更 API 路由、无迁移、无 .github/workflows 变更**（无需 refresh-openapi / alembic / yaml 校验——C 官纪律④⑤）。

## 5. 验收（手动 + 自动）

1. 自动：§1/§2 用例红→绿记录；全量门禁绿；
2. 冒烟（无 Key）：Fake 链路全通 + 画像注入行在 system 尾部可见（日志/调试）；**真 Key 冒烟（META ≥90% + 教练笔记自然 + `[-META-]` 解析无回归 + 缓存命中率实测）留待 Key 就绪日**，PR 如实标注；
3. B 骨架：2 用例绿；真录音 console 抽查（非 NaN，pauseRatio 0~1，f0 非离谱）。

## 6. 风险与回退

| 风险 | 触发 | 回退 |
|---|---|---|
| 拆条重写 → META 解析率/扮演风格劣化 | 真 Key 冒烟 META <90% | **二选一（A 官 F05，不可兼得）**：(a) 完全回退 prompt_version=1（放弃前缀稳定，P1/P2 断言按 v1 重写）；或 (b) 保留分组但边界前移（动态更靠后、稳定前缀变短、逼近原语序）。POC 数据支撑后再下结论 |
| 画像注入过度纠正 | 冒烟观察 | `learner_injection_enabled=False` 一键关 |
| word_level 判定与 ISE 词首音素语义不符 | 真 Key 冒烟核验 | 白名单收缩或降级为「低分词频次 top-N」 |
| 多进程不一致 | 未来 uvicorn>1 | 缓存迁 Redis（代码注释已标记，现状单进程） |
| 单人日超时 | 17:20 未完成 | 按 §3 模块级砍项；**绝不跳过测试与门禁** |
| f0 平局/低频周期不足 | 骨架用例 2 | Hann 窗+最小滞后规则已有；f0Min 80 兜底；仍是「趋势/辅助」不作硬指标 |

## 7. 依据

- 调研：`local/InternalBeyond对比与借鉴分析.md`（①12952–13092 / ⑤14298+11663 / ⑥15696,16754–16780,22536,22964）
- 官方事实：[DeepSeek 缓存（自动、无参数，usage 含 prompt_cache_hit_tokens）](https://api-docs.deepseek.com/zh-cn/news/news0802/)；[IB LICENSE](https://github.com/Sui-IB/InternalBeyond/blob/main/LICENSE)
- 本仓：docs/14 §3.4（prompt 契约 v2 需回写）/ §2.2（教练双人格——注入措辞向「轻纠正+重复盘」靠拢，属 role 行为层微调，非 coach 层）、docs/18（契约冻结/POC 先例）、docs/10（mastery/attempts）、docs/06 §7（限流）、docs/05（评审纪律）、docs/23（前端重构/pitchy 分工）、services/python/app/practice/{service,orchestrator,state,corpus}.py、scripts/poc/deepseek_meta.py

## 8. 待办（明确顺延，非阻塞）

- **B 系列整体**（组长拍板 2026-09-03）：`prosody.ts` 引擎 + 8 vitest（全静音/纯音高/停顿/包络/降采样===16000+44.1k/倍频）+ f0Spread/f0TailDelta/f0Jitter + blobToMonoBuffer + UI 挂接——按 §2 设计定稿实施，建议随 docs/23 前端重构波次；
- A 真 Key 冒烟（META 率/缓存命中率实测）——若今日无 Key，POC-2 与 cache POC 一并列为「密钥就绪日」首项（docs/14 POC 状态同步更新）；
- PR1 次日 reviewer 评审与合并；
- speechRate（语速）——需 SSE 下发用户转写（B3 契约落库）后实现；英文语速阈值标定（真人口语样本）；
- 报告页韵律小节 + 学习报告导出（随 docs/23 前端重构）；
- word_errors 值注入（若今日未顺手修）。

## 9. 答辩口径（C 官 F2-7，评审追问用）

- **为什么这么组织 prompt**：DeepSeek 上下文缓存按请求前缀自动匹配（无需参数、磁盘级）——把逐字稳定的角色/输出契约放前缀、逐轮可变内容全部后置，前缀稳定即命中、命中即降成本（LLM 在 TTS+ISE 面前成本占比小，故定位为「上下文一致性与成本双优化」，不是纯省钱）；
- **韵律指标哪来的**：算法**概念**源自 IB `_vmToneAnalyze`（12952–13092，PolyForm NC 1.0.0 项目），本仓**独立重写**（TS 纯函数），未拷任何代码/素材（视觉/文档 CC BY-NC-SA 4.0 同样不碰）；参数（30ms/15ms、0.35s、80–400Hz）属功能性事实不受版权保护；
- **为什么不直接用**：IB 整站单文件/离线架构与本仓 Vue3+FastAPI 多端架构不兼容；其语音模块以浏览器 IndexedDB + 个人使用为目标，本仓为服务端权威（faster-whisper/ISE）+ 前端增强；
- **B 为什么只做骨架**：接入点在前端重构报告页（docs/23 phase5），今天先交付可测引擎资产，避免在旧页重复挂接。

---

*状态：v3 修订定稿（已过三官拷问，见 docs/25）。今日按 §3 执行，PR 就绪待审。*
