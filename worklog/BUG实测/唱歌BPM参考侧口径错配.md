# BUG：唱歌 v3「真实 BPM」（item7）参考侧口径错配 → 该特性实际恒回落 duration（形同虚设）

- **发现**：2026-09-10 · 唱歌模块容器端到端功能测试（`local/sing_e2e_test.py`，真 PG/真 pyin/真 ffmpeg）。
- **修复**：2026-09-10 · 执行人：AI 代签（正式署名待组长确认）。
- **影响面**：`app/audio/sing.py`（bpm_from_onsets / bpm_ratio_info / PyinSingScorer）、`app/audio/pitch.py`（EXTRACTOR_VERSION / slice_window）、
  `app/sing/jobs.py`（refs 落库内容）；**评分公式与权重不受影响**（bpm_ratio 是信息性字段，docs/06 §9.4）。

## 复现

1. 重建 python-api 容器（v3 代码）→ 3 首 demo `pitch_ref_status=ready`；
2. 用 `local/sing_test_user.py` 生成"跟唱"音频（参考旋律降 3 半音 + 慢 5% + 晚起唱 0.5s + 微噪声）；
3. 走全链路：注册/登录 → `POST /sessions(kind=sing)` → `POST /sessions/{id}/audio` → 轮询 → `GET /sing/attempts/{id}`；
4. 结果：`alignment.bpm_source = "duration"`、`bpm_user = null`、`bpm_ref = null`（期望 `onset` + 两侧 BPM 数值）。

## 根因

**两侧 onset 不是同一物理量，且过滤窗口按用户侧设定**：

| 侧 | v3 初版实现 | 量纲 | 实测 |
|---|---|---|---|
| 参考侧 | LRC 逐句 `start_ms` 间隔（评分时从 ref_lines 取） | **秒级**（demo 童谣 4890ms/句） | `bpm_from_onsets([0,4890,9780,…])` → **None**（4890ms > `MAX_IOI_MS=3000` 全被滤掉，有效间隔 <3） |
| 用户侧 | `librosa.onset_detect`（音符级） | **百毫秒级** | 容器内实测 63 个 onset、中位 IOI 640ms → 93.75 BPM |

→ 参考侧恒 `None` → `bpm_ratio_info` 恒定回落 `_coarse_bpm_ratio`（v2 的时长截断比），
`bpm_source` 恒 `duration`：**item7「onset 真实 BPM 替代伪比」从未生效**；
且即便强行放宽过滤，`user 93.75 / ref 12.3 = 7.6`（被 clamp 到 2.0）也是垃圾值——异量纲比无意义。

**文档失真**：docs/06 §9.4 与 worklog 已登记"bpm_ratio 由时长截断比改为 onset 间隔中位"，
与实际行为不符（点值口径的口径登记没有端到端验证支撑）。

## 修复（组长拍板 A2：参考 onset 入库）

1. `pitch.py`：`EXTRACTOR_VERSION = "pyin-v2"`；`slice_window()` 返回值增
   `onsets_ms`（落在该句窗口内的**参考音符级起音**绝对时刻）；
2. `jobs.py`：无需改动（pitch_ref 透传 slice_window 结果；`_refs_ready` 比对版本 →
   **世代升级自动触发重提取**，Python 侧判断，不触碰 Java 独占写的 songs 表）；
3. `sing.py`：评分侧由各句 `pitch_ref.onsets_ms` 拼接去重 → 与用户侧 `onset_detect` **同量纲**；
   `bpm_from_onsets` 增相邻 <50ms onset 合并（librosa 强起音会给出相邻重复帧，实测 480/480、1152/1152）；
   注释/文档串修正（不再写"LRC 间隔"）。

## 验证

- 单测：`tests/test_sing_scorer.py` 增「去重等价」与「异量纲参考侧必须回落 duration（不得伪造节拍）」两个守卫；`tests/test_pitch_extract.py` 断言 `slice_window` 的 `onsets_ms` 窗口语义 + 世代 pyin-v2；
- 容器端到端：重提取后 `song_pitch_refs.version=pyin-v2` 且 `pitch_ref ? 'onsets_ms'` 全覆盖；
  e2e 断言 `bpm_source=onset`、`bpm_user/bpm_ref` 非空、`bpm_ratio<1`（素材为慢 5%）。

## 踩坑

1. **口径登记 ≠ 口径生效**：v3 的 item7 有单测（纯函数层面全绿）却没端到端验证——单测喂的是
   "两侧同量纲"的理想数组，掩盖了真实数据源（LRC 句起点）与用户信号（音符级 onset）的错配。
   教训：**引入跨源统计比的新特性，必须有一步真实链路的数值断言**（本层由 `local/sing_e2e_test.py` 承担）。
2. 过滤窗口 `[200,3000]ms` 是按"音符间隔"设的，套到"句间隔"上会把正常数据全部滤掉而不报错——
   静默回落路径（duration）掩盖了错误，**降级必须留痕**（本次靠 `bpm_source` 字段才发现）。
3. 我最初生成的测试素材用"乘系数"冒充移调（实为幅度缩放），且用线性插值实现"慢 5%"（顺带降了 5% 音高）
   → 险些把"产品正确"误判为 bug。素材实现已改为 `librosa.effects.pitch_shift` / `time_stretch`。
