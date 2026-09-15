# 25 · IB 借鉴落地计划拷问报告（三官火力拷问 · 2026-09-03）

> 对象：`docs/24-InternalBeyond借鉴落地计划.md` v2 → 修订定稿 v3。
> 方式：三路独立子代理对抗式拷问（只读核查，未改任何文件），结论已逐条落进 docs/24 v3。
> 状态：**拷问完成，docs/24 v3 为定稿**；今日执行按 v3 §3。

---

## 0. 总判

| 拷问官 | 范围 | 判定 |
|---|---|---|
| A · 技术/架构 | §1 A 系列（LLM 上下文层） | **需整改**：P0×2 / P1×4 / P2×5 |
| B · 算法/前端 | §2 B 系列（韵律引擎） | **需整改**：P0×3 / P1×4 / P2×若干 |
| C · 范围/排期/合规 | 全局（单人执行框架） | **需整改**：**全量 A+B 今日不可行**，裁决「A 硬底线 + B 骨架」；P1×4 / P2×7 |

**三官一致确认**：方向正确、选型合理、许可合规（只借算法思路，未越 IB PolyForm NC / CC BY-NC-SA 红线）；问题集中在**定义不清导致的实现翻车**与**范围过大**。

---

## 1. P0 清单（必须修，docs/24 v3 已全部落地）

| # | 官 | 问题 | 整改（v3 对应段） |
|---|---|---|---|
| F01 | A | 「语义等价仅调序」为假：拆条会**丢掉 `set conclude=true` 行为指令**、丢 `(none)` 兜底——是重写不是调序 | §1-A1 改「重写」定性；conclude 指令保留进静态块；corpus/hits 保留 `(none)` |
| F02 | A | P1 回归锚点自相矛盾：「只改 user_text」时旧实现 system 也逐字节一致 → 非「修复前必失败」；且要红必须换 state，则整条 messages[0] 又不一致 | P1 改为**两个不同 state**调用，断言 `DYNAMIC_BEGIN` 之前**子串**逐字节一致（整条不要求一致） |
| #1 | B | VAD 单位域混用：帧能量转 dB 后又用线性语义阈值（×4/×0.5/1e-4）→ 纯音用例全判静音、f0=null | §2-B1 作用域规则：VAD/f0 全部线性 RMS 域；dB 只出现在报告端 |
| #2 | B | 特征作用域矛盾：meanDb「有语音帧均值」在全静音时 0/0=NaN；case4 线性 VAD 把 0.2 段判静音 → tailDeltaDb≈0 违背断言 | 能量类特征按**全帧**、VAD/f0 按语音帧；接口注释修正 |
| #3 | B | f0 峰值拾取无去DC/加窗/最小滞后规则：200Hz 纯音在 τ=80/160/240 平局 → `>=` 取到 66.7Hz | 去均值→Hann 窗→归一化自相关→**最小滞后**局部峰；注明 r>0.3 不防倍频 |
| F0-1 | C | **6.5h 完成 A+B 全量不可行**（≈4 人日 vs 7h，超 3.5~4.6×）；§3 只「削字段」不「削模块」 | §0/§3/§8 重排：今日 = A 系列硬底线（内缩 0.9~1.0 人日）+ B 骨架（引擎 + 2 决定性用例）；B 完整、真 Key 冒烟、合并全部顺延 |

## 2. P1 清单（docs/24 v3 已全部落地）

| # | 官 | 问题 | 整改 |
|---|---|---|---|
| F03 | A | weak_words 写 PG 专属 jsonb 聚合，SQLite 单测跑不起来 | Python 侧聚合（select details limit 窗口，Pandas-free 遍历过滤） |
| F04 | A | `error_type != 'other'` 脆弱（空串/词首音素语义不明，会漏判/错判） | 显式白名单（substitution/omission/insertion/mispronunciation/stress/intonation）+ score<60；注记词首音素试探性、真 Key 冒烟核验 |
| F05 | A | 回退「边界下移即恢复原语序仍稳定」不闭环（不可兼得） | 二选一：(a) 完全回退 v1；(b) 保留分组边界前移缩短稳定前缀；注明断言按版本重写 |
| #4 | B | speechRate 恒 null（SSE 不下发用户转写 + B3 不做）→ 死输出 | **本期砍掉**（§0/§2/§8）；随 B3 契约落库再实现 |
| #5 | B | 「语音帧时长」歧义（frameMs=30ms 会让 2.5→1.26 wps） | 定义为「语音帧数×hopMs」；speechRate 已砍，标注待恢复 |
| #6 | B | downmix 断言 ±1% 过松 + 44.1k 非整数步无用例 | 断言 ===16000（顺延用例）+ 加 44.1k 用例 |
| #7 | B | energyCv 除零（全静音 0/0=NaN）；f0Min=60Hz 仅 1.8 周期 | energyCv 全静音=0；f0Min 默认 80 |
| F1-1 | C | 无真 Key 无法证明缓存命中（Fake≠缓存） | PR 描述如实标「Fake 链路验证 + 待实跑」；冒烟判定口径降级 |
| F1-2 | C | 改冻结契约的 review 通道与 grep 前置没入时间块 | §3 step ① 显式 grep；契约走 docs/18 §2 review（非 ADR，F2-2） |
| F1-3 | C | 单人日自审自合违规（docs/05 明令不要） | 今日终点 = push + CI 绿 + **自评 comment（非 approve）** + 挂 reviewer 待审，不合并 |
| F1-4 | C | worklog 日期/置顶错乱（「AI 改错日期」实锤：09-09 条目实为昨日/前日产出） | 已修正：worklog 4 条 `2026-09-09` → `2026-09-02`；docs/24 以 09-03 为执行日 |

## 3. P2 采纳（v3 就地落）

- **F06/F2-1**：`.env` 加载引用不实（deepseek_meta.py 只读 os.environ，全仓无 load_dotenv）→ POC 用 `load_dotenv()`。
- **F07**：learner 行 tradeoff（跨用户共享前缀只到 corpus）在 §1-A1 注明，策略待 POC 数据。
- **F08**：`details.get('word_level')` 非 list/None 防御 + `kind==DIALOG_SPEECH` 过滤。
- **F09**：单进程模型注记（多 worker 时缓存迁 Redis）。
- **F10**：`word_errors` 恒 0（last_errors 从未写入 state.assembled）——今日顺手修（1 行），§8 记录。
- **F11**：POC 不触 per-user 30/h 桶（只占共享 key 配额）；conclud 轮双 LLM 调用未另计桶（既有，记录）。
- **F2-2**：契约变更归类「实现」：无需 docs/06 新增 ADR；走 review + docs/14 §3.4 回写 + prompt_version=2 登记；docs/06 §7 补一行（建议非阻断）。
- **F2-3**：合规姿态强化：prosody.ts 文件头与 docs/24 注明「算法概念源自 IB `_vmToneAnalyze`（12952–13092），独立重写，未拷代码/素材」。
- **F2-4**：教练双人格引用章节修正（docs/14 **§2.2** 非 §2.4）；注入措辞向「轻纠正 + 重复盘」靠拢（role 行为层微调，非 coach 层）。
- **F2-5**：prosody.ts 与 docs/23 选型 **pitchy（实时 F0）** 分工注明：离线分析 vs 实时反馈；今日交付无 consumer 的引擎资产，UI 接入学 docs/23 phase5。
- **F2-6**：边界声明：prosody=语音韵律；唱歌音准=后端 pyin+DTW，勿混用。
- **F2-7**：新增 §9 答辩口径（prompt 组织 / 韵律来源与许可 / 为何不直接用 IB / B 为何骨架）。
- **F2-8**：拷问结论落 docs/25（本文档）+ README 登记 + docs/24 状态「v3 定稿」。

## 4. 今日硬底线交付物（C 官裁决，做完即算成功）

1. A 系列核心：`build_llm_context` 拆条（重写口径）+ `learner.py` + Settings + `_post_session_skills` 失效挂钩 + word_errors 顺手修；
2. A 系列 6 pytest 红→绿（P1 修正版锚点 / P2 / P3 / P4 / P7 / P8）；
3. `scripts/poc/llm_cache_hit.py`（dotenv + 无 Key skip 走通，不实跑）；
4. docs 同步：docs/14 §3.4 回写 + README + docs/25 + worklog 置顶署名（执行人 LHRCarrier）；
5. 全量门禁绿；
6. PR1 就绪（3 commits 分开）+ 自评 comment + 挂 reviewer 待审（**今日不合并**）。

**可选**：B1 引擎骨架 + 2 vitest → PR2（同样待审）。

**明确顺延**：B 完整 6 用例与 f0 细节；A 真 Key 冒烟；契约评审合并；报告页接入学 docs/23 phase5；B3 契约落库；speechRate 与语速标定。

> **组长拍板（2026-09-03，追加）**：LLM 框架优先——B 系列（含骨架）**整体顺延**，今日只做 A 系列（详见 docs/24 v3.1 执行框架与 §3 时间块），且 A 系列新增「真 Key 验证」为框架落地的关键一步（POC-2 与缓存命中实跑）。

## 5. 事实核查修正记录（执行前已对齐）

- 日期：今日 = 2026-09-03；worklog「2026-09-09」4 条标题为误标，已更正为 2026-09-02。
- `.env`：全仓无 load_dotenv；POC 脚本须自行加载（python-dotenv 已是依赖）。
- 教练双人格：docs/14 **§2.2**（原文被误引为 §2.4）。
- B 侧事实：vitest 环境 = happy-dom（无 Web Audio，纯 Float32Array 方案正确）；recorder 产 webm/opus；仓库无现成音频缓冲工具；SSE 无用户转写字段（speechRate 死输出实证）。

## 6. 结论一句话

**docs/24 v3 可执行**：今日硬底线 = A 系列 PR1 就绪待审（无 Key 如实标注、不合并）；B 系列降级骨架；三官全部 P0/P1 已按上表落进 v3，无遗留未整改项。
