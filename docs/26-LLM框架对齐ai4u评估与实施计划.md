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

*状态：拍板完成（§7）。docs/24 A 系列实现方式被本 P0 取代（并入 §8③）但目标不变；docs/24 的 B 系列顺延、许可红线、禁止项继续有效。*
