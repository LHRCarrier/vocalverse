# 58 · 审核自动送审（Jev）接入设计

> 状态：**已落码**（2026-09-22）。落码范围：Java 自动送审链路 + 管理端审核工作台 4 处闭环缺陷。
> 关联：`docs/50 §5.3.8~§6.2`（审核域权威设计）、`docs/51 B-4`（作者可见性拍板）、
> `docs/06 §17`（开关登记）、`docs/api/error-codes.md`（本设计**不新增**错误码）。

## 0. 一句话

内容（帖子/评论）发布后，异步调用 **Jev**（TypeSafe AI 的 System One 决策模型）判定「是否违规 /
违规类型 / 严重度」，命中阈值就自动建**待审单**（`source='auto'`，判定证据写进 `snapshot.ai`），
由审核员在控制台决定处置 —— **Jev 只负责把它送进队列，不负责处置**。

## 1. 为什么是 Jev（以及为什么只让它建单）

| 维度 | 事实 | 对本项目的影响 |
|---|---|---|
| 定位 | System One 决策模型：不做生成，只对一段文本并行回答 `noul`（是/否+概率）/ `choice`（选项+概率）/ `score`（量表） | 正好对应「违规？/哪类？/多严重？」——不需要它写字 |
| 延迟/成本 | 官方口径 70–500ms；输入 $0.042/M token、输出免费（本机实测一次调用含 TLS 握手 6.16s，服务在美西） | 必须异步、不能进发帖热路径；单次成本可忽略 |
| 输入形态 | **纯文本**（64k 上下文，不支持音频/图像） | 只能覆盖帖子/评论；媒体与私信不接 |
| 可靠性 | 官方评测只与中档模型打平；第三方实测有正确率 64.5% 的记录（`docs/58 §9 参考`） | **不自动隐藏**：所有处置动作仍由审核员决定并留审计（`docs/50 §6.2`） |
| 可用性 | 闭源托管 API（美西）；已可通过 OpenRouter / Vercel AI Gateway 等接入 | 依赖不可用时**降级放行**，内容发布不受影响 |

结论：把 Jev 当作**队列的分流器**而不是法官 —— 误报的代价是一次人工复核，漏报的代价由举报入口
（尚未实现，见 §5.5）与后续迭代继续兜。

## 2. 现状缺口（修复前实测）

| # | 缺口 | 修复前表现 | 影响 |
|---|---|---|---|
| G-1 | `source='auto'` 有字段、无写入方 | 内容发布后永远不会自动进入审核队列，只能靠人工建单/举报 | 审核队列在生产上长期为空，「自动审核」名存实亡 |
| G-2 | 升级件从默认队列消失 | `GET /moderation/cases?status=pending` 不含 `escalated`；页面却写着「升级后仍留在队列里」 | 升级 = 单子失踪，没人再处理 |
| G-3 | 趋势图「新建」接了 `pending` | 服务端 `pending` 是「当日结束时仍未决定（积压）」，前端当新建画 | 图表与图例不符，看板给出错误信号 |
| G-4 | `decision_note` 文案与拍板冲突 | `DecisionDialog` 告诉审核员「作者本人会看到这段文字」，而 `docs/51 B-4` 已定稿**不下发** | 审核员按错误预期写备注；契约漂移 |
| G-5 | 举报处理请求体双键 hack | 前端同时发 `decision` + `action` 并 `as unknown as` 断言（注释误以为 `action` 是 `@NotNull`） | 掩盖契约理解错误，误导后续维护者 |

## 3. 设计

### 3.1 触发链路（为什么不阻塞发布）

```
CommunityService.create / addComment   （@Transactional）
   └─ publishEvent(ContentPublishedEvent)     ← 事务内发布
        └─ ModerationAutoScreenListener       ← @TransactionalEventListener(AFTER_COMMIT)
             └─ moderationScreenExecutor      ← 单线程 + 有界队列(200)，队列满丢弃并打 WARN
                  └─ ModerationAutoScreen.screen()   ← @Transactional(REQUIRES_NEW)
                       └─ JevHttpClient → POST /v1/systemone
                       └─ ModerationService.createAuto()  → moderation_cases(source='auto')
```

三条接线纪律：

1. **AFTER_COMMIT**：回滚的事务（如评论计数自增失败）不产生审核单；
2. **REQUIRES_NEW**：`afterCommit` 回调执行时旧事务资源仍绑定在线程上，默认传播会「加入一个已提交的
   事务」导致写入在收尾时被丢弃 —— 必须显式挂起旧资源开新事务；
3. **丢弃优于阻塞**：队列满时丢弃本次送审（`DiscardPolicy` 的自定义实现打 WARN），
   绝不用 `CallerRunsPolicy` 把第三方延迟加到用户请求上。

### 3.2 判定契约

一次调用并行问三个问题（官方口径：并行评估，加问题几乎不加延迟）：

| 问题 id | 类型 | 说明 |
|---|---|---|
| `is_violation` | `noul` | 是否违反社区规范（返回 0–1 概率） |
| `category` | `choice` | 违规类型。**选项键与 `ModerationService.REASON_CODES` 逐字同值**（spam/abuse/porn/violence/politics/ad/copyright/misinfo/other），因此不需要映射表；测试 `JevQuestionContractTest` 把两者相等钉死 |
| `severity` | `score` | 严重度（0 无问题 / 1 轻微 / 2 中等 / 3 严重，可落级别之间） |

`state` 只带判定必需字段：`contentType`（帖子/评论）、`kind`、`domain`、`title`、`body`（截断
≤ `max-chars`，默认 4000）；**不带作者 id、用户 id、媒体 URL**。

### 3.3 建单口径

- **阈值**：`violation ≥ threshold`（默认 0.7）才建单 —— 只建单不处置，阈值宁松勿紧；
- **原因码**：`category` 若不在 `REASON_CODES` 内 → 回落 `other`（防上游加选项导致的脏值入库）；
- **优先级**：`severity ≥ 2.5 → 1（高）`、`≥ 1.5 → 2（中）`、其余 `3（低）`；
- **证据**：`moderation_cases.snapshot.ai = {model, violation, category, categoryConfidence,
  severity, severityConfidence, latencyMs, inputTokens}`（保留三位小数）。审核员在决定弹窗里直接看到
  「这单为什么自动进来」；事后调阈值也有可对账凭据；
- **审计**：系统身份落行（`adminUserId=null`、`username="-"`），动作名复用 `moderation.case.create`
  （不新增动作，前端审计过滤器零改动），`detail.source='auto'` 区分来源（白名单新增 `source` 键）；
- **幂等**：目标已有 pending/escalated 单 → 复用不新建（同一目标先被举报、再被自动送审命中也只有一张单）。

### 3.4 失败语义（全链路 fail-open）

| 失败 | 行为 |
|---|---|
| 未配置 `TYPESAFE_API_KEY` | 客户端短路，零网络调用，启动打一行 WARN |
| 超时 / 连接失败 / 429 / 529 | 客户端吞掉并 WARN（含 `ref` 与耗时，**不含正文**），不建单 |
| 响应缺字段 / 不可解析 | 同上 |
| 送审线程执行异常 | 监听器双层 try/catch，异常不外溢到请求线程 |
| 队列满 | 丢弃本次 + WARN，内容发布不受影响 |

**没有实现重试队列**：发送失败就是失败，不补送（不做的理由见 §8）。

## 4. 安全与隐私

- **数据出境**：开启即构成「UGC 文本 → 第三方 API（美西）」的数据流；`.env.example` 明确标注，生产启用前
  需过合规评估（与 `docs/19 P-07` 同源议题）；
- **最小化**：截断 4000 字；只发内容文本与分类上下文，不发身份标识；
- **日志纪律**：只打 `post#12` 引用、概率、耗时；不打正文、不打密钥（`docs/50 §9.3`）；
- **密钥管理**：`TYPESAFE_API_KEY` 只走 `.env`（已 gitignore）；`.env.example` 只放占位符；
  `docs/06 §17` 只登记功能开关，密钥不登记（沿用 `VOICEVERSE_CONSOLE_JWT_SECRET` 的处置）。

## 5. 闭环缺陷修复

### 5.1 升级件可见性：`status=open`

`ModerationCaseRepository.search` 增加聚合筛选：`status='open'` ⇔ `status IN ('pending','escalated')`。
控制器 `@Pattern` 加入 `open`，`/moderation/contract` 增加 `caseStatusFilters`（区别于真实状态值
`caseStatuses`）。队列页默认筛选从 `pending` 改为 `open`。

### 5.2 趋势图口径

服务端 `trend` 本来就有 `created` 字段，前端只是没接。新增 `trendSeries()` 纯函数（`moderationMeta.ts`）
统一映射：`新建=created / 已处置=approved / 驳回=rejected`，并补测试防回潮。

### 5.3 `decision_note` 文案对齐 `docs/51 B-4`

弹窗文案改为「处置备注（内部留痕，不对外展示）」，并注明作者侧只看固定原因码标签（P6 落地）；
`moderationMeta.auditNoteText` 的注释同步修正。

### 5.4 举报处理请求体清理

`ReportsView.callHandle` 只发 `{decision, note?}`（Java `ReportHandle.effective()` 本就以 `decision`
优先、`action` 可空），删除 `as unknown as` 断言与那段过时注释。

### 5.5 仍然缺的（登记，不在本轮）

| 缺口 | 说明 | 去向 |
|---|---|---|
| C 端举报入口 | `ModerationService.createReport` 只被测试调用；举报页空态已注明「C 端举报入口由 Python 侧提供（本期尚未接入）」 | 独立工单（Python 端点 + C 端入口 + 内部委托） |
| 作者侧处置原因下发 | `docs/51 B-4` 拍板：`reason_code` 中文标签经公开面下发，需扩 C 端 DTO | P6 后续 PR（不做半成品） |
| 敏感词库 | Jev 是语义判定，不替代关键词表 | P1 |

## 6. 配置开关

| 键 | 默认 | 说明 |
|---|---|---|
| `VOICEVERSE_MODERATION_AUTO_SCREEN` | `false` | 总开关（已登记 `docs/06 §17`）。公网仓库默认关；演示环境开启 |
| `TYPESAFE_API_KEY` | 空 | 密钥；为空时即使总开关为 true 也不外发 |
| `TYPESAFE_BASE_URL` | `https://api.typesafe.ai` | 端点 |
| `VOICEVERSE_MODERATION_JEV_MODEL` | `jev-latest` | 模型别名（响应里的 `model` 记版本化 ID） |
| `VOICEVERSE_MODERATION_THRESHOLD` | `0.7` | 建单阈值 |
| `VOICEVERSE_MODERATION_JEV_TIMEOUT_MS` | `10000` | 读超时（连接超时封顶 3s） |
| `VOICEVERSE_MODERATION_MAX_CHARS` | `4000` | 送审正文截断 |
| `VOICEVERSE_MODERATION_ASYNC` | `true` | `false` = 同步执行（**仅测试**） |

## 7. 测试与验证（实跑记录）

命令与结果（2026-09-22，Windows 本地）：

```
# Java：新增 6 例（5 例自动送审链路 + 1 例问题契约），全量 185 例
cd services/java && mvn -B -ntp verify -DskipITs
→ Tests run: 185, Failures: 0, Errors: 0；spotless:check 通过

# 门禁脚本
python scripts/check_pg_typed_params.py     → exit 0
PYTHONIOENCODING=utf-8 python scripts/check_feature_flags.py → exit 0（12 行全 ok）

# 管理端（apps/admin）
pnpm lint / pnpm typecheck / pnpm test -- --run / pnpm build
→ lint 0 error；typecheck 通过；Test Files 9 passed · Tests 81 passed；build 成功
```

回归测试的**修复前必红**说明：

- `ModerationAutoScreenTest.escalatedCaseStaysVisibleInOpenQueue`：修复前 `status=open` 会被
  `@Pattern` 拒绝（400），测试必红；
- `moderationMeta.test.ts` 的「新建 = created」：修复前 `trendSeries` 不存在、图接 `pending`，断言必红；
- `JevQuestionContractTest`：把「Jev 选项 = reason codes」的等式钉死，任一侧加值未同步必红。

另有一次**真实 API 冒烟**（本机直连 api.typesafe.ai，非测试桩）：HTTP 200，
`model=jev-1.13.0`，`noul=0.96`，`severity=1.96`，端到端 6.16s（含 TLS 握手；美西→本地）。

## 8. 不做项与风险

| 不做 | 理由 |
|---|---|
| 自动隐藏/删除 | 第三方准确率不足以承担误伤；处置必须由审核员决定并留审计 |
| 媒体 / 私信送审 | Jev 纯文本输入；媒体处置在 Python 媒体库，私信只读（`docs/50 §5.4`） |
| 送审重试队列 / 补送 | 丢一条送审只影响该内容的自动发现（举报/人工仍可兜）；重试队列的复杂度与运维面不值得 |
| 流式/逐字送审 | 判定对象是完整内容，发布后一次性送审即可 |
| 关键词库 | P1，与语义判定互补而非替代 |

风险：

- **队列默认视图改动**：运营习惯 `pending` 筛选 → 现在默认 `open`（多出 escalated）。这是修复项本身，
  在页面文案与测试中都已对齐；
- **送审队列积压**：单线程 + 队列 200；极端刷帖时丢弃并打 WARN（可观测）。
  若未来需要，可把 executor 换成多消费者 —— 但送审非实时，当前无必要；
- **第三方依赖**：fail-open 已保证发布不受影响；模型别名（`jev-latest`）背后版本会变，
  证据里记录版本化 `model` 字段以便回溯。

## 9. 参考

- TypeSafe 官方文档：`https://docs.typesafe.ai`（System One / primitives / API reference / models）
- 独立第三方实测与生态：`https://jev-agent.com`、`https://madewithjev.com`（含第三方正确率争议记录）
- 上游发布说明：TypeSafe AI Blog《Introducing System One Models & Jev》（2026-09-15）
