"""进度钟 / 进度轨纯函数（docs/56 §A；规则层无 DB、无 IO，红线 9 可单测）。

设计依据 docs/55 §2.1：正向钟（玩家目标，满格=完成）与威胁钟（倒计时，满格=坏事发生）共用
同一份 ``quest.{名}.progress``（``"3/6"`` 当前/总格）。规则：
- 格数由系统夹取在 0..segments（工具 delta 1~3，越界夹取而不是报错）；
- 结算档位（strong/weak/miss）由进度比例自动判定，威胁钟语义反转；
- 尾声（标题/正文/后日谈）由模板渲染，**零 LLM 成本**——模型只负责把它叙述出来。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 进度档位（complete_quest 的 outcome）
Outcome = Literal["strong", "weak", "miss"]
ClockKind = Literal["positive", "threat"]

#: 缺省总格数（场景卡未预置 clock 时的兜底；BitD 常用 4/6/8，取中位数 6）
DEFAULT_SEGMENTS = 6
#: 单次 tick 上限（docs/56 §3：delta 1~3，与 BitD 位置/效果档对齐）
TICK_DELTA_MAX = 3
#: 掷骰判定的「大成功」余量（docs/57 §3.1：成功 +1，total-vs ≥5 再 +1）
ROLL_MARGIN_BONUS = 5
#: 自动判定的比例分界（positive：≥0.66 强 / ≥0.25 弱 / 否则失；threat 反转）
_STRONG_RATIO = 0.66
_WEAK_RATIO = 0.25


@dataclass(frozen=True)
class TickResult:
    """一次 tick 的算术结果（落表用）。"""

    current: int
    segments: int
    full: bool

    @property
    def text(self) -> str:
        return format_progress(self.current, self.segments)


def parse_progress(value: str | None) -> tuple[int, int] | None:
    """解析 ``"3/6"`` → ``(3, 6)``；纯数字 ``"3"`` → ``(3, DEFAULT_SEGMENTS)``。

    非法/空 → None（调用方按「未建进度」处理，工具初始化而不是报错）。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "/" in text:
        left, _, right = text.partition("/")
        try:
            current, segments = int(left.strip()), int(right.strip())
        except ValueError:
            return None
        if segments <= 0 or current < 0:
            return None
        return current, segments
    try:
        current = int(text)
    except ValueError:
        return None
    if current < 0:
        return None
    return current, DEFAULT_SEGMENTS


def format_progress(current: int, segments: int) -> str:
    """``(3, 6)`` → ``"3/6"``（当前值夹取在 0..segments，防负数/超格写坏事实）。"""
    segments = max(1, int(segments))
    return f"{clamp_progress(current, segments)}/{segments}"


def clamp_progress(current: int, segments: int) -> int:
    """夹取到 ``0..segments``（segments<=0 视为 1，空钟无意义）。"""
    segments = max(1, int(segments))
    return max(0, min(int(current), segments))


def tick_progress(value: str | None, delta: int, *, default_segments: int = DEFAULT_SEGMENTS):
    """读旧值 + delta → :class:`TickResult`（未建进度按 ``0/默认`` 起）。

    只做算术与夹取；delta 的合法性（非零、|delta|≤3）由工具层校验后传入。
    """
    parsed = parse_progress(value)
    current, segments = parsed if parsed is not None else (0, default_segments)
    current = clamp_progress(current + int(delta), segments)
    return TickResult(current=current, segments=segments, full=current >= segments)


def normalize_kind(value: str | None) -> ClockKind:
    """``threat`` 之外的任何值都按正向钟（宽容；工具入参只认这两值）。"""
    return "threat" if str(value or "").strip() == "threat" else "positive"


def judge_outcome(current: int, segments: int, kind: str = "positive") -> Outcome:
    """结算档位自动判定（docs/56 §3：complete_quest 可省略 outcome）。

    - 正向钟：推进越多越好（≥66% 强 / ≥25% 弱 / 否则失）；
    - 威胁钟：推进越多越糟（倒计时满格=坏结果），比例语义反转。
    """
    segments = max(1, int(segments))
    ratio = clamp_progress(current, segments) / segments
    if normalize_kind(kind) == "threat":
        ratio = 1.0 - ratio
    if ratio >= _STRONG_RATIO:
        return "strong"
    if ratio >= _WEAK_RATIO:
        return "weak"
    return "miss"


def roll_tick_delta(outcome: str | None, margin: int | None, kind: str) -> int:
    """掷骰判定 → 进度钟格数（docs/57 §3.1「推进靠规则不靠自觉」）。

    - 成功：+1；余量（total-vs）≥ :data:`ROLL_MARGIN_BONUS` 再 +1；
    - 失败：威胁钟 +1（正向钟不变——挫折只对倒计时有意义）；
    - 未判定（无 vs / 非法 outcome）：0（保持旧行为，不推进）。
    """
    if outcome == "success":
        return 2 if int(margin or 0) >= ROLL_MARGIN_BONUS else 1
    if outcome == "failure":
        return 1 if normalize_kind(kind) == "threat" else 0
    return 0


@dataclass(frozen=True)
class SettlementPlan:
    """一次结算的纯规则产物（工具与路由共用的唯一结算逻辑；落库由 state 门面做）。"""

    outcome: Outcome
    status: str  # done | failed
    title: str
    text: str
    epilogue: str


def _settled_done_outcome(parsed: tuple[int, int], kind: str | None) -> Outcome:
    """已 done（但结局卡缺失）时的档位兜底：进度判 miss 说明是弱收束，提升为 weak。"""
    judged = judge_outcome(parsed[0], parsed[1], normalize_kind(kind))
    return "weak" if judged == "miss" else judged


def plan_settlement(
    quest: str,
    *,
    requested: str | None = None,
    progress: str | None = None,
    kind: str | None = None,
    stage: str | None = None,
    status: str | None = None,
) -> SettlementPlan:
    """结算计划（纯函数，零 DB；docs/57 §3.1 确定性结算）。

    - ``status`` 已是 done/failed → 幂等：failed 判 miss、done 按进度兜底（不再新判定）；
    - ``requested`` 为合法档位时优先（玩家/路由显式指定）；
    - 否则按 ``progress`` 比例自动判定（威胁钟反转）；
    - 尾声三件套由 :func:`render_ending` 模板渲染。
    """
    parsed = parse_progress(progress) or (0, DEFAULT_SEGMENTS)
    if status in ("done", "failed"):
        outcome: Outcome = "miss" if status == "failed" else _settled_done_outcome(parsed, kind)
    elif requested in ("strong", "weak", "miss"):
        outcome = requested  # type: ignore[assignment]
    else:
        outcome = judge_outcome(parsed[0], parsed[1], normalize_kind(kind))
    ending = render_ending(quest, outcome, stage=stage)
    return SettlementPlan(
        outcome=outcome,
        status="failed" if outcome == "miss" else "done",
        title=ending["title"],
        text=ending["text"],
        epilogue=ending["epilogue"],
    )


#: 结局模板（零 LLM：结局标题/正文/后日谈由服务器模板渲染，quest 名格式化进文案）
ENDING_TEMPLATES: dict[str, dict[str, str]] = {
    "strong": {
        "title": "圆满结局 · {quest}",
        "text": (
            "你以出色的行动力让「{quest}」迎来了最好的收束：该守住的守住了，该揭开的也水落石出。"
        ),
        "epilogue": ("多年以后，酒馆里仍有人提起这一夜——他们说，那是「{quest}」被圆满写下的日子。"),
    },
    "weak": {
        "title": "尘埃落定 · {quest}",
        "text": (
            "「{quest}」在勉力周旋中收场：事情没有变得更好，但也没有彻底失控，"
            "代价与收获都真实地留下。"
        ),
        "epilogue": ("你带着未尽的疑问离开——「{quest}」告一段落，而有些账，只能留给下一次相遇。"),
    },
    "miss": {
        "title": "遗憾收场 · {quest}",
        "text": (
            "「{quest}」最终没能如愿：局势从指缝间滑走，留下的是教训、伤痕，以及尚未熄灭的念头。"
        ),
        "epilogue": (
            "故事没有在此结束——失败的余波仍在暗处回响，而你知道，迟早要回来把「{quest}」重新面对。"
        ),
    },
}


def render_ending(
    quest: str,
    outcome: Outcome,
    *,
    templates: dict[str, dict[str, str]] | None = None,
    stage: str | None = None,
) -> dict[str, str]:
    """渲染尾声三件套 ``{title, text, epilogue}``（模板 + 档位文案，零 LLM）。

    ``stage`` 为可选章节名（并入后日谈的落款，供「调查/对峙/收束」这类阶段收尾）。
    """
    quest_name = str(quest or "").strip() or "未命名任务"
    pack = ENDING_TEMPLATES if templates is None else templates
    block = pack.get(outcome) or ENDING_TEMPLATES[outcome]
    epilogue = block["epilogue"].format(quest=quest_name)
    if stage:
        epilogue = f"{epilogue}（{stage}·落幕）"
    return {
        "title": block["title"].format(quest=quest_name),
        "text": block["text"].format(quest=quest_name),
        "epilogue": epilogue,
    }


def is_full(value: str | None) -> bool:
    """进度是否已满格（威胁钟满格 = 该发生的事发生了）。"""
    parsed = parse_progress(value)
    if parsed is None:
        return False
    current, segments = parsed
    return clamp_progress(current, segments) >= max(1, segments)
