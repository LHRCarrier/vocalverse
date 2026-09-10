# BUG 实测：唱歌端点响应无 schema——前端手写 DTO 与后端契约漂移（P1-14）

- **日期**：2026-09-10
- **发现**：`local/唱歌模块全链路拷问报告-2026-09-10.md`（P1-14 / 多路交叉）
- **范围**：`services/python/app/sing/schemas.py`（新增）、`app/api/routes/singing.py`、契约快照/生成类型、`apps/web/src/api/sing.ts`、`apps/web/src/composables/sing.ts`
- **影响**：唱歌 5 端点 + 收藏 2 端点在 OpenAPI 里**响应是空 schema**（`{}`）→ `pnpm gen:api` 生成的 TS 类型无内容 → 前端只能手写 DTO 副本；副本一旦漏改就**静默漂移**（实测两处）：
  - `alignment.bpm_source` 前端写成 `'onset' | 'duration'`，后端实际四值 `onset-f0|onset-flux|onset-arbitrated|duration`（口径 v3 item7 新增的三值前端根本不知道）；
  - `uploadSingAudio` 声明的返回类型带 `progress`，后端 `SubmitAck` **只有** `{attempt_id, status}` → 类型谎报（运行时 `status.value.progress` 是 `undefined`，靠 `progressPct` 里的 `if (!p) return 0` 兜底才没崩）。

---

## 1. 复现

1. 打开 `apps/web/src/api/specs/python-openapi.json`，看 op 22~28（`/songs`、`/songs/{id}`、`/songs/{id}/favorite`、`/sessions/{id}/audio`、`/sing/attempts/{id}/status`、`/sing/attempts/{id}`）的 `responses.200`：**没有 `content`**（空 schema）；
2. 前端 `src/api/sing.ts` 里却有 8 个手写 `interface`——两边没有任何机制保证一致；
3. 把生成类型接上去（本次修复）后，`pnpm typecheck` 立刻报出 9 处真实漂移：

```
src/lib/sing-chart.ts(77,19): error TS18048: 'result.lines' is possibly 'undefined'.
src/views/mobile/MobileSingView.vue(372,50): error TS2345: Argument of type 'number | null | undefined' ...
src/views/mobile/__tests__/MobileSingView.test.ts(167,5): error TS2353: ... 'progress' does not exist in
  type '{ attempt_id: number; status: string; }'
src/views/preview/SingingPreview.vue(171,47): ...
```

4. 契约层面（`tests/test_sing_schemas.py`，**修复前必失败**）：`test_singing_endpoints_declare_response_schema` 断言每个端点 200 响应引用具名 DTO——修复前 `responses.200.content` 不存在。

## 2. 根因

- 路由只写了 `return ok(...)`，**没有 `response_model`**：FastAPI 无注解时 OpenAPI 响应为空 schema，`openapi-typescript` 生成 `data?: unknown`；
- 于是前端为了能用，手写了一份 DTO —— 这正是 `docs/06 §7`「不做运行时 codegen（杜绝 DTO 双写）」想避免的状态：**双写必然漂移**，而漂移在 typecheck 里看不出来（手写副本自己就是"真源"）。

## 3. 修复

1. **服务端 DTO 集中声明**（`app/sing/schemas.py`）：`SongSummary`/`SongLine`/`SongDetail`/`PitchRef`/`FavoriteState`/`SubmitAck`/`TaskProgress`/`AttemptStatus`/`ScoreLine`/`SingAlignment`/`AttemptResult`——字段与 service 层 `_song_summary`/`_status_payload`/`_result_dict`/`_line_dict` 一一对应；
   - `SingAlignment` 加 `model_config = ConfigDict(extra="allow")`：口径升级新增的诊断键**必须原样透传**（响应模型只做标注、不做过滤，否则前端会看到"字段时有时无"）；
   - 闭集字段用 `Literal`：`bpm_source`（四值，docs/06 §9.4 口径 v3 item7）、`pitch_reliability`（full/reduced/low，item8）——新值即契约变更，须同步 docs 与前端类型；
   - `lines`/`alignment` **不给默认值**（必填）：service 恒写，生成的 TS 类型因此必填，前端不必到处写 `?? []`。
2. **路由挂 `response_model`**（7 个端点，比审计点的 5 个多收口了收藏 2 个）：`Envelope[SongSummary]`/`Envelope[list[SongSummary]]`/`Envelope[SongDetail]`/`Envelope[FavoriteState]`/`Envelope[SubmitAck]`/`Envelope[AttemptStatus]`/`Envelope[AttemptResult]`。
3. **契约与类型重生成**：`python-openapi.json`（29 ops 不变、`components.schemas` 23 → 40）+ `pnpm gen:api`（`python-api.d.ts` +463 行；`java-api.d.ts` 零 diff）。
4. **前端改为消费生成类型**（`api/sing.ts`）：`export type SongSummary = Schemas['SongSummary']` 等 8 个别名，删除手写字段表；`SingSessionCreated` 保留手写并注明原因（`POST /sessions` 该 op 的 `data` 仍是 `Any`，后端补齐后同样改别名）。
5. **顺带修掉两处真实缺陷**：`composables/sing.ts` 上传后不再把 ack 当 `status` 用（补一条 `{progress:{0,0}}` 本地 queued 快照，字段与后端一致）；`scoreColor(v: number | null | undefined)` 放宽签名匹配可选字段。

## 4. 验证

- 新增 `tests/test_sing_schemas.py`（4 条）：
  - `test_singing_endpoints_declare_response_schema`：7 个端点 200 响应必须 `$ref` 到具名 envelope（**修复前必失败**：无 `content`）；
  - `test_song_summary_keys_match_schema` / `test_sing_attempt_keys_and_alignment_passthrough` / `test_favorite_endpoint_keys_match_schema`：HTTP 响应键集合 == DTO 字段集合；`alignment.future_diag_key=42` 必须透传（守 `extra="allow"`）。
- 前端 typecheck 从 **9 处报错 → 0**（这 9 处就是漂移清单，逐一核对并修正了代码/夹具而非放宽类型）。
- 门禁：Python `ruff check` / `ruff format --check` / `pytest -q` **478 passed**；前端 `lint` + `typecheck` + `test:run` **177 passed** + `build` + `check-bundle.mjs`。
- 文档：docs/21 §2.1 增「响应 schema 补齐（P1-14）」注（含 DTO 清单与 `extra="allow"` 语义）。

## 5. 踩坑

1. **Pydantic 有默认值的字段在 OpenAPI 里是「可选」**：`lines: list[ScoreLine] = Field(default_factory=list)` 生成 `lines?: ScoreLine[]`，于是前端每处访问都要 `?? []`（typecheck 直接报 TS18048）。真实契约里这两个键**恒存在**，所以去掉默认值改成必填，类型才与行为一致——"给个空默认值更安全"在**响应**模型上是反的。
2. **`extra="allow"` 是响应模型的必需品，不是可选优化**：`alignment` 这类"留痕字典"会随口径升级加键；用默认的 `extra="ignore"` 会在**响应阶段**把新键悄悄删掉（服务端代码、DB、文档都对，只有 API 输出少字段），排障时极难定位。加一条"未知键透传"的测试把这条约定钉住。
3. **类型接管的报错不是噪音，是漂移清单**：换生成类型后 9 处报错里既有真 bug（ack 无 progress），也有两边都"没错但类型太窄"（可选字段传进 `(v: number | null)`）。逐条判断比一次性 `as any` 有价值得多。
4. **`Literal` 的代价要写进文档**：闭集字段用 `Literal` 后，评分侧若写入第五个 `bpm_source`，响应会**校验失败（500）**而不是静默透传。这是有意的"契约变更必须显式"，但必须让改评分的人知道——已写进 `schemas.py` 模块注释与 docs/21。

—— 执行人：AI 代签（正式署名待组长确认），2026-09-10
