"""唱歌端点响应 DTO（P1-14 修复：给 5+ 端点补 `response_model`，让契约快照含真 schema）。

依据（2026-09-10 · 拷问报告 P1-14）：
唱歌端点此前**无 `response_model`** → `python-openapi.json` 里这些响应是空 schema `{}` →
`pnpm gen:api` 生成的 TS 类型无内容 → 前端只能**手写** DTO（`apps/web/src/api/sing.ts`），
契约漂移无人拦（实测已漂移：`alignment.bpm_source` 前端写成 `'onset' | 'duration'`，后端实际
`onset-f0|onset-flux|onset-arbitrated|duration`）。现由本模块集中声明响应模型：

- 与 service 层 `_song_summary` / `_result_dict` / `_status_payload` 的键**一一对应**，
  新增字段需同时改这里与 docs（docs/10 §4.3 / docs/21 §3.6）——否则前端类型缺少该字段；
- `SingAlignment` 用 `extra="allow"`：口径升级新增的诊断键必须**原样透传**
  （响应模型不得静默吞字段），同时已知字段获得真实类型（`bpm_source` 闭合四值见
  docs/06 §9.4 口径 v3 item7）；
- 闭集字段（`bpm_source`/`pitch_reliability`）用 `Literal`：新值 = 契约变更，
  须同步 docs 与前端类型；
- **本次不改任何响应键**（纯 schema 补齐）：`tests/test_sing_schemas.py` 断言「加 `response_model`
  前后响应体逐键相等」，并覆盖 alignment 未知键透传。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# docs/06 §9.4 口径 v3 item7：闭合四值（回退时长比 → "duration"）
BpmSource = Literal["onset-f0", "onset-flux", "onset-arbitrated", "duration"]
# docs/06 §9.4 item8：参考完整性驱动的音准置信档
PitchReliability = Literal["full", "reduced", "low"]


class PitchRef(BaseModel):
    """逐句参考旋律（song_pitch_refs.pitch_ref；docs/10 §4.3 · pyin-v2）。"""

    f0s: list[float] = Field(default_factory=list)
    notes: list[str | None] = Field(default_factory=list)
    midi: list[int | None] = Field(default_factory=list)
    # pyin-v2：落在本句窗口内的参考音符级起音（口径 v3 item7 的参考侧数据源；旧世代无此键）
    onsets_ms: list[float] | None = None


class SongSummary(BaseModel):
    """选歌列表条目（`GET /api/v1/songs`）。"""

    id: int
    title: str
    artist: str | None = None
    level: int
    duration_s: int | None = None
    bpm: float | None = None
    musical_key: str | None = None
    cover_url: str | None = None
    # 参考旋律音频（共享卷路径）：前端取 basename 走 /api/v1/audio/{name} 回放
    audio_url: str | None = None
    pitch_ref_status: str
    expected_lines: int
    # 当前用户收藏态（2026-09-10）：前端每首歌一个收藏按钮的初始态
    favorited: bool


class SongLine(BaseModel):
    """歌曲详情的逐句 LRC + 参考旋律（D3 双序列图数据源）。"""

    seq: int
    start_ms: int
    end_ms: int | None = None
    text: str | None = None
    pitch_ref: PitchRef


class SongDetail(SongSummary):
    """`GET /api/v1/songs/{id}`：列表字段 + 逐句数据。"""

    lines: list[SongLine]


class FavoriteState(BaseModel):
    """收藏切换结果（PUT=收藏 / DELETE=取消，均幂等；docs/21 §3.6）。"""

    song_id: int
    favorited: bool


class SubmitAck(BaseModel):
    """整首上传受理回执（`POST /api/v1/sessions/{id}/audio`）。"""

    attempt_id: int
    status: str


class TaskProgress(BaseModel):
    """任务进度（轮询展示用）。"""

    done_lines: int = 0
    total: int = 0


class AttemptStatus(BaseModel):
    """任务状态（queued→processing→done|failed；轮询端点）。

    `code` 仅失败态回带（50003 算法失败 / 50002 任务态丢失，docs/api/error-codes.md）。
    """

    attempt_id: int
    status: str
    progress: TaskProgress
    error: str | None = None
    code: int | None = None


class ScoreLine(BaseModel):
    """逐句评分（sing_attempts.lines[i]；结构契约 docs/10 §4.3）。"""

    seq: int
    start_ms: int
    end_ms: int | None = None
    pitch_score: float | None = None
    rhythm_score: float | None = None
    pron_score: float | None = None
    synced: bool = True
    skipped: bool = False
    # no_pitch / no_ref / low_frames / no_onset（v5 起"无新起唱"句 rhythm=None）
    reason: str | None = None
    ref_seq: int | None = None
    no_ref: bool = False
    # v2：该句起唱偏差 ms（null=未检出，或该次演唱无换气结构——口径 v4 · R1）
    onset_dev_ms: float | None = None
    # v4 · R2：音符命中率 0~1（null=参考无音符）
    note_hit_rate: float | None = None
    # D4：用户逐帧 F0 [[t_ms, f0_hz], ...]
    user_f0: list[list[float]] = Field(default_factory=list)
    # D3：帧级折叠 cent 偏差（对齐后；含整体移调口径）
    cent_dev: list[float] = Field(default_factory=list)


class SingAlignment(BaseModel):
    """整首对齐与口径留痕（docs/10 §4.3 alignment 扩展；口径 v3/v4/v5）。

    `extra="allow"`：口径升级新增的诊断键**必须透传**——响应模型只做类型标注，不做过滤。
    """

    model_config = ConfigDict(extra="allow")

    # item7：两路 onset 在 BPM 层仲裁所得真实节奏比（不可用回退时长比并标 duration）
    bpm_ratio: float | None = None
    bpm_user: float | None = None
    bpm_ref: float | None = None
    bpm_source: BpmSource | None = None
    offset_ms: float | None = None
    # v6 · F1：整首时间弯折（stretch>1 = 用户更慢）；句窗端点 = offset_ms + stretch × 参考时刻
    time_warp_stretch: float | None = None
    # v6：逐句用户时间轴窗口 [[seq, start_ms, end_ms], ...]（发音抽样/图表/排障共用同一份映射）
    windows_ms: list[list[float]] | None = None
    method: str | None = None
    version: str | None = None
    # item5/6：移调与滤波留痕
    transpose_semitones: int | None = None
    range_hint: str | None = None
    medfilt_kernel: int | None = None
    # item8：参考完整性驱动的音准权重
    ref_coverage: float | None = None
    pitch_weight: float | None = None
    pitch_reliability: PitchReliability | None = None
    weight_note: str | None = None
    # v4 · R2/R3：音符命中率 + 有效句覆盖率置信度
    note_hit_rate: float | None = None
    user_coverage: float | None = None
    coverage_conf: float | None = None
    coverage_note: str | None = None
    # v5 · R1 留痕：整轨换气结构（判据已下沉逐句 reason='no_onset'）
    breath_structure: bool | None = None


class AttemptResult(BaseModel):
    """跟唱评分结果（`GET /api/v1/sing/attempts/{id}`；done 后可取）。

    `overall` **允许为 null**：v4/v5 覆盖率 <40% 不给综合分（docs/06 §9.4 口径 v4 · R3）。
    """

    id: int
    song_id: int
    audio_url: str | None = None
    duration_s: int | None = None
    overall: float | None = None
    pitch: float | None = None
    rhythm: float | None = None
    pron: float | None = None
    is_complete: bool
    expected_lines: int
    scoring_version: str
    ref_version: str | None = None
    # lines/alignment **必返**（service 层恒写：无结果 = 空数组/空对象）——不给默认值，
    # 生成的 TS 类型才是必填，前端无需对 `undefined` 兜底（P1-14：类型即契约）
    lines: list[ScoreLine]
    alignment: SingAlignment
    created_at: str | None = None
