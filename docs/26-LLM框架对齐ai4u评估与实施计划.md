# 26 · LLM 框架对齐 ai4u 评估与实施计划

> 依据：组长的自研项目 `F:\WorkingL\ai4u`（Electron+Vue3+NestJS 桌面 AI 伴侣；Agent 运行时为自研分层架构，README + `docs/agent/` 与源码已通读）。
> 性质：**架构模式迁移，不拷贝代码**（技术栈不同：NestJS/TS → FastAPI/Python async；且 ai4u 本身无 LICENSE、含米哈游素材/IB 风格借鉴，仅可借「分层思想」，任何代码/视觉不入境）。
> 与 docs/24 关系：本文档**升级并替代** docs/24 的 A 系列实现方式——A 系列（⑤前缀稳定+⑥画像注入）成为本框架 P0 的**第一批内容**；docs/24 其余裁定（B 系列顺延、许可红线、禁止项）继续有效。
> 状态：**评估通过（v1），待组长拍板分期（§7）**。

---

## 0. 一句话结论

**可以。** ai4u 的 Agent 运行时是一套「场景门面 → 回合执行器 → 上下文组装 → 领域逻辑 → 兜底钩子」的**纯架构模式**，与 VocalVerse 的现状是升级关系而非推倒：VocalVerse 已有 SSE 异步生成器（与 ai4u 的 `AsyncGenerator` 形态天然对应）、已有 META 结构化输出（相当于 ai4u 工具调用的简化版）、已有收尾钩子雏形（`_post_session_skills`）——缺的是**把它们抽象成分层**，以及 ai4u 做得最深的**记忆/摘要/用量**三块。迁移**不改任何对外契约**（SSE 事件、REST、META 协议、prompt_version 语义），M2 DoD 测试全绿是硬门禁。

---

## 1. ai4u 框架解剖（迁移对象）

| 层 | 职责 | 关键机制（可借鉴点） |
|---|---|---|
| `scenes/` | 场景门面（assistant/companion/trpg）：编排 context-builder → turn-runner → message-sink → hooks/摘要 | 每场景一个门面，场景决定工具集与规则 |
| `runtime/turn-runner` | LLM 流式循环 + 工具调用回放 + 最后一轮强制正文 + 用量累加，async generator 产出 delta/status 事件 | **DSML 泄漏门**（畸形工具标记当正文透传时拦截→弃轮原地重试≤2，工具轮整轮缓冲防「前半句+重试完整句」拼接）；检索类工具每轮配额 3 次防成本爆炸；工具轮 maxTokens 放大（长参数截断修复） |
| `runtime/context-builder` | **单一入口**组装：历史 N 条原文 + 滚动摘要 + 记忆注入 + 临近日历/待办 + few-shot → system + messages | 「唤醒即检索」统一构造检索 query；每类注入失败各自降级为空不阻塞 |
| `runtime/tool-executor` + `tool-defs` | 工具注册表 + 执行；tool-params 校验 | 工具上下文（actorId/会话/剧本）注入；搜索工具配额 |
| `runtime/message-sink` | 落库门面（消息 + 溯源角标） | 与 RSS/IM 解耦，SSE 无关 |
| `domains/memory` | 记忆双轨：`memory-injector`（**置顶优先 + 衰减排序 + 语义重排 + 字符预算 + 15% 探索窗口**，激活计数/最后激活时间回写）· `summarizer`（**增量滚动摘要**：近 N 条原文保留、更早 40 条按 4 条/次触发异步压缩、首尾保底 300/100 字、重试+失败标记自动重试）· `auto-memory` · `recall_memory`/`save_memory` 工具（AI 自主召回/写入） | 摘要↔记忆收敛为同一事实源（约定沉淀）；确定性探索（最久未激活优先，弃随机） |
| `domains/persona` | persona-builder（人设+背景+语气+few-shot 组装）；tone-calibrator（语料提取语气特征） | 角色一致性优先 |
| `hooks/` | 回合后兜底钩子注册表 + 运行器（模型漏调用时兜底：定时消息/手账/送卡片） | 失败静默、绝不阻塞回合 |
| `core/llm` | chat / chatStreamRich（含 usage 事件）+ reasoning_content；轻量模型标志（摘要用 light） | usage 记账（prompt/completion tokens）贯穿所有调用点 |
| `core/usage` | 用量统计服务 | 成本可溯源 |
| `proactive/` | 主动消息（触发选择器/决策门/调度器/冷却） | —— VocalVerse 不做 |
| `knowledge/` + RAG | 知识库导入/分块/向量/FTS5 + rerank | —— VocalVerse 不做（无独立知识库产品线；语料走场景绑定即可） |

---

## 2. 映射表（ai4u → VocalVerse）

| ai4u | VocalVerse 现状 | 迁移动作 | 落点（建议） | 量级 |
|---|---|---|---|---|
| scenes | `orchestrator._dialog_turn` / `_defense_turn`（未抽象） | 建 `app/agent/scenes/`：dialog/defense 门面，编排器收敛为门面调用 | `app/agent/scenes/{dialog,defense}.py` | 中 |
| turn-runner | `_dialog_turn` 内联 LLM 流式 + META 拆分 | 抽 `TurnRunner`：流式循环 + META 执行器 + **DSML/META 泄漏门**（ai4u 同款防「畸形标记透传」——M2 此隐患真实存在，docs/16 有先例） | `app/agent/runtime/turn_runner.py` | 中 |
| context-builder | `build_llm_context`（service.py:356 混装） | 抽 `ContextBuilder`：静态块/动态块两级 + （⑤稳定前缀）+ （⑥画像注入）+ 摘要 + few-shot，**单一入口** | `app/agent/runtime/context_builder.py` | 中（docs/24 A1+A2 并入） |
| tool-executor | `meta.py` 只解析不执行 | META 执行器（grammar/coach_note/corpus_hits/difficulty/conclude 的**权威执行**：命中/难度/收尾落库决策）——是「结构化输出即工具」的 ai4u 风格 | `app/agent/runtime/meta_executor.py` | 中 |
| message-sink | 落库散在 orchestrator | 抽 `MessageSink`（user/assistant 消息 + attempts + meta 幂等） | `app/agent/runtime/message_sink.py` | 中 |
| hooks | `_post_session_skills`（唯一钩子） | `hooks/registry + runner`：post-session（skills/learner 失效）、META 缺省兜底、摘要触发 | `app/agent/hooks/` | 低 |
| core/llm + usage | `llm.py`（无 usage） | 增强：stream/chat 返回 usage（含 `prompt_cache_hit_tokens`）；UsageService 记账（写 `usage_log` 新表或 events） | `app/agent/core/llm.py` + `usage.py` | 低 |
| domains/memory | ⑥ 画像注入（docs/24 计划）| **学习者记忆域**：mastery/skill/attempts → 「易错点清单」检索注入（=memory-injector 的 SQLite 版）+ 摘要双轨（=summarizer 的 ④）+ Auto-memory（会话收尾把新易错点**写入**学习者画像——ai4u save_memory 的对应物） | `app/agent/domains/learner/`（或学 ai4u 叫 memory）+ `app/agent/domains/summarizer.py` | 中-高 |
| domains/persona | 场景 system_prompt + 教练双人格（docs/14 §2.2）| persona-builder 化（人设/语气/规则/few-shot 组装；双人格收敛到 persona 域） | `app/agent/domains/persona.py` | 中 |
| tools 工具集 | 无（单次 META 调用） | **本期不引工具调用**（META 已是拍板契约、POC-2 未实跑）；turn-runner 预留 tools 参数 | — | — |
| 契约层 | OpenAPI 双快照 + sse-types（比 ai4u @shared 更成熟） | 不动 | — | — |

## 3. 不迁移清单（明确不做）

- `proactive/`（主动消息）、IM 信封/未读、`domains/journal`（手账）、`letter`（来信）、`trpg`（跑团）、`knowledge/`+RAG+rerank、多角色/角色语料、reasoning_content 思考模式（可留选项）、Electron/Ipc（VocalVerse 是 Web）。
- 长期「情感记忆」（角色与用户的私人记忆）不迁移——VocalVerse 的「记忆」是**学习者画像**（掌握度/易错词/错误类型），数据已在库，形态更结构化。

## 4. 分期实施

| 期 | 内容 | 人日 | 目标 |
|---|---|---|---|
| **P0 内核**（建议今日起） | ① 框架壳：`app/agent/` 目录 + scenes/runtime/hooks 骨架；② ContextBuilder（含 docs/24 ⑤⑥：静态/动态两级 + 画像注入 + learner 域基础版）；③ MetaExecutor 抽取；④ MessageSink 抽取；⑤ TurnRunner 事件化 + META 泄漏门；⑥ Usage 记账（prompt/completion/cache_hit）；⑦ hooks（post-session + learner 失效）；⑧ pytest 全量回归（DoD 绿是硬门禁） | 2.5~3.5 | 分层落地，行为零变化，为「框架」正名 |
| P1 | memory 域完整版：摘要双轨（④ summarizer：增量压缩 + 首尾保底）+ Auto-memory（收尾写入易错点）+ 学习者画像检索注入升级（预算/衰减/探索） | 1.5~2 | 长会话记忆闭环 |
| P2 | persona 域（双人格模板化）+ defense/placement 场景过门面收敛 | 1~1.5 | 三门面统一 |
| 砍 | proactive/IM/TRPG/journal/RAG | — | — |

> 与 docs/24 的关系：docs/24 A 系列（P0 ⑤⑥）**并入 P0 内核**（不再单独实现 `build_llm_context` 拆条——ContextBuilder 抽象就是它的归宿）；`llm_cache_hit.py` POC 不变；B 系列韵律引擎仍按 docs/24 §8 顺延。

## 5. 风险与回退

| 风险 | 触发 | 回退 |
|---|---|---|
| 重构伤 M2 契约/行为（SSE 事件、META、Fake 路径） | 全量 pytest/vitest 回归红、联调回归异常 | **保留现版 orchestrator 分支**，框架在独立分支孵化；行为等价 = 验收线（对比测试） |
| 今日单人天内框架壳做不完整 | 超时 | 砍项：框架壳只做 ContextBuilder+MetaExecutor+TurnRunner 三个纯抽取（hooks/usage 顺延）；不砍测试/门禁 |
| META 泄漏门误伤正常回复 | 真 Key 冒烟 | 阈值（标记特征）可配；泄漏仅弃轮重试 ≤2 |
| 与 docs/14 §3.4 契约评审冲突 | 改动 prompt 组装 | 契约冻结原则不变：SSE/META 协议不变，仅内部组织变化，走 docs/18 §2 review |
| 与 docs/14 §2.1 冲突 | 评审问「retry 命中作废？代码为何计命中」 | **已登记待拍板**（2026-09-03）：docs/14 §2.1 注释「retry/hint/demo 作废」与旧实现 `action in ("normal","retry")` 不符（retry 实际计命中）；本次重构按**行为等价**保留实现，未改语义——组内拍板改哪边后再动 |
| ai4u 引用合规 | 评审问「框架哪来的」 | 口径：架构模式受启发自组内自研项目 ai4u；代码全为 VocalVerse 自研实现；ai4u 制品（含其借鉴的 IB 风格/米哈游素材）不入境（§6） |

## 6. 答辩口径

- **为什么自研框架**：场景扮演 Agent 需要「上下文稳定性 + 记忆闭环 + 可测分层」（分层=单测边界、META 执行器=结构化输出权威、学习者画像=产品级记忆）；对照组内 ai4u 自主架构验证可行模式（产品不同：情感陪伴记忆 vs 学习者画像记忆）；
- **为什么不直接引工具调用**：M2 契约已拍板「一次调用 + META」（POC-2 验证后可能演进）；框架层预留 tools 接口为 M3+ 演进留口；
- **记忆来源合规**：学习者画像数据全部来自本系统评分/掌握度（非用户隐私原文），注入仅为「温柔提醒」，可一键关闭（learner_injection_enabled）。

## 7. 拍板点（组长）

> **拍板结果（2026-09-03 已确认）**：P1 分期采纳 §4；**P2 今日按 P0 内核最小切片实施**（ContextBuilder + MetaExecutor + TurnRunner 抽取 + learner 域基础版（含 docs/24 ⑤⑥）+ META 泄漏门 + 最小 hooks；MessageSink/usage/域完整版顺延 P1）；P3 usage 仅日志不建表；P4 答辩话术提「架构模式参考内部项目验证」。
> **今日（2026-09-03）真 Key 实跑与框架切片同天完成**：POC-2 流式 META + 缓存命中 + 5 轮对话冒烟。

| # | 拍板项 | 建议 |
|---|---|---|
| P1 | 分期采纳（P0 内核 → P1 memory → P2 persona） | ✅ 采纳 §4 |
| P2 | 今日范围 | ✅ **P0 内核最小切片**（见 §8） |
| P3 | Usage 记账表（数据库加 `usage_log` 表 vs 仅日志） | ✅ 仅日志+进程内统计（暂不加表，M3 报表再定） |
| P4 | ai4u 展示/引用是否在答辩材料提及 | ✅ 答辩话术提「架构模式参考内部项目验证」，不提仓库细节（ai4u 未公开 LICENSE） |

## 8. 今日执行序（2026-09-03，P0 内核最小切片）

| 时间 | 步骤 | 交付/验收 |
|---|---|---|
| 09:30–09:45 | ① 基线快照（pytest/test:run/typecheck 绿）+ grep 确认改动面 | 基线绿 |
| 09:45–11:00 | ② learner 域（`app/agent/domains/learner.py`：Profile/render/build/cache/invalidate + Settings + `_post_session_skills` 挂钩）+ pytest（P3/P4/P7/P8）红→绿 | 域就绪 |
| 11:00–12:30 | ③ ContextBuilder（`app/agent/runtime/context_builder.py`：静态/动态两级 + learner 注入 + ⑤）（先写 P1/P2 见红）| 前缀稳定锚点绿 |
| 12:30–13:30 | 午休 | — |
| 13:30–14:30 | ④ TurnRunner 抽取 + META 泄漏门（`app/agent/runtime/turn_runner.py` + `leak_gate.py`）：orchestrator 改调 runtime，行为等价 | 全量 pytest 回归绿 |
| 14:30–15:00 | ⑤ MetaExecutor 抽取（META 权威执行：命中/语法/收尾决策集中）| 同上 |
| 15:00–15:30 | ⑥ POC 脚本（`llm_cache_hit.py` + 复用 deepseek_meta.py） | 脚本可跑 |
| 15:30–16:30 | ⑦ **真 Key 实跑**：POC-2（META ≥90%）+ 缓存命中率（≥5 轮）+ 5 轮场景冒烟 | 实跑报告 |
| 16:30–17:00 | ⑧ 全量门禁（ruff/format/pytest + lint/typecheck/test:run/build）| 全绿 |
| 17:00–17:30 | ⑨ 提交：PR `feat(agent): llm-framework-core`（代码/测试/docs 3 commits）+ 自评 comment + 挂 reviewer | PR 待审 |

**超时砍项（顺序）**：MetaExecutor 抽取 → META 泄漏门 → P2 断言细节 → 真 Key 冒烟轮数（5 轮→3 轮）→ POC 实跑（留脚本+标注待跑）。**测试与门禁不砍**。

---

## 9. 真 Key POC 复盘（2026-09-03 · 推翻两处原设计并定案）

> 依据：真 Key（deepseek-chat）实测 60+ 次调用。结论已被 `context_builder.py` v2.2 实现固化。

### 9.1 实验矩阵与结果

| 臂 | 构造 | META 遵守率 |
|---|---|---|
| A | 静态 system（无示例、无动态）· 非流式 | 10/10 = **100%** |
| B | 静态 system + 完整示例 JSON | 5/10 = 50% |
| C | 静态 system · **流式** | 10/10 = **100%** |
| D | system 内动态块（难度/语料/摘要·含中文释义）· 流式 | 0/8 = **0%** |
| D1 | system 内动态块（**无**语料行）· 流式 | 4/8 = 50% |
| E | 动态块搬 **user 尾部**（含中文释义语料）· 流式 | 6/8 = 75% |
| E2 | 动态块搬 user 尾部 + **语料仅英文 phrase** · 流式 | 8/8 = **100%** ✅ |
| E3 | system 内动态块（语料仅英文）· 流式 | 0/8 = 0% |

### 9.2 定案（违反直觉但铁证）

1. **system 内禁止任何动态内容**（E3 证明：即使纯英文动态块在 system 内 = 0%；D1 证明动态块本身就有重罚）——system = 纯静态（角色/句长规则/conclude 指令/输出契约/META 字段说明），逐字恒定；
2. **所有动态上下文挂 user 消息尾部 `[context]` 段**（难度/语料/画像/已命中/收尾/摘要）——E2 = 100%；
3. **语料只注入英文 phrase**（`parse_corpus` 抽取，丢弃 `|中文释义`）——中文释义是给用户看的，进 LLM 上下文是污染源（E 75% vs E2 100%）；
4. **附加收益**：system 全静态 → DeepSeek 前缀缓存「完整匹配缓存前缀单元」全量命中（§8⑦ 缓存 POC 联合验证）；learner 画像进 user 尾（会话内稳定，不影响 system 命中，跨用户共享 system 缓存）；
5. **POC-2 原判**（`deepseek_meta.py`）35% 的根因 = 其 prompt 在 system 内嵌动态/示例混杂，非「一次调用」方案本身不成立 → **无需回退两调用**；`docs/18 §6` 预案保留为最终 B 计划；
6. **防御补丁**：模型可能输出 `grammar: 90`（裸数字）等畸形 META → `meta_executor.grammar_ok` 已加 `isinstance(dict)` 防御（冒烟实测抓出，旧代码同口径崩溃）。

### 9.3 对 docs/24/25 文档的追溯修正

docs/24 §1-A1 的「system 内静态/DYNAMIC 两级」布局**被本复盘推翻**（动态进 system 摧毁契约）：
目标同（前缀稳定 + 画像注入）但实现 = **system 全静态 + user 尾部 [context]**（本 § 为权威）。
docs/14 §3.4 已按 v2.2 回写；tests/agent/test_context_builder.py 断言已升级为
「两次调用 system 逐字节一致（非前缀子串）」——更强的锚点。

### 9.4 补偿调用（最终定案：条件性两调用）

全上下文下流式直出遵守率仍只有 ~40-75%（E2 单轮 100% 是信息量小的乐观情形）；继续调 prompt
边际收益不确定。**定案 = 条件性补偿**（`meta_executor.compensate_meta`）：
流式 META 缺失时后置一次 `llm.chat`（temperature 0.2、非流式、JSON 提取）——演示 20 轮 ×
~40% ≈ 8 次补偿 ≤ 30/h 桶（docs/14 登记）；契约可靠性从 40% → **100%**（框架冒烟 5/5 实证）。

| 方案 | 调用数/轮 | META 可靠性 | 取舍 |
|---|---|---|---|
| 一次调用（原契约） | 1 | ≈40-75%（全上下文实测） | 元数据大量缺失，coach_note/grammar 靠降级 |
| 全两调用（docs/18 预案） | 2 | 高 | 演示 40 次/轮超 30/h → 提频 |
| **条件补偿（定案）** | 1~2（均值≈1.4） | **100%（冒烟 5/5）** | 失败轮 +1 次调用；限流内达标 |

### 9.5 前缀缓存实证结论（收益重定位）

`llm_cache_hit.py`（预热 → 等 300s 落盘 → 相同前缀验证）在 deepseek-chat 上返回
**hit=0**（95-token 级请求；官方文档声明机制存在，本账户/模型未观测到可命中单元）。

**修正⑤定位**：前缀稳定的**根本收益是契约稳定**（B 官/实证：system 动态 → META 0% vs 静态 →
100%，差别是数倍）与 prompt 可测性；**缓存降费作顺带红利、不依赖、不进答辩主张**
（答辩口径 §6 相应改：讲「契约稳定性工程」，不承诺缓存命中）。`llm_cache_hit.py` 保留为
后续（换模型/账户、更大前缀）的复测工具。

---

## 10. 数据设计：现有表承载 + 两处该补的缺口（对比 ai4u schema）

> 结论先行：**P0 零新表是正确设计**（框架层不落库、全部聚合派生）；对 ai4u 30+ 张表逐表比对后，
> 真正「该落库没落库」的只有 **① 会话摘要 ② 用量记账**，其余均为「有语义对应、形态不同」。

### 10.1 VocalVerse 现状（LLM 框架读写面，全部既有表，零迁移）

| 数据 | 表/载体 | 说明 |
|---|---|---|
| 场景人设/语料 | `scenarios`（system_prompt/target_corpus 行制式 `phrase\|释义`/difficulty/prompt_version） | 场景即角色（单入口产品，无需 ai4u character 表） |
| 会话 | `sessions`（kind/scenario_id/assigned_turns/turn_count/duration_s） | **无 summary 列** |
| 消息/每轮 META | `scenario_messages`（role/seq/content/audio_url + **meta JSONB**：grammar/coach_note/corpus_hits/difficulty_delta/prompt_version/basis/is_question） | 相当于 ai4u agent_message 的 meta 位（缺 tokenUsage） |
| 词级错误 | `attempts.details.word_level`（error_type/score） | learner 画像词级源 |
| 句级/场景级掌握度 | `user_corpus_mastery` / `user_mastery`（status=not_mastered/in_progress/mastered、mastery_score、attempt/pass 计数） | **学习者记忆的结构化形态**（评分驱动，非对话内容记忆） |
| 动态水平 | `user_skill_state`（est_score/est_level/confidence/60 天半衰期/滞回/低谷保护） | ai4u memory 的「衰减」语义对等物 |
| 画像缓存 | **进程内 dict（TTL 900s）**，不落表 | 聚合派生 + 收尾失效，无需表 |
| 滚动摘要 | **进程内 state.digest（30min TTL）**，不落表 | ⚠️ 见 §10.3 缺口① |

### 10.2 ai4u → VocalVerse 对照（与 LLM/记忆相关表）

| ai4u 表（关键字段） | VocalVerse 对应 | 判定 |
|---|---|---|
| `agent_conversation`（**summary/summaryUpdatedAt/summaryFailedAt**、messageCount、isPinned、lastMessageAt；scene/characterId/campaignId） | `sessions` 部分对应 | **摘要三列缺失 → 缺口①**；其余字段无对应需求 |
| `agent_message`（role/content/**tokenUsage（JSON）**/meta/refs/kind/payload；source=chat\|proactive） | `scenario_messages`（meta 已有） | **tokenUsage 缺失 → 缺口②**；proactive/IM 字段不迁移 |
| `memory`（content/valence/arousal/importance/**activationCount/lastActivatedAt/pinned/visibility**/source=manual\|auto\|chat-tool\|letter\|proactive\|summary/quote） | ✅ 语义对应 = `user_corpus_mastery`+`user_skill_state`+`attempts`（**结构化学习者记忆**） | **不建对等表**：学习者记忆是评分派生数据，半衰期/复习席（rec `review_gap_days` 最弱优先）已覆盖「衰减/激活/探索」语义；valence/arousal/quote 是陪伴产品要素，不迁移 |
| `character`（persona/backstory/toneDescription/toneFeatures/generationConfig/**firstChatAt/lastAutoMemoryAt/proactiveEnabled/status/personalSignatures**） | `scenarios`（system_prompt+difficulty 档位=persona 轻量化；教练双人格 docs/14 §2.2 在 prompt 内） | 不建表（无多角色需求） |
| `character_corpus`（dialogue/lore + chunks） | `target_corpus`（行制式） | 无（few-shot 语料 = target_corpus 本身） |
| `qa_scenario`（profileId/persona/toneRules/citationRules/domainRules/**params JSON**）/ `prompt_template`（scene/template/variables/isSystem） | prompt 模板**硬编码**于 `context_builder._STATIC_TEMPLATE` | P2 可选：如需可管理模板再建 `prompt_templates` 表（ai4u prompt-admin 先例） |
| `usage_log`（source/model/**promptTokens/completionTokens**/meta） | **无**（P3 拍板：仅日志不建表） | **缺口②**：M3 报表时按此模板加表（P3 已登记「M3 报表再定」） |
| TRPG 六表/journal/letter/character_event/scheduled_message/media/conversation_participant/knowledge_base 系/Settings 单例 | —— | 不迁移（产品定位差异，§3 不迁移清单） |

### 10.3 缺口与 P1 建议（待组长拍板）

> **状态（2026-09-03 已实施，迁移 0004）**：① 摘要三列已落库（`sessions.summary/summary_updated_at/summary_failed_at` +
> `SummarizerService` 增量压缩：近 6 条原文 + 更早 40 条窗口/首尾保底/重试 1 次/失败标记，
> 收尾最终总结覆盖写入；**注入 user 尾部 [context]「Rolling summary」**——绝不进 system，
> 见 §9.2 铁证）；② `usage_log` 表 + `log_usage`（source=turn/meta_compensate/summary/conclude）
> + `llm.py stream_rich/chat_with_usage` 用量透传，回合/补偿/收尾/摘要四点记账。

1. **① 会话摘要落库**（ai4u 双轨精华）：`sessions` 加 `summary TEXT` + `summary_updated_at TIMESTAMP`（+可选 `summary_failed_at`）——摘要从进程内 digest 落库后：长会话不失忆、跨会话续聊有基础（M2「刷新恢复 P2 延期」卡的就是此缺口）、失败可自动重试（ai4u summaryFailedAt 系统信号）。**✅ 已完成（迁移 0004 + SummarizerService）**；
2. **③ 学习者画像维持派生不建表**：mastery/skill/attempts 聚合 + 进程内 TTL 缓存已闭环；如 P1 做 **Auto-memory**（每会话收尾把新易错点沉淀为画像更新），可在 `user_corpus_mastery`/衍生表上自然生长，不新增记忆表——ai4u memory 的情感坐标/quote 是陪伴产品要素，与口语训练产品不符。
3. **② usage_log**：**✅ 已完成（迁移 0004 + log_usage）**；M3 报表按本表聚合成本。

### 10.4 P1 摘要双轨只读口径（已实现，供拍板参考）

- 字与轮数：`RECENT_N=6` 原文窗口、`TRIGGER_MESSAGES=4` 增量触发、`SOURCE_LIMIT=40` 压缩窗口、首尾保底 300/100、失败重试 1 次（1.5s 退避）——魔数均标 ai4u 溯源，调整前重估；
- 注入：`[context]` 段 `Rolling summary (earlier turns): …`（会话级稳定段，与画像行同级）；
- 收尾：`complete_session` 以最终总结覆盖 `sessions.summary`（报告快照与摘要列同源）。

---

## 11. Agent Lab 测试指南（怎么用 / 测什么 / 指标口径）

> 入口：`/preview/agent-lab`（前端预览画廊，dev-only）；后端 `APP_AGENT_LAB_ENABLED=true`。
> 本页所有调用走真实 DeepSeek（`.env` 的 `APP_DEEPSEEK_API_KEY`），每次点击消耗配额。

### 11.1 怎么用（三步）

1. `services/python/.env` 加 `APP_AGENT_LAB_ENABLED=true`（Key 已有则直用），重启后端（uvicorn 8000）+ `pnpm dev`（5173）；
2. 打开 `http://localhost:5173/preview/agent-lab` → 画廊点「Agent Lab · LLM 框架测试台」；
3. 默认参数即「Maya 咖啡馆」场景 → 点 **运行单轮**（看单回合样例）或 **连跑 5 轮冒烟**（看会话统计）。

### 11.2 测什么（五类验证）

| # | 验证点 | 怎么看 |
|---|---|---|
| 1 | **system 静态契约** | 任意两次「运行单轮」的 system 原文应**逐字相同**；若不同 → 契约被破坏（POC 铁证：动态进 system = META 0%） |
| 2 | **META 契约与补偿** | 每轮 result 卡：`META OK`（流式直出）或 `META OK(补偿)`；`MISS` = 补偿也失败（检查 Key/网络/补偿 prompt） |
| 3 | **MetaExecutor 命中/收尾** | hits 列表（规则通道应命中目标语料短语）；连跑末轮 conclude=true |
| 4 | **画像/摘要注入** | 第 2 轮起 user 原文应含 `Learner profile` 行；消息 ≥7 条后应含 `Rolling summary` 行（图片行 0~3 条、摘要 ≤300 字） |
| 5 | **用量记账** | 连跑统计 tokens；对照后端 `usage_log` 表逐轮新增（turn/summary/conclude 源） |

### 11.3 指标口径与阈值（页面顶卡同款）

| 指标 | 口径 | 阈值/参考 |
|---|---|---|
| META 直出率 | 流式自带可解析 META 的轮次/总轮次 | 观察值 ≈60%（全上下文）；**不设硬门槛**（补偿是兜底） |
| 补偿后 META 率 | (直出+补偿成功)/总轮次 | **目标 100%**；<80% → 检查补偿 prompt / docs/18 §6 两调用回退预案 |
| 补偿率 | 补偿轮次/总轮次 | **<50% 良好**；持续走高说明主契约退步（对比 docs/26 §9 四臂矩阵） |
| coach_note 有效 | MetaBlock.coach_note 非空占比 | 目标 100%（用户在对话页看到每轮点评） |
| 覆盖度命中 | hits 非空轮次（规则通道，独立于 LLM） | 冒烟场景 2/5 起步即正常；与语料相关性相关 |
| conclude 正确 | 第 5 轮（冒烟末轮）为 true | =true（规则兜底保证，META 只是加速） |
| 往返耗时 ms | 回合总时长（含补偿） | 参考 1~2s/轮（POC-2 first_token 0.41s） |
| tokens | prompt/completion 累计 | 对照 usage_log 表一致（记账验证） |

### 11.4 结论判定

- **PASS**：补偿后 META 率 ≥80% 且 system 逐字一致且补偿率 <50% 且 tokens>0；
- **FAIL 自检顺序**：① META 0% → 看 system 是否被意外改动（契约）；② 补偿率 100% → 检查 prompt 静态块是否含动态值；③ tokens=0 → 后端未启用新代码 / 用旧进程。

---

*状态：拍板完成（§7）。docs/24 A 系列实现方式被本 P0 取代（并入 §8③）但目标不变；docs/24 的 B 系列顺延、许可红线、禁止项继续有效。*
