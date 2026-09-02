# VocalVerse · 工作日志

> 团队可见的工作记录（入库）。负责维护：LHRCarrier（组长）；其他成员需补充时经 PR 追加到 `VocalVerse工作日志.md`。
> 用途：按日记录项目关键改动、验证结果与踩坑；新记录追加在最上方。正式决策看 `docs/06-技术框架决策.md`（ADR 唯一权威）。

## 2026-09-07 Java 启动日志两坑修复（安全密码 WARN + spring-boot:run 中文乱码）

用户实测暴露两个启动问题（commit `5ad2c8c` + `16a4e6b`）：

1. **「Using generated security password」WARN**：项目是自定义 JWT 过滤器 + BCrypt（AuthController 自己校验），从不创建 `UserDetailsService` bean → Boot 的 `UserDetailsServiceAutoConfiguration` 兜底生成随机密码并打误导性 WARN。已 `exclude UserDetailsServiceAutoConfiguration` 消噪（测试证明 SecurityConfig 一直生效：链路失效则 /auth/** 被默认 basic auth 拦截，AuthFlowTest 必挂）。
2. **DemoSeeder 中文乱码（verify 正常、spring-boot:run 乱码）**：logback sett UTF-8 字节后，**mvn spring-boot:run 的 fork 子进程 stdout 经管道由 Maven 主进程按平台编码（GBK）解码** → UTF-8 字节被读错乱码；surefire 转发路径无此环节所以 verify 正常。修复三层对齐：`logback-spring.xml charset=UTF-8` + `.mvn/jvm.config -Dfile.encoding=UTF-8`（Maven 主 JVM）+ `spring-boot-maven-plugin jvmArguments -Dstdout.encoding/-Dstderr.encoding=UTF-8`（fork 子 JVM）。Linux/容器无影响（本然 UTF-8）。
3. 门禁：`mvn clean verify` 全绿（15 tests + spotless + 契约对账）。

**踩坑（并入 32 待登记）**：Windows 中文编码是「字节流向 × 每层的解码器」问题——logback 只管字节（charset），Maven 管道转发按自己编码解码；修编码先分清「哪层转码」再动手，单改一层必然残留（第一轮只加 logback charset 时 verify 好了 run 没好的原因）。

## 2026-09-07 Java 包结构按 Package-by-Feature 规范重整（专家子代理审计 + 实施）

**触发**：组长检查发现上轮「Controller 统一收 controller/」后分层不明确（Controller 按层、Entity/Repository 按域 = 混合分层）。派专家子代理审计（35 主 + 9 测文件全量清单为输入，结论可复现）：

- **诊断**：① 混合分层割裂——同域端点被拆到无归属层包（工单 = controller/TicketController + ticket/ 两地）；② ContentAdmin/QuestionAdmin 同属 content、InternalLevelController 实属 user，包名表达不了域归属；③ SecurityConfig/JwtService/JwtAuthFilter 是全局安全编织却塞在 auth 域；④ 测试主/镜像不一致（PingController 主在 controller/、测试在 health/）；⑤ AbstractAdminApiTest 跨域共享却放层包。
- **方案（唯一推荐）**：Package by Feature——域内自包含（`域/controller/` 子包 + 域根 entity/repository），跨域安全/种子上移 `config/`、健康探针归 `health/`、共享视图 DTO 归 `ticket/dto/`；测试镜像到 `域/controller/` + `support/` 基座。豁免项：薄端无 service 层（唯 AuthController 的密码/refresh 逻辑越界已标记，后续可选抽 AuthService）、controller 内嵌 record DTO（跨端点复用的仅 TicketView 例外）。
- **实施**：`117beef`（主代码 13 移 + 测试 4 移，git 识别 rename 90~100%）+ `28b5448`（测试镜像 import 同步）。**外部可见性零变化**：@RequestMapping 与内嵌 record 字段未动，`ContractSnapshotTest` 逐字通过（springdoc tag/operationId 不依赖包路径），前端契约/类型无需刷新。
- **门禁**：`mvn clean verify` 全绿（15 tests + spotless + 契约对账）。

**踩坑 31（实施自伤，已恢复）**：第一轮用 PowerShell `[regex]::Replace(..., "package $pkg;")` 替换 package 行——`.NET 正则替换的 replacement 中 `$pkg` 被解释为命名组引用`，导致整个文件被静默置换破坏（实测表现为源码字符错乱）→ 全量 `git checkout` 回滚后改用 `git mv` + **字面 `.Replace`（无 `$` 语法）** + 每步 `Contains` 校验，一次通过。教训：**批量改文本用字面替换 + 校验；正则 replacement 的 `$` 是陷阱**；另 `git mv` 会立刻 staged，别再用 `git add` 分批攒 commit（本次导致测试 rename 混入主代码 commit，无功能影响但分类不纯）。

## 2026-09-07 系统设计 Day1：架构设计说明书 + 接口设计说明书（docs/20、docs/21）

### 任务与产出

按分工（09/07，A 全天）：系统架构设计（分层、服务边界、写方唯一性约束、数据流图）+ 接口契约梳理（OpenAPI）。产出《系统设计说明书》两份分册（09/09 设计评审交付）：

| 交付物 | 文件 | 要点 |
|---|---|---|
| 架构分册 | `docs/20-系统架构设计说明书.md` | 系统上下文 DFD（mermaid）+ 五层划分 + 应用内三层端分层（route/service/port/adapter + 禁止规则 R1~R6）+ 服务职责边界表（含「新功能落位判据」）+ **表级单写方矩阵**（19 表 × 写方 × 现状代码）+ **守护机制设计 M-1~M-4**（DB 双角色 vv_python/vv_java/vv_seed、CI 静态探针、seed 只增不改 + slug 键、评审打回）+ 回合目标态时序图 + 报表流 + 写方边界图 + **D1~D14 设计决策/现状差异/排期表** |
| 接口分册 | `docs/21-接口设计说明书.md` | 双快照对账：Python 20 ops / Java 6 ops 端点总清单（方法/路径/鉴权/限流/备注）+ SSE 回合契约（事件序列）+ **内部 REST 契约正式登记**（`POST /internal/level`：userId 键名/3s/幂等/调用方义务/双侧契约测试）+ 整改项 **R-1~R-16** 登记表 + 错误码对账 + 契约变更流程 |
| 错误码补登记 | `docs/api/error-codes.md` | 补 40902/40903/41001/42202（代码已用未登记）+ 40901 预留 + 40301 语义扩注（越权统一按不存在处理） |

### 现状盘点结论（先答「有没有做过类似工作」）

- **分层/服务边界**：docs/06 §1、§2 已有文档级拓扑与职责表，但无设计说明书成文；docs/19 §1.1 是评审口径的现状速写（非设计）。
- **写方唯一性**：docs/10 §3 矩阵 + §5 细则已相当完整，但 **P0-7 实锤只有文档没有机制**：`seed.py` 直接写 Java 独占表（scenarios/placement_questions）、两服务共用同一 DB 账号、无任何守护。
- **数据流图**：此前**从未做过**正式 DFD（全仓无 mermaid/drawio），今天补齐 4 张（上下文/回合时序/报表流/写方边界）。
- **OpenAPI 契约**：基础设施此前已远超小组水平（双快照 + openapi-typescript 生成 + CI 三关卡 + refresh-openapi.ps1 + docs/06 §7），本次补的是「设计先行」的接口清单、内部 REST 契约与对账落地。

### 对账发现（2026-09-07 代码实测，全部登记进 R-1~R-16 / D1~D14）

1. **Python OpenAPI 快照中没有任何 operation 带 `security`**：practice/placement/defense/events 的 `Depends(get_current_user_id)` 因用 `Depends` 而非 `Security` 未进 OpenAPI；`/asr /score /tts /llm/chat` 四端点是真的裸奔（与 docs/19 P0-4 一致，未修）。
2. **docs/19 的 9 个 P0 经复核全部仍在**（2026-09-07 重查代码：进程内状态、同步 Session 跨 SSE、三处越权、裸接口、串行 TTS、`user_id` vs `userId`、seed 违例、reports 非 upsert、默认密钥/网关可达）——排期见 docs/20 §6 表（9/10~9/11 集中返工承接）。
3. **三处文档与代码不符（新发现）**：① docs/06 §7 写 `/api/auth/refresh`，实际网关路径 `/manage/auth/refresh`（R-15）；② docs/06 §7「评分 30/h」，代码 `ise_rate_per_hour=60`（R-16）；③ 错误码表落后代码 4 个码（本次已补）。
4. **快照口径修正**：Java 快照是服务原生路径，**对外契约以网关 `/manage/` 前缀为准**（docs/21 §2.2 已加说明）。

### 踩坑记录（追加第 29 条）

29. **「文档声称」必须与「代码事实」三方对账，不能拿 docs/06 当事实**：本次盘点靠逐条提取快照（PowerShell ConvertFrom-Json 列 paths + security）+ 关键行 grep 复核，发现 3 处 docs/06/docs/api 与代码不符（refresh 路径、ise 桶、错误码缺失）——这些差异如果只读文档永远不会暴露，而它们恰恰是接口设计说明书的「对账结论」最有价值的部分。做法：快照为唯一基准列端点，代码为唯一基准列鉴权/限流/字段名，docs 为第三列对比。

### 同日补记：Java 薄端管理端提前落地（超出分工计划）

把盘点出的 Java 缺口（admin 角色链路 / 用户管理 / 内容库 CRUD / 工单）全部实现，从 9/14~9/15 计划提前到设计日完成：

| 提交 | 内容 |
|---|---|
| `c8cbba2` | feat(java)：管理端最小集 —— JWT 加 role claim + `/api/v1/admin/**` hasRole(ADMIN)；用户管理（列表/详情/禁用启用/档案，改档 source=manual）；scenarios/songs/lrc/listening_materials/placement_questions 实体+CRUD（DELETE=归档；LRC 整首重写 → seq 重排 + pitch_ref_status→missing 触发 Python 重提取；题库 exam_revision 版本化 + 重复题 409）；工单（用户提交/我的 + 管理侧前向状态机 open→processing→resolved→closed，回复即认领）；Controller 按 Spring Boot 分层规范统一收 `controller/` 包，entity/repository 按域 |
| `b684e44` | test(java)：AdminUser/Content/Ticket 三组 API 测试（15 tests 全绿含既有） |
| `07a28a4` | chore(contract)：Java 快照 6→33 ops + `pnpm gen:api` 前端类型（现有调用零改动） |

门禁：`mvn verify` 全绿（15 tests + spotless + ContractSnapshotTest 对账新快照）；`pnpm typecheck` 通过（前端类型无破坏）。

### 踩坑记录（追加第 30 条）

30. **MockMvc `content(String)` 不是 UTF-8；Java 文本块里的 `\"` 是转义不是字面反斜杠**：单测两连坑——① 请求体含中文时 `content(String)` 按平台编码（ISO-8859-1）传输 → Jackson `JSON parse error` 400，必须 `content(body.getBytes(StandardCharsets.UTF_8))`；② 文本块（`"""`）中想表达 JSON 的 `\"` 实际是 `"`（转义生效），导致 `"interestTags":"["daily"]"` 这类 JSON 断裂——测试用 `[]` 或 `\\\"`。另：`git commit --amend` 会改 HEAD（上次 commit）不是任意 commit，错点后要用 `reset --soft` 重排队列。

---

## 2026-09-02 lieflat-charts 表盘美化（预览高保真）：按技能选型规则出图，不"接入"库

### 背景与产出

用 [lieflat-charts](https://github.com/larashero3-dotcom/lieflat-charts)（AI Agent 用的数据可视化 Skill：
`SKILL.md` 选型法典 + gallery 正本模板）为 VocalVerse 表盘数据做美化，示例数据口径与 docs/06 §9.1 一致，
先出 preview（docs/13 §8：静态高保真 → 视觉验收 → 集成真实 view）：

| 交付 | 文件 | 模式 / 体系 | 选型 |
|---|---|---|---|
| 管理端评价看板 | `apps/web/src/assets/lieflat/vv-admin-dashboard.html` | 图表模式 · Glance × PORCELAIN | 四指标 KPI 卡 + G8 / G3 / G4 / G13 / G14 |
| 用户端学习报表 | `apps/web/src/assets/lieflat/vv-learning-report.html` | 报告模式 · R09 骨架 × PORCELAIN | 雷达（SKILL §7 例外）+ F2 / F4 / L15 + KPI 栏 |

- 预览入口：dev 环境 `/preview/lieflat`（前端预览画廊，生产构建自动剔除）；渲染组件
  `src/components/LieflatChart.vue`（sandbox iframe + srcdoc + postMessage 高度桥）。
- 选型审计记录（含全部淘汰理由）与许可说明：`apps/web/src/assets/lieflat/README.md`。

### 关键点

1. **这是"用技能出图"，不是把库接进产品**：交付物是两份单文件 HTML，与前端渲染机制解耦；
   M3 真实接口落地后替换数据即可，届时再决策"iframe 渲染 vs 移植 Vue SFC"。
2. **选型按 SKILL.md 硬约束**：看板 = 用户明确要 dashboard → Glance 系入场（Lupi/Basics 不适配理由
   已记录）；报表 = 报告模式 R09（淘汰 R12 依赖最重 / R03 无 KPI 槽位 / R05 密度不足 / R11 定尺太窄）；
   页内图全部复用 gallery 正本结构（图脚标 REAL TEMPLATE），雷达按 §7 例外用 ECharts 原生换肤。
3. **许可 ⚠️**：上游为 PolyForm Noncommercial 1.0.0（仅限非商业用途）。本项目作实训项目使用没问题；
   **若未来商用，须向作者申请授权**，或在 M3 集成前重绘（ADR 决策点）。
4. **踩坑 28（SFC 字面 `</script>`）**：`LieflatChart.vue` 桥接脚本字符串里的关闭标签必须写
   `<\/script>`（反斜杠转义），且 **doc 注释里也不能出现字面 `</script>`**——@vue/compiler-sfc 按
   字面序列切脚本块，注释里的字面串把块切在 40 行，报"`*/` expected"。另一处踩坑：交付 HTML 的
   内联脚本按 SKILL 自检 7 用 `node --check` 抽检，抓到雷达 legend `fontFamily:'Inter','Noto Sans SC'`
   逗号语法错误（改 `'Inter, Noto Sans SC'`）。

---

## 2026-09-01 实训作业四件套 + 六路拷问：从"能不能跑"到"该不该这么做"的补课

### 背景与产出

今日要求：需求调研文档（含 2 份竞品分析）+ 项目计划 + 四件套（立项/计划/调研/SRS）在需求评审前交付。MVP（M1+M2）已于今日之前完成，因此本日核心工作量在**产品侧拷问**而非开发——派 6 个子代理对已实现系统火力全开拷问，产出归档于 `docs/19-*.md`，交付物在 `local/9月1日实训作业/交付物/`：

| 交付物 | 文件 | 说明 |
|---|---|---|
| 需求调研报告 | 01-需求调研报告.md | 用户画像 3 个、竞品深度分析 2 份（流利说/Speak，B/C 分工）、功能矩阵、P0~P2 决策 5 条 |
| 项目立项报告 | 02-项目立项报告.md | 按 Project Start Report 模板；工作量 62 人天（模块口径）/72.5 人天（全项目口径）；风险登记 15 条 |
| 项目计划（简版） | 03-项目计划（简版）.md | 按 SPP 模板；WBS 24 工作包 + 19 日甘特图；产能缺口 40% 四层应对 |
| 需求规格说明书 | 04-需求规格说明书.md | 全量功能需求 + 验收标准 + 可追溯矩阵 + 代码级缺陷清单 C-1~C-16 |
| 产品功能说明书 | 05-产品功能说明书.md | 万玄阁章法：19 章，功能 + 系统 + 算法 + 合规全量 |
| 项目组成员分工 | 06-项目组成员分工.md | 万玄阁体例：现状/目标/阶段/逐日任务；A/B/C 代号 |

### 拷问结论（六份报告的交叉印证）

- **产品**：选题成立但定位必须收敛（全年龄段 → 以有 deadline 的真实开口事件为锚点）；唯一真壁垒 = 评分与真人评委 r≥0.7；40 条语料 30 分钟打穿（已复核实）；唱歌转影子跟读、推荐降级规则、答辩导师泛化。
- **UX**：FTUE 8 步 90~120s（目标 ≤20s）；■ 假按钮等 9 项 P0，修复清单 ≤2 人日。
- **架构**：9 条 P0（进程内会话、同步 DB 连接、三处越权、裸接口无鉴权、首声 6~7.6s、跨服务字段名错断、默认密钥等），最小修复集 5~6 人天；结论「撑到交付、撑不到上线」。
- **商业**：单轮成本中位 ¥0.67（TTS 42% + ISE 27% + 审核 14% + LLM 仅 7%）；1 万 DAU 月烧 16.6~124.6 万；免费用户成本须压到 ≤¥1/月；B 端是唯一 LTV/CAC 成立的路径。

### 本轮顺带修复（代码级，全部亲验）

1. **PracticeView `NCard` 未注册**（UX 拷问 P0-9）：模板用 `<NCard>` 但 import 缺失，评分卡渲染残缺。全仓复扫仅此一处，1 行修复已推送 main（8a0dd0b）。
2. 六条代码级实锤亲自复核通过：报告越权（`get_report` 无归属校验）、跨服务字段名不匹配（`user_id` vs `userId`，定档回写 100% 断）、默认密钥入库、24h 清理未实现（仅惰性过期）、音频 sha1 明文平铺、前端零隐私组件。

### 踩坑记录（追加第 27 条）

27. **子代理结论必须抽查，不能直接采信**：6 份拷问报告共 400KB+，引用几十处「文件/行号」。本轮对其中 6 条高影响断言逐一回读代码验证——全部属实（含 P0-6 字段名这种"整链路坏掉但全仓测试绿"的案例），但过程说明：**引用行号的论断验证成本极低（一次 grep），不验证就直接写进交付文档是对评审负责的失职**。另一个坑：子代理写入的路径要复查（本次六份报告初次落盘在仓库根目录，后续方归档到 docs/；早先一次转换脚本曾把 0 字节文件写到仓库根，已清理）。

---


### 背景

PR #22（Faust-sudo，入学测试录音停止键）复审后发现补丁自身仍有三条破的边界路径，已整改（详见 `worklog/BUG实测/入学测试功能测试.md` BUG-001-R）。本条记录后续三项收尾。

### 1. 停止键修复推广到 Practice / Defense

BUG-001 踩坑记录 3 已标注这两页同模式。本轮统一：

- `DefenseView.startAnswer()` 与修复前的 Placement **逐行同构**（`if (recording.value) return` + 无 try/catch），两个 bug 全中；
- `PracticeView.startRecording()` 的守卫是 `phase !== 'ready'`，而 `phase` 在录音期间仍是 `'ready'`（只在 `sendTurn` 内才翻 `'busy'`），所以点 ■ 会重入 `startRecording()` 并被 `recorder.start()` 内部的 `state === 'recording'` 守卫吞掉 → 停止键同样失效。

两页改为与 Placement 一致的「录音中 `stop()` / 启动窗口 `cancel()`」二选一，并接上 `micErrorMessage` 与 `MIN_RECORD_MS`。

### 2. 服务端音频下界（40002）

前端停止键修好后，**误触第一次成为可能**：原先停不下来，录音时长恒等于 15s。新增 `app/audio/upload.py::validate_audio_bytes` 统一上下界：

- `placement.py`：**校验前置于限流扣减**——空录音不该消耗 ASR/ISE 配额，也不该推进题目；
- `practice.py`：带音频的回合先校验（空录音会推进 `current_turn` 且不可重来）；
- `/asr` `/score` 是无状态管线端点，保持 `min_bytes=0` 的历史行为，只共用上界实现。

> **残留（已知未修）**：`practice.py` 的限流是 FastAPI `Depends`，依赖先于函数体执行，故该路径上配额仍先于下界校验被扣。要修需把 `consume` 移进函数体，会牵动既有 429 用例，本轮未做。

### 3. ⚠️ `frontend-ci` 与 `python-ci` 从未真正执行过

排查 PR CI 状态时发现两条工作流 `conclusion=failure` 但 **`jobs.total_count = 0`**——启动即失败，一个 step 都没跑。根因是 YAML 语法错误：

```yaml
- name: Contract: OpenAPI snapshot in sync    # ← 未加引号的标量里出现 ": "，非法
```

用 `yaml.safe_load` 逐个解析五条工作流：**恰好只有这两条 INVALID，也恰好只有这两条 jobs=0**，其余三条（java-ci / secret-scan / docker-build）正常。加引号后五条全部解析通过（python-ci 9 steps、frontend-ci 10 steps）。

这意味着此前所有「门禁全绿」的结论（含上一条日志 2026-09-01 表格里的那一行）**都只是本地跑的**，GitHub 上这两条从来没验证过任何东西。顺带修掉门禁真正跑起来后立刻会红的一处存量问题：`alembic/versions/0002_m2_practice.py` 未过 `ruff format --check`。

已按 CI 的九/十个步骤在本地逐条复跑：ruff check / ruff format --check / uv lock --check / pytest 45 / OpenAPI 契约快照一致 / alembic 单头 / pnpm gen:api 无漂移 / lint / typecheck / vitest 18 / build —— 全绿。

### 踩坑记录（追加第 24~26 条）

24. **CI「红」和 CI「没跑」是两回事**：`conclusion=failure` + `jobs.total_count=0` = 工作流启动失败，一个 step 都没执行。只看 PR 页面的红叉会误判成「某个测试挂了」。**排查工作流问题第一步查 jobs 数量，而不是翻日志**（日志根本不存在，`gh run view --log-failed` 会报 log not found）。
25. **YAML 未加引号的标量里不能有 `": "`**：`name: Contract: OpenAPI snapshot in sync` 会被当成嵌套映射 → 整份工作流非法。这与踩坑 14（块标量里 `#` 不是注释）是同一家族：**YAML 的字符串比看上去更需要引号**。约定：step `name` 只要含 `:`、`#`、`{`、`[` 一律加引号，并在改动工作流后本地 `yaml.safe_load` 过一遍。
26. **修好一个限制会解锁新的输入域**：停止键不可用时录音恒为 15s，修好后 200ms 的误触第一次成为可能，而上传即推进题目/回合且不可重来。**新增能力要同时补上它放开的输入域约束**（前端 `MIN_RECORD_MS` + 服务端 40002 双侧）。

---


### 背景

- M2 全量合入后，按 README 方式 B 本机启动（三端 + PG/Redis 容器），浏览器实测登录/对话，一组**只在"经网关 + 浏览器"路径上才暴露**的坑连爆（同日）。排障方法论沉淀：**同一症状逐层二分（直连 8080 / 经 5173 网关 / 浏览器 DevTools Network），每层换一个变量再测**。

### 排障链（症状 → 根因 → 修复）

1. **登录 403 + 空响应** → ① Java 控制器误把路径写成 `/manage/auth`（网关 nginx/Vite 剥离 `/manage` 前缀后变成 `/auth/login`，无匹配）；② 更深一层：Spring Boot 3 默认把 `/error` 错误转发**也纳入安全过滤链**，控制器抛错（401/404）先跳 `/error` 而 `/error` 不在 permitAll → 任何异常都被织成 403 空响应。**修复**：控制器路径去掉 `/manage`（与 PingController `/api/v1` 同语义）+ `/error` permitAll；已在线验证：正确账密 200，错账密 401 带 JSON 体。
2. **登录后对话 401 missing bearer token** → ① SSE 回合走 `openSseFetch` 直连 fetch，**绕过了 `request()` 的自动 `Authorization` 注入**；② 更隐蔽：`bootstrapAuth()`（localStorage→全局 token 恢复）**从没接线到启动流程**——任何一次 F5 之后全局 token 为空，全部 API 401（"重新登录又好、刷新又挂"的元凶）。**修复**：`openSseFetch` 支持 headers + `streamTurn` 带 `authHeaders()`；`main.ts` 启动调用 `bootstrapAuth()`。
3. **连续对话报 stale turn 409** → 提示卡"继续对话"发出**无音频 hint 回合**：服务端早退分支**不推进 `current_turn`**，而前端**任何 `turn_end` 都 +1**——计数器双写不同步，下一轮 `expected_turn` 失配。**修复**：服务端 hint/demo 回合落库并推进轮次（兜底）；前端示范/提示卡改为**仅播音频 / 直接录音**（回合只在录音后发生），横幅按钮改「🎙 试试说 / 🔊 示范」。
4. **启动报错三连**：`uv run uvicorn` 报 WinError 10013（8000 被旧实例占用，非 bug）；`alembic` 命令不识别（Windows 下 `uv run` 不激活 venv，裸命令不在 PATH）；seed 报 `password authentication failed`（`.env.example` 的 DB 密码是占位符 `change-me-db-password`，与 compose 默认回退值 `vocalverse-dev` 失配）。**修复**：`.env.example`/根 `.env.example` 默认值对齐 compose 回退；README 命令加 `uv run` 前缀 + FAQ 三行。
5. **Java 日志中文乱码**（`婕旂ず璐`）→ 双重错位：pom 未声明 `project.build.sourceEncoding`（GBK 系统按平台码读源文件）+ 终端码页 cp936。**修复**：pom 钉 UTF-8 + `chcp 65001` / `-Dstdout.encoding=UTF-8`（README FAQ）。

### 踩坑记录（追加第 16~23 条，与前文 15 条连续编号）

16. **网关剥离前缀 vs 控制器路径**：Java 控制器若带 `/manage` 前缀，MockMvc/直连 curl 永远测不出（都能 200），**只有经 nginx/Vite 网关才暴露 403**。约定：Java 侧路径一律不带 `/manage`（网关剥离后命中），与 PingController 语义一致；改路径必同步：SecurityConfig 匹配器 / ServiceTokenFilter / Java 测试 / Python 回写 URL / 联调脚本。
17. **Spring Boot 3 的 `/error` 也在安全链里**：自定义 `SecurityFilterChain` 后，任何控制器异常 → `/error` 转发 → 不在 permitAll → 织成 **403 空 body**（前端 `JSON.parse` 报 "Unexpected end of JSON input"，症状与真 403 无法区分）。**处置**：`/error` permitAll；排障时看 DevTools 响应体是否为空是判别信号。
18. **直连 fetch 绕过公共客户端**：`openSseFetch` 这类专用请求路径必须显式携带 `authHeaders()`——**公共 `request()` 的鉴权不是全局中间件**；同理 `bootstrapAuth()` 必须接线（main.ts），否则刷新即丢全局 token。
19. **计数器双写不同步**：同一"轮次"概念在服务端（当前轮）与前端（已收 turn_end 数）各维护一份，任何分支（hint/demo/错误降级）少推/多推一侧都会产生 stale turn；**原则：turn_end 的发送方 = 轮次推进方**，前端按事件数累加。
20. **Vite 只绑 ::1**：`127.0.0.1:5173` 打不开但 `localhost:5173` 正常——不是错误，IPv6-only；排障时别把「localhost 通、127.0.0.1 不通」当异常。
21. **`.env.example` 占位符 vs compose 回退值**：`change-me-db-password` 与 `${POSTGRES_PASSWORD:-vocalverse-dev}` 失配 → 复制即用必炸；**默认值必须与 compose 回退一致，且改密码三处同步**（compose 环境变量 / services/python/.env / 根 .env）。
22. **Windows 裸命令不在 PATH**：`uv run` 不激活 venv——`alembic/uvicorn/pytest` 一律 `uv run` 前缀，README 已全部修正。
23. **Java「编译期 + 运行期」双重编码**：pom `sourceEncoding=UTF-8`（编译期）+ `chcp 65001`/`-Dstdout.encoding`（运行期）；缺一都会乱码。另：**jar 被运行进程锁定**时 `mvn package` 报 `Unable to rename ... .original`——先停 Java 再打包（Windows 文件锁）。

### 验证状态（本日结束时）

| 路径 | 结果 |
|---|---|
| 5173 网关登录（demoadult） | 200 + Token ✓ |
| 错账密/未知用户 | 401 带 JSON 体（不再是 403 空响应）✓ |
| 对话回合（含连续 5+ 轮） | SSE 事件完备，无 stale turn ✓ |
| 刷新页面后功能 | token 恢复接线，不再 401 ✓ |
| Python/FE/Java 门禁 | pytest 41 / ruff / typecheck / vitest 8 / build / mvn verify 全绿 ✓ |

### 提交管理（main 线，全部管理员直推）

```
7a6143f fix(practice): 无音频回合计数器同步 + 示范/提示卡只播不发送
90f6941 fix(web): SSE 携带 JWT + 启动恢复会话 token
218049a fix(auth): /error 加入 permitAll（401/404 不再被织成 403 空响应）
69b0bd4 fix(auth): Java 控制器去 /manage 前缀（网关剥离语义对齐）
1aa72e2 fix(java): 钉死 UTF-8 源码编码 + FAQ
5007caf fix(dev): 启动指引默认值对齐（DB 密码 / uv run 前缀 / FAQ）
9a0b3a6 docs: DoD 验收清单勾选
323c581 docs(worklog): M2 实施记录（踩坑 1~15）
（本条目 → 追加为最新）
```

每个修复 = 一个 commit（可回滚、可 review），无 squash 粘连；本条目单独成 commit。

---

## 2026-09-01 VocalVerse · M2 实施落地——双子拷问收敛 → 全链路实现 → 真环境联调（DoD 全绿）

### 背景

- 对组长 M2 场景对话草案（v1）派 **双子拷问官交叉拷问**（互不知晓、四层递进至穷尽）：需求/产品官 28 问（docs/15）+ 技术/架构官 37 问（docs/16），合流拍板记录 docs/17；规格修订为 docs/14 v2；实施计划 docs/18。
- 拍板关键项：答辩 M2 W3 极简版 / defense_profiles **软删+脱敏** / 回答质量改**等级标签**（避开 docs/06 §9.3 冲突）/ LLM **流式回复 + `[-META-]` 尾部标记**（修复"假流式"首声超预算）/ 覆盖度口径（5 条、命中双态、retry 作废）。

### 实施（按 docs/18 §3，3 人分工由组长一人代跑）

1. **W1 前置**：3 个 POC 脚本（scripts/poc/：edge_tts_latency / deepseek_meta / whisper_rtf）+ 8 套场景内容（data/seed/scenarios.json：4 场景×入门/进阶，每套 5 语料含中文释义）+ 幂等 seed.py（含入学测试题库 5+1）。
2. **Python**：迁移 `0002_m2_practice`（defense_profiles 新表、sessions.kind/attempts.kind/scenario_messages.action(+hint)/events.event_type(10 类)/reports.scope(+session) 五处 CHECK 扩展、sessions.profile_id SET NULL、**defense 题数复用 assigned_turns 快照**）；编排器 app/practice/（回合状态机、流式 text_delta + META 尾部拆解、评分并行、命中双态、2 级救场、会话锁、覆盖度）；答辩（异步知识包生成 6 条校验 + basis 提问依据 + `<untrusted_input>` 注入隔离 + 等级阶梯）；路由 10+（sessions/turns-SSE/reports/GET audio 鉴权+410 惰性过期/defense profiles/placement/events 幂等埋点/限流分桶）；真实客户端 DeepSeek/edge-tts/faster-whisper/讯飞 ISE（重依赖延迟导入，CI 零 Key 纪律不变）。
3. **Java**：Spring Security + jjwt 认证最小集（register/login/refresh rotation/me/service-token 内部回写）；DemoSeeder 3 画像账号（demoadult/demoteen/demosenior，密码 demo123456）；HS256 与 Python 手写验签对齐。
4. **前端**：sse.ts 重写（fetch 流解析器，6 单测）+ recorder 参数化 + 计时器 composable + auth store（pinia）+ 埋点封装；PracticeHub / PracticeView / ReportView / DefenseView / **PlacementView**（5 句+1 QA→综合分 S→水平档）；预览页平移后**删除+撤登记**（docs/13 §8 纪律）。
5. **基础设施**：compose 一键 migrate 服务（alembic+seed）、python `--workers 1` + mem_limit 2g、Dockerfile `--workers 1`。

### 验证（全部实测）

| 检查 | 结果 |
|---|---|
| Python pytest | **41 passed**（含 M2 核心 20+4 seed+10 类事件防漂移）；ruff check + format ✓ |
| Java `mvn verify` | BUILD SUCCESS（认证流程 3 用例 + 既有 5）；契约快照已重刷 |
| 前端 | typecheck / lint / vitest **8 passed** / **build ✓**（p5 独立懒加载 chunk） |
| 契约 | python/java 双快照已重生成，gen:api 零 diff 口径保持 |
| **真 PG** | alembic upgrade head（0001+0002）✓；**alembic check 零 diff**（首次启用） |
| **真环境联调**（scripts/poc/integration_check.py） | Java 登录→Python 验签互通 ✓ →场景 8 套/会话 ✓ →**真实 whisper 转写完整无误** ✓ →真实 edge-tts 4 段音频+回放鉴权（200/越权 401）✓ →报告 ✓ →埋点 SQL 核对（8 类非零）✓ |
| POC-1（edge-tts 延迟） | 单句 mean **1.34s** / 3 句串行 4.12s → **FAIL 判据**，回退方案生效：并发预热+预合成开场，首声口径 3~6s |
| POC-3（whisper RTF） | mean RTF **0.328**（短）/ **0.258**（长）→ **PASS**，演示话术「3~5s」成立 |

### 踩坑记录（本轮重点，务必留存）

1. 🚨 **alembic check 首次真 PG 即崩（上游不兼容，最大坑）**：SQLAlchemy 2.0.52 反射 PG16 **identity 列**为 `server_default=Identity()`，alembic `_user_compare_server_default` 对其 `cast(...).arg.text` → `AttributeError: 'Identity' object has no attribute 'arg'`（1.18.5/1.19.1 均复现，降级无解）。**处置**：env.py `compare_server_default=False` 规避 + docs/06 §10 登记；补偿门禁=offline PG 渲染测试 + 本轮真 PG 零 diff 实测；上游修复后恢复 docs/11 Q-A06 自定义比较器。**教训：迁移门禁必须真 PG 跑一次，离线渲染测试测不出运行时崩溃。**
2. 🚨 **`services/python/.env` 里的 `APP_JWT_SECRET` 与 Java 默认值不一致 → Python 401「invalid token」**：JWT 互通联调失败时，单进程 decode 正常、运行中服务 401——查半天是**本地 .env 覆盖了 pydantic 默认值**（secret=change-me，仅 9 字节）。**处置**：两端默认值统一为 `vocalverse-dev-jwt-secret-0123456789abcdef`（≥32 字节，JJWT 硬性要求 256bit，弱密钥会 WeakKeyException）；.env.example 同步。**教训：联调类问题先核对"默认值 vs 本地 .env 覆盖"，再怀疑代码。**
3. **edge-tts 逐句延迟超标**：单句 1.34s（网络往返+合成），3 句串行 4.12s——按句串行 TTS 会把回放拖垮。**处置**：逐句**并发合成** + 开场/常用句预合成 + 首句文本到达即启动。首声预算重估 3~6s（docs/06 §8 已登记实测值）。
4. **HF 模型下载 xet 通道 401**：`cas-server.xethub.hf.co` 返回 401。**处置**：`HF_HUB_DISABLE_XET=1` 强制经典 HTTP 下载。**教训：新 pipeline 的下载通道要标注可绕过变量。**
5. **SQLite vs PG 时区/事务差异**：① SQLite 返回 naive datetime 与 `now(UTC)` 相减 TypeError → started_at 归一化；② SQLite 单连接（StaticPool）下"外层 turn 事务未提交 + 嵌套 complete_session 新会话"→ 事务冲突 → 嵌套调用前先 `db.commit()`。**教训：跨方言/双会话路径，单测（sqlite）跑通 ≠ PG 无虞，两处都要在测试断言里覆盖。**
6. **seed 测试被同库污染**：共享 in-memory 引擎里其它用例插入的场景让 `count==8` 断言变 10。**处置**：seed 测试用独立引擎 fixture。**教训：测试间的共享 DB 状态要显式隔离。**
7. **测试命中 Redis 限流**：本地 Redis 在跑（容器），`_redis_consume` 的 incr 跨进程累计 → 单测 6 轮跑完 LLM 桶 429。**处置**：`get_redis()` 在 `APP_TESTING=true` 时直接返回 None（内存后端），测试 hermetic。
8. **ffmpeg 缺失挡真实 ASR**：WinError 2；winget 需管理员。**处置**：asr.py 支持 `FFMPEG_BIN` 环境变量，本机用 pip 包 imageio-ffmpeg 的二进制路径（免管理员）。
9. **JJWT 弱密钥**：`change-me` 仅 72 bit→`WeakKeyException`；统一 ≥256bit 长密钥（与坑 2 同源）。
10. **Spotless 挡 verify**：新增 Java 文件未格式化 → `mvn verify` 在 check 阶段挂；先 `mvn spotless:apply` 再 verify；契约快照须 `CONTRACT_SNAPSHOT_GENERATE=1`（**环境变量**而非 -D！）重生成。
11. **vitest include 只匹配 `*.test.ts`**：`sse.spec.ts` 不收集（一直"2 passed"骗了人）；改为 `.test.ts`。SSE 多 `data:` 行语义是按行+换行拼接为一条消息，JSON 内含未转义换行会解析失败——测试用"尾随空行"聚合场景。
12. **GBK 控制台打印 emoji 崩**：`UnicodeEncodeError 'gbk' codec can't encode '\u2705'`（脚本尾打印 ✅）。**处置**：脚本输出用 ASCII 或 `$env:PYTHONIOENCODING='utf-8'`。
13. **常量导出**：`app.models` 只再导出表（不导出 SessionKinds/EventTypes 等常量）→ 多处 `from app.models import ContentStatus` ImportError，统一从 `app.models.base` 导入。
14. **后知后觉的 schema 缺口**：`reports.scope CHECK` 原为 ('global','user','scene','song')，会话级报告无处落袋 → 0002 迁移一并扩 'session'；`scenario_messages.action` 需 +'hint'（v1 草案漏项，拷问官抓到）。
15. **abandon 早退分支不产报告**：调收尾前必须释放外层 DB 事务，且该分支自身不落任何消息——用户点"结束"要直接走 complete_session（冒烟脚本抓到）。

### 提交

- 分支 `feat/m2-implementation`（9 个 commit 已推送，最新 `118b507`）；文档链 docs/14(v2)/15/16/17/18 与 README 索引同步；按组长授权管理员直推 main（跳过 PR 评审）。

---

## 2026-08-31 VocalVerse · 同构 Monorepo 参照对比评审——双子拷问官交叉拷问 + 拍板（不照搬、补 .dockerignore、契约生成化）

### 背景

- 组员提问：「admin/frontend/server 三个服务能按某同构 monorepo 参照项目那样做吗，是否会更清晰？」（动机确认＝要架构清晰、维护少混乱）。
- 参照项目＝同构 pnpm monorepo：2 前端（frontend+admin）+ 1 后端（NestJS+Prisma）+ 共享包（types/sdk/ui/utils）+ 独立 nginx 网关 + 根 compose；**外部项目，名称不入库**（见 docs/12 头部注记）。
- 方法论：资深架构初评 → 双拷问官交叉拷问（技术官 × 语境官），各自多轮递进至**问询穷尽**，两官独立得出同一评级「基本支持但需修正」。

### 关键拍板（5 项）

1. **不照搬**：参照项目清晰度源于同构（单语言/单契约源/单后端）；本项目＝1 前端 + 2 后端（Python/Java 课程强约束），`pnpm -r` 编排不了 Python/Java。
2. **拒 workspace 的真实依据**＝docs/08 Q9（单前端不用 pnpm workspace）+ docs/06 §10.1（Prisma 先例：同构工具链收益无法迁移到异构栈）——**不是 AD-01**（AD-01 只拍板目录命名，为其引证即引错锚点）。
3. **网关已存在**：apps/web/nginx.conf 即唯一入口（/api/v1/→python、/manage/→java、/healthz、/readyz），前端全走同源相对路径，无 CORS 问题；**不新增独立网关容器**。
4. **管理端 UI ＝ apps/web 内 /admin 路由 + admin 角色**，不建独立 SPA（管理端最小集仅 3 能力；docs/04 无独立管理台里程碑）。
5. **契约痛点才对症**：跨语言改契约→手工同步前端类型是唯一真实痛点，workspace 解决不了，**只有 OpenAPI 构建期生成前端类型能解**（docs/06 §7 已改写，动作 C 当日落地）。

### 实施

- `docs/06`：§2.1 布局演进注记（5 条，不推翻 AD-01）+ §7 codegen 口径澄清（"不做运行时 codegen"≠"不做构建期生成"）+ §14 修订说明登记。
- `docs/12-同构Monorepo对比与裁决.md`：双拷问官完整交付物归档（对照表/问题清单/行动清单/答辩口径/穷尽声明；参照项目名称不亮明）。
- **补 3 个 `.dockerignore`**（P0，此前全库缺失）：`services/python`（.venv≈1.1GB）、`services/java`（target≈55MB）、`apps/web`（node_modules≈121MB）此前全部进 build context——per-service context 只是"分开污染"非"躲开体积"。
- `/manage` 两处一致性守护：nginx（proxy_pass 尾斜杠剥离）与 vite.config.ts（rewrite）互指注释。
- README 文档索引补齐 10/11/12。
- **动作 C（契约生成管线，当日落地）**：① Python 侧契约定型——`app/audio/base.py` 增 `TTSResult`/`ChatResult`，4 条 stub 路由返回注解从 `Envelope[Any]` 改为 `Envelope[ASRResult/ScoreResult/TTSResult/ChatResult]`（OpenAPI 随出真 schema）；② 前端管线——`pnpm gen:api`（openapi-typescript 7.13）从契约快照 `src/api/specs/python-openapi.json` 生成 `src/api/generated/python-api.d.ts`（均入库），`client.ts` 的 asr 数据改为消费生成类型；③ 后端改契约后 `pnpm gen:api` 重跑 + typecheck 立即暴露断点。**CI 双关卡**：python-ci 增「契约快照 vs 后端 `app.openapi()` 一致性」（本地实测 MATCH）；frontend-ci 增「`pnpm gen:api` 重跑后生成文件零 diff」；开发侧一步刷新 = 新增 `scripts/refresh-openapi.ps1`。
- **脱敏**：参照项目为企业项目，名称已全库清理（含 git 历史核查，历史无引用）；docs/12、docs/06 §2.1/§14、README、worklog 一律以「同构 monorepo 参照项目」指代。
- **trace 透传（可观测性，动作 F 落地）**：nginx（`$request_id` 兜底生成 + /api/v1 /manage /healthz /readyz 四 location 透传 + 响应头回写）→ Python（`app/core/trace.py` 纯 ASGI 中间件，兼容 SSE 流式；ContextVar + 日志 filter，每条日志带 request_id）→ Java（`RequestIdFilter` 写 MDC + logback 模式 `%X{requestId}`）；三端各配测试（py 2 条 / java 2 条）。docs/06 §11 承诺补齐为"已落地"，loguru/logback JSON 结构化列为 M2 待办。
- **Java 契约对账（契约三关卡闭环）**：`apps/web/src/api/specs/java-openapi.json` 快照（初始由 `CONTRACT_SNAPSHOT_GENERATE=1` 跑 `ContractSnapshotTest` 生成）+ 该测试在 `mvn verify` 内用 springdoc MockMvc 实时渲染对账（servers 归一化排除）；`gen:api` 增 `java-api.d.ts`；`refresh-openapi.ps1` 升级为 4 步（Python+Java 双快照导出 + 双类型生成）；java-ci 触发路径补快照/生成文件。
- **M1 遗留修复：Java 裸返回违规 envelope（2026-09-01 重点）**：`PingController` 原返回裸 `Map{status,service}`，前端 `request()` 强制 `code===0` 检查 → `body.code` 为 undefined → **演示页"Java 不可达"永远是假的（服务一直健康）**。修复：新增 `common/dto/Envelope<T>`（record + ok/error 工厂），ping 改为 `Envelope<PingData>`；契约快照/生成类型重刷（新增 `PingData`/`EnvelopePingData` schema）；`client.ts` 的 `PingData` 改由生成契约导入。**教训：Java 任何接口必须过 Envelope（docs/06 §7 实现欠账，M2 前补齐）；排查"不可达"先看响应体有无 envelope，再看网络层**。
- **前端设计系统定版（docs/13）**：拍板 naive-ui + UnoCSS + 设计 token（三层分工）、B 多邻国活力配色（绿主色/柠檬黄激励/橙评分，本期仅浅色）、可视化栈 ECharts（报表）+ P5（仅品牌动效）+ D3（仅唱歌细图）、**Three.js 不引入**（docs/06 §9.2 2D 数字人拍板）。落地：`styles/tokens.ts`（token 唯一来源）+ `styles/theme.ts`（naive themeOverrides）+ `uno.config.ts` + 路由全表（`router/index.ts`，M2/M3 页面用占位页收敛）+ `UserLayout`/`AdminLayout`（管理端单 SPA 内路由）+ `LoginView`（P5 声波动效，懒加载+降级）+ `DemoView`（原演示页迁移 `/demo`）+ vitest 换 happy-dom（docs/09 P1-#10）。**两个版本坑**：vue-router 5.x 要求 Vite 7 → 钉 ^4.6；p5 2.x 与 @types/p5 1.x 类型不匹配 → 钉 ^1.11。版本已登记 docs/06 §3。
- **预览机制底座（docs/13 §8）**：`/preview` 画廊（`router/preview.ts` 整个子树包在 `import.meta.env.DEV` 三元内——**生产构建验证零 chunk**）+ 画廊布局（分组菜单 + DEV ONLY 标注 + 流程说明）+ 注册表 `views/preview/registry.ts`（新增页两步：加路由 + 登记）+ 5 张高保真预览页（学习主页 / 场景对话★★ / 评分报告 / 评价看板·ECharts / 用户管理）+ `useECharts` 懒加载封装（core/charts/components/renderers 全动态 import、ResizeObserver、dispose）。**明天群流程即可直接开工：在画廊里新增预览页画图 → 验收 → 平移集成。

### 验证

- [x] docs/06 三处编辑落位（§2.1 / §7 / §14）；docs/12 创建；README 索引更新；**外部参照项目名称（中/英文）全库零匹配（含 git 历史）**。
- [x] Python：`pytest` 15 passed；`ruff check` + `format --check` 通过（契约响应模型改动）。
- [x] 前端：`typecheck / lint / test:run(2 passed) / build` 全绿；`pnpm install --frozen-lockfile` 通过（CI 同款）。
- [x] **Java `mvn verify` 全绿**（spotless + 测试：含 `ContractSnapshotTest` 快照对账、`RequestIdFilterTest` 2 用例）。**Python `pytest` 17 passed**（含 trace 2 用例）、ruff 全过。**前端 `gen:api` 双文件生成 + typecheck/lint 全绿**。
- [x] **前端设计系统骨架验证**：`pnpm typecheck / lint / test:run(2 passed) / build` 全绿；chunk 健康——p5（1MB）独立 chunk 仅登录页懒加载，naive-ui 主包 266KB（gzip 90KB），无首屏重依赖。
- [x] **契约比对本地实测**：快照 vs `app.openapi()` → MATCH（CI 双关卡口径已核）；`scripts/refresh-openapi.ps1` 语法/路径核过（未实跑——需后端在跑）。
- [x] `.dockerignore` 生效性：`docker compose build` 下一轮构建验证（本次未重建镜像）。
- [x] vite/nginx 注释为纯注释，不影响 `pnpm typecheck/build` 与 nginx 语法（`nginx -t` 下次容器构建验证）。
- [x] git 工作区仅新增/修改上述文件，无密钥类文件。
- ⚠️ 注意：`pnpm add -D openapi-typescript` 时 pnpm 将锁内 vite 6.0.x→6.4.x、vitest 3.0.x→3.2.x、vue-tsc 2.1.x→2.2.x 等解析为区间内最新（锁文件 v9.0，与 CI 的 pnpm 9.12.1 兼容；构建/测试已验证）。版本纪律：本次属于区间内自动刷新，非人为升级；下次按 docs/06 §3 季度纪律统一执行。

### 待办（M2 起）

- [x] 动作 C：`openapi-typescript` 构建期生成前端类型（生成文件入库 + CI typecheck 兜底）。
- [x] 动作 F：X-Request-Id 全链路透传（nginx 注入 + Java filter + Python middleware）——已落地，各端有测试。
- [ ] 动作 D：/manage 一致性 CI 冒烟断言。
- [ ] 动作 E：docs/04 为 `/admin` 管理台路由排期。

## 2026-08-31 VocalVerse · 数据库表设计落地（19 表）+ 双子代理拷问 42 问收敛

### 背景

- M2 前的前置性工作：数据库表结构设计（按 docs/06 §10 表清单 + docs/08 Q37~Q39 + docs/09 §4.3），用 **Alembic 作为管表结构演进的唯一工具**，并**按约定做好每张表的「写归属」（Single-Writer）**。
- 流程：先设计完成（未提交）→ 开**两个子代理火力拷问**（① schema-迁移工程官 ② 业务域-写归属官，合计 **42 问**）→ 按结论整改 → 全量验证 → 本日志记录后提交推送。

### 产出

- **19 张表**：docs/06 §10 清单 15 张 + 补充 4 张（`song_pitch_refs` 参考旋律、`listening_materials` 听力素材、`placement_questions` 入学题库、`post_likes` 社区点赞），补充依据均来自 docs/06 已拍板口径（§9.2/§9.4/§9.5/§9.6）。
- `services/python/app/models/`（SQLAlchemy 2.0 typed + naming_convention + `jsonb()` JSONB variant + `bigint_pk()` SQLite 变体）；`docs/10-数据库设计.md`（表清单 + **写归属矩阵** + 契约 + 开放项裁决）。
- `alembic/env.py`（metadata 挂载、compare_type、自定义 server_default 比较器）、`alembic.ini`（纯 ASCII 化）、`alembic/versions/0001_initial_schema.py`（19 表初始迁移，upgrade/downgrade 双向离线渲染可编译）。
- `tests/test_models.py` 15 用例（19 表 create_all / CHECK 与唯一索引探针 ×5 / 单头 / 升级+回滚离线渲染）；python-ci 单头断言收紧 `-le 1` → `-eq 1`；compose/测试/环境变量统一 `APP_DATABASE_URL`、`APP_REDIS_URL`。

### 拷问结论（42 问：A 官 19 + B 官 23，详见 docs/11）

- **三大疑点**（组长视角已拍板）：入学题库**必建表**（placement_questions，Java 写，exam_revision 版本化）；协同过滤模拟矩阵**不建表**（`data/seed/reco_demo.csv`，demo 验证产物）；社区最小版**只建 post_likes 一张**（点赞不可推导；打卡/动态流派生）。
- **B 官最重一击**：四指标口径「普遍悬空」——CTR 缺 impression→click 关联键、唱歌完成率缺判定存储、互动率分母缺字段。已补：`events.browse_session_id/recommend_group_id/page/target_type/target_id/server_offset_ms`、`sing_attempts.is_complete/expected_lines/lrc_id`、`sessions.user_turn_count/assigned_turns`、`origin` CHECK 收紧为「仅 user 行可带」。
- **A 官验收**：19 表模型 vs 迁移**逐字段核对完全一致**（唯一差异为刻意重映射的时间戳默认值书写）；FK 建表顺序与 downgrade 逆序满足依赖；单头线性。

### 踩坑记录（本日最有价值的部分）

1. **alembic.ini 中文注释在 GBK locale Windows 上崩**：`configparser` 用 locale 编码读 ini（`encoding="locale"`），GBK 机器读 UTF-8 注释 → 所有 alembic 命令本地直接炸；CI 是 Linux（UTF-8）所以 M1 全绿是「假绿」。**处置**：ini 保持纯 ASCII + `path_separator = os`；凡是 configparser 消费的配置文件一律 ASCII。
2. **纯 `BIGINT` 主键在 SQLite 不是 rowid 别名** → 单测 INSERT 报 `NOT NULL constraint failed: id`；`create_all` 不报错（DDL 层 OK）、插数据才暴露。**处置**：`BigInteger().with_variant(Integer, "sqlite") + Identity()`，PG 仍 `BIGINT IDENTITY`（探针验证）。**教训**：SQLite 兼容要测「建表 + 插入」两步，不能只测 create_all。
3. **`server_default` 裸字符串被当裸 SQL**：`server_default="normal"` 渲染成 `DEFAULT normal`（未加引号！），`DEFAULT []` 在 PG 直接非法。**处置**：一律 `text("'...'")` 显式引号。
4. **`.gitignore` 裸 `models/` 静默吞掉 schema 模型**：无 `/` 锚定的目录规则匹配任意层级 → `services/python/app/models/*.py` 整个不入库（`git status` 看不见！）。**处置**：改为 `/models/` 锚定；**教训**：`git check-ignore` 与 `git status --untracked-files=all` 是新目录入库前的必查动作。
5. **autogenerate 静默跳过表达式唯一索引**（`lower(username)`）：SQLite 方言无法反射表达式索引 → 生成的迁移**不含**用户名大小写不敏感唯一索引，直接提交=唯一性丢失。**处置**：人工补 `op.create_index(..., [sa.text("lower(...)")], unique=True)` 并在测试断言。
6. **`text("now()")` 在 SQLite 是运行时雷**：`DEFAULT now()` 建表能过、INSERT 时「no such function: now」才炸（SQLite 对默认值函数调用延迟求值）。**处置**：统一 `func.now()`（SQLite 编译 `CURRENT_TIMESTAMP`）。
7. **id 命名双轨（DATABASE_URL vs APP_DATABASE_URL）**：pydantic `APP_` 前缀 vs compose/env.py/测试用裸变量 → M2 一接真引擎，**Python 服务连 SQLite、迁移跑 PG**（schema 静默分裂）。同坑还有 `REDIS_URL`。**处置**：全链路统一 `APP_` 前缀变量。
8. **属性名遮蔽模块函数**：`Lrc.text`（列名 text）遮蔽 `sqlalchemy.text()`，同 class body 内后续 `server_default=text(...)` 全部解析成 MappedColumn 崩溃（`TypeError: 'MappedColumn' object is not callable`）。**处置**：属性改名 `line_text`（DB 列名不变）。
9. **Numeric 列注解 float vs 运行时 Decimal**：`Mapped[float]` + `Numeric(5,2)` → 运行时返回 Decimal，与阈值比较 TypeError、JSON 序列化口径混乱。**处置**：统一 `Decimal` 注解。
10. **IDENTITY 序列不与显式 ID 同步**：seed 写 id=1/2/3 后注册拿 id=1 → PK 冲突；`ON CONFLICT DO NOTHING` 不解决。**处置**：契约写入 docs/10 §7.3（seed 不写显式 ID 用 `lastval()`；必须写则 `setval(pg_get_serial_sequence(...))`）。
11. **CI 单头断言 `-le 1` 假绿**：0 头（脚本损坏/迁移缺失）也被判过。**处置**：`-eq 1`（项目必有初始迁移）。
12. **迁移 docstring 修订头重复 / downgrade 忘写**：离线渲染只出 upgrade，必须人工补降级与文档头。**处置**：组装脚本推导逆序 downgrade + 测试断言 DROP TABLE 数。

### 验证（全绿）

- pytest **15 passed**（19 表 create_all；CHECK/表达式唯一/幂等键/origin/channel 探针；alembic 单头；upgrade/downgrade 离线渲染）；ruff / mypy 干净；`alembic heads` = `0001 (head)`；PG 方言离线 SQL：upgrade 19 表 + JSONB + IDENTITY，downgrade 19 表逆序 + 32 DROP INDEX。

### 待拍板（不阻塞 M2）

- ① seed 单写豁免 vs 用户种子移 Java `CommandLineRunner`（严格单写）；② 容器内迁移执行方案三选一（compose 一次性 migrate 服务 / 启动前置迁移 / 手动文档化）——M2 联调前必须落地；③ M2 接 PG 首日 `alembic upgrade head && alembic check` 接入 CI（with_variant/表达式索引噪音 diff 验证预案放 docs/07 架构官报告 Q-A04/05）。

---

## 2026-08-31 VocalVerse · 框架评审（docs/09）审阅与整改落地

- 收到另会话产出的 `docs/09-技术框架评审.md`（总评 A-，不主张替换技术栈）；逐条核验证据后**大部分采纳**，3 处修正评审意见（P0-#2 延迟预算按场景分层而非一刀切；P1-#7 无 Redis 不拒绝启动、改为 degraded 模式；P2-#13 探针修复后已非空转）。
- 落地整改：nginx `client_max_body_size 20m`；python-ci 探针改**单头断言**（0 头=暂允、多头=红）+ 新增 `uv lock --check`；Dockerfile 移除 `|| uv sync --no-dev` 回退；新建 `infra/`（含 `.wslconfig` 示例）；docs/06 补「并发与线程模型 / 模型缓存卷+预热 / 分层延迟口径 / sklearn joblib 一次训练 / JSONB with_variant / Redis 降级行为 / 升级纪律」；docs/09 追加处置记录（采纳/修正/汇总）。
- 过程教训：自己写的 CI 断言差点引入「0 头迁移=失败」的误伤——**断言场景要考虑空态**（0 头允许、多头拒绝）。

---

## 2026-08-31 VocalVerse · 补录：docker-build CI 三连坑修复（cache 驱动 / ghcr 小写 / YAML 块标量注释）

### 背景

- PR #1（M1 骨架）合入 main 后，`docker-build`（push 到 main 触发）失败：web job 8s 失败，另两个 matrix job 被 fail-fast 级联取消（用户看到的「2 cancelled / 2 successful / 1 failing」）。
- 排查方法：`gh run view <id> --log-failed` 逐层定位，三层都是配置级错误，非代码问题。

### 坑 1 · GHA 缓存需要 buildx docker-container 驱动

- **症状**：`ERROR: failed to build: Cache export is not supported for the docker driver.`
- **根因**：`docker/build-push-action` 的 `cache-to: type=gha` 依赖 BuildKit 的 `docker-container` 驱动；runner 默认 buildx 的 `docker` 驱动不支持 GHA 缓存导出。
- **处置**：去掉 `cache-from/cache-to`（M1 镜像小、缓存收益低），注释说明；如以后要缓存，先 `docker buildx create --driver docker-container --use`。

### 坑 2 · ghcr tag 的 owner 必须小写

- **症状**：`invalid tag "ghcr.io/LHRCarrier/vocalverse-python-api:latest": repository name must be lowercase`
- **根因**：`github.repository_owner` = `LHRCarrier` 含大写；Docker 仓库名规范要求全小写。
- **处置**：tags 写死小写 owner `ghcr.io/lhrcarrier/...`（注释提醒仓库迁移时同步）。

### 坑 3 · YAML 块标量里的 `#` 不是注释（本日最典型，自己埋的）

- **症状**：`invalid tag "# 注意：Docker 仓库名必须小写；..." : invalid reference format` —— tag 直接变成了注释文本。
- **根因**：把 `#` 注释写进了 `tags: |` **块标量内部**；YAML 中块标量（`|`/`>`）内容是字面文本，`#` 不生效（缩进正确与否无关）。
- **处置**：注释移到块外；并建立校验动作——**改完 workflow YAML 必须解析验证其值**：`uv run --no-project -p 3.12 --with pyyaml python -c "import yaml; print(yaml.safe_load(open('.github/workflows/docker-build.yml', encoding='utf-8')))"`，只凭肉眼缩进是看不出来的。
- **纪律**：`with:` 下的多行字符串（`|`/`>`）除目标内容外不得含任何其他行；注释一律放块外；提交前解析校验 + 看实际日志确认。

### 验证

- 修复链：PR #15（去缓存）→ PR #16（owner 小写）→ PR #17（块标量注释外移），均管理员绕过合入；
- 最终 run `33370144948`（sha `27381ce`）**success**：python-api / java-api / web 三镜像全部构建并推送 GHCR；
- 附带发现：runner 警告 Node.js 20 弃用（checkout@v4 等被强制跑 24），记录待后续升级 action 版本时处理。

---

## 2026-08-31 VocalVerse · M1 框架从零搭建——双子代理拷问收敛 123 问 + 三端骨架落地 + 全链路验证通过

### 背景

- 项目从零开始（仓库只有 docs 规划层，无代码）；目标是先搭**成熟技术框架**再进功能开发。按案例 #7 原文（后端 Python+Java、前端 Vue、模型 PyTorch/TensorFlow、Scikit-learn 推荐）搭建，需求与选型矛盾多，先拷问后动手。
- 采用「需求拷问官 + 技术架构拷问官」双子代理火力拷问（合计 **123 问**），组长拍板 6 项关键分叉，随后落地 M1 骨架并逐端验证。

### 关键拍板（6 项）

1. **拓扑**：语音热路径直连 Python；Java 只做管理端 + JWT 签发（不进语音/SSE 热路径）；
2. **语法评分**：暂定 DeepSeek LLM 判定转写文本（0-100 + 错误类型）；不稳定则回退砍项、口径改「发音/流利度/完整度」；
3. **自研评分门禁化**：冻 wav2vec2 backbone 只训评分头（GPU 5~10h、约 ¥20~40）；门禁 = M3 的 P0/P1 全绿 + 验证集 r≥0.8 且 MAE 达标，检查点 M3 第 2 周周末；不达标回退讯飞基线；
4. **M3 取舍**：唱歌做深（音准/节奏/发音逐句评分），推荐/报表演示化（预置模拟行为矩阵验证「生效」）；
5. **社区最小版**：打卡 + 成绩卡片 + 只读动态流 + 点赞；不做双人实时对练（答辩口径「分享+激励」）；
6. **前端 TypeScript strict**。

### 实施

**1. 决策文档**：`docs/06-技术框架决策.md`（16 章：拓扑/目录/版本矩阵/质量链/CI/测试/契约/音频与流式/功能口径/DB/安全/Windows 对策/门禁/修订说明/风险回退/M1 清单）；并修正 `docs/01`「三项指标」→「四项指标」。
**2. 功能口径定稿**（写入 docs/06 第 9 章，团队照此开发）：四项检查点指标精确定义（CTR=推荐曝光 30min 内点击去重/曝光；完成=口语 5 轮或 2min、唱歌整首；跳出=进页 30s 无有效事件；互动率=主动发消息轮数/分配轮数）+ 9 类埋点事件；水平 4 档 L1~L4（综合分 S=0.4发音+0.3语法+0.3流利度，≥85/70~84/55~69/<55）；入学测试 = 5 固定朗读句 + 1 轮 QA（admin 题库）；场景 4~5 个、会话 5~8 轮/2~3min；唱歌映射表与综合 = 0.5音准+0.2节奏+0.3发音（发音复用口语引擎）。
**3. Monorepo 骨架**：`apps/web` + `services/python` + `services/java` + `infra` + `docs` + `scripts`；根配置 `.editorconfig`/`.tool-versions`/`.nvmrc`/`.env.example`/`.pre-commit-config.yaml`（纯 Python 钩子，Windows 可用，禁 *.sh）/`docker-compose.yml`（5 服务 + healthcheck + 依赖顺序，Web 映射 8088 避 80 端口权限）。
**4. CI/CD**：frontend-ci / python-ci / java-ci / secret-scan / docker-build 五件套 + PR 模板（敏感数据检查项）+ CODEOWNERS + dependabot；与 docs/05 分支保护（1 人 review、squash、dismiss stale）配合；**CI 零真实 API Key**（ASR/TTS/评分/LLM 全走 stub）。
**5. Python 服务**：Pydantic Settings（APP_ 前缀）、Envelope/错误码、`healthz/readyz`、音频 stub 路由（asr/score/tts/llm-chat，上传 20MB 上限 41301）、`app/audio/base.py` 四个抽象接口 + `stubs.py` Fake（M2 只改实现，不改签名）、Alembic 骨架（唯一 schema 真源）、Dockerfile（slim + ffmpeg）。
**6. Java 服务**：Spring Boot 3.3.5 / Java 21 / Maven + Spotless（google-java-format）；`ddl-auto=none`；H2 测试配置 + PingController + 2 测试；双阶段 Dockerfile。
**7. 前端**：Vue 3.5 + TS strict + Vite 6 + pnpm；`api/client.ts`（envelope 解析、`request<T>` 可切 Python/Java base）；`audio/recorder.ts`（MediaRecorder → WebM/opus，60s/20MB，录完再传）；`audio/sse.ts`（text_delta/audio_chunk/done 协议，音频为时间轴权威、文本为字幕）；`App.vue` 演示页（三服务连通 + 录音→stub 转写冒烟链）；nginx 容器（SPA + SSE 反代 buffering off）。
**8. 契约与脚本**：`docs/api/envelope.md` + `error-codes.md`（错误码表）；`scripts/dev.ps1`（幂等 + 端口检测）、`scripts/bootstrap.ps1`（工具链自检）；音频/模型延迟口径 = 7~10s 出第一声，演示话术「录音后 3~5 秒反馈」（不承诺实时）。

### 验证（全部实测）

| 检查 | 结果 |
|---|---|
| `docker compose config -q` | ✅（修 env_file 后通过） |
| Java `mvn -B -ntp verify`（含 Spotless） | ✅ BUILD SUCCESS |
| 前端 `pnpm lint / typecheck / test:run / build` | ✅ 全绿（vitest 2 passed；dist 66.7KB/gzip 26.9KB） |
| Python `ruff check` + `format --check` + `pytest` | ✅ 6 passed（ephemeral env，未装 torch） |
| `uv lock`（101 包）/ `pnpm-lock.yaml` | ✅ 已生成，CI `--frozen` 可复现 |
| `.gitignore` 豁免实测（`git check-ignore`） | ✅ 种子/夹具可提交，产物被忽略 |

### 实施中踩坑（务必留存）

1. 🚨 **`.gitignore` 裸后缀黑名单是第一天就埋的雷**：原文件用 `*.wav/*.lrc/*.csv` 与整目录 `data/` 黑名单，歌曲库 LRC 种子、埋点 CSV、音频测试夹具全被静默忽略，M1 提交卡死。**处置**：改按路径忽略（`data/audio/`、`models/`、`*.pth` 等）+ 显式豁免（`!data/seed/**`、`!**/*.lrc`、`!**/tests/fixtures/**`，豁免规则放忽略规则之后）。**纪律：改 .gitignore 必须用 `git check-ignore -v` 实测**。
2. 🚨 **vitest 2.x 与 Vite 6 类型冲突（前端踩坑，最耗时）**：vitest 2.1.9 内部绑定 vite@5 类型，`vite.config.ts` 从 `'vitest/config'` 引入 defineConfig 后与项目 vite@6 的 `PluginOption` 撞型；`pnpm typecheck --noEmit` 不爆、只有 `vue-tsc -b`（build）爆。**处置**：vitest 升 `^3.0.0`，build 立即通过。**纪律：升级 Vite 主版本必须同步升级 vitest；CI 以 build 为准**。
3. **FastAPI 响应校验按「返回注解」执行**：路由声明 `-> dict` 但返回 Envelope → `ResponseValidationError`（loc=response）。注解改为 `-> Envelope[Any]`。**教训：FastAPI 返回注解不是文档，是响应模型**。
4. **Stackless 细节**：`EventSource` 无 `onclose` 属性（收尾逻辑放 onerror/done）；`vite.config.ts` 需 `@types/node` + tsconfig.node.json `"types":["node"]`；Python `on_event("startup")` 已弃用 → 改 lifespan。
5. **Python 依赖**：`[tool.uv] package = true` 会让 uv 尝试打包应用（无 build-system 报错）→ **`package = false`**；torch 走 pytorch-cpu 显式 index（**只装 CPU 轮子**，训练在云 GPU 隔离环境）；**不引 crepe/TensorFlow**（pyin 基线，TF 是纯负担）；`uv.lock` 必须提交否则 CI `--frozen` 失败；python-ci 需 dev 组（pytest/ruff）→ `uv sync --frozen` 不要 `--no-dev`。
6. **双后端/schema 纪律**：Alembic 唯一 schema 真源，Java `ddl-auto=none` 只映射；CI 加 alembic heads 一致性探针。
7. **本机验证环境**：Windows 只有 Python 3.7 → 用 `uv python install 3.12` 托管解释器 + `uv run --no-project -p 3.12 --with …` 拉轻量依赖跑 pytest（回避 200MB torch）；`uvx ruff` 直接跑 lint/format。
8. **其余小坑**：`docker compose` 的 `env_file: .env` 不存在会 config 失败 → `- path: .env` + `required: false`；Spotless 首次必挂 → 先 `mvn spotless:apply`；CI 用 runner 预装 Maven（`mvn`），`mvnw` 本地 `mvn -N wrapper:wrapper` 生成一次；ESLint 模板换行风格规则过严 → 显式关闭纯风格项；proxy 需单独加 `/healthz`、`/readyz`（健康检查在根路径，不在 /api/v1 下）。

### 备注

- 双子代理完整拷问原文已归档：`docs/07-需求拷问报告.md`（63 问 + 38 条 ADR）、`docs/08-技术架构拷问报告.md`（60 问 + AD-01~40）；拍板结论见 docs/06，本日志为当日执行记录。
- 合规红线（docs/06 9.7）：录音默认不持久化（24h TTL）、demo 歌曲用公有领域/自创曲目、模型权重用 setup 脚本下载、密钥只进 .env。
- 变更尚未提交；按 docs/05 应走 `feat/m1-scaffold` 分支 + PR（建议分 2~3 个 PR：ci+根配置 / python / java+web）。

### 提交与推送

- 未提交。建议：`git checkout -b feat/m1-scaffold` → 3 个 PR → 1 人评审 → squash 合入 main（CI required checks 生效后合并即全绿）。
- ⚠️ 本文件为团队可见（已从 .gitignore 移除），内容已脱敏：无任何密钥/真实数据。
