"""学习者画像域（ai4u memory-injector 的 VocalVerse 版，docs/26 P0 · docs/24 ⑥）。

把「掌握度/词级错误/动态水平」三类既有数据（只读，零迁移）渲染为一行注入
prompt 的易错点清单（≤learner_max_items 条），随每次回合注入（docs/26 §8③）。

- ingest 链：attempts × corpus_hit → user_corpus_mastery（句级，python 写）；
  词级错误来自 ISE 评分 results.word_level（词首音素 error_type，试探性判定——真 Key
  冒烟核验后回写谓词，见 https://github.com/Sui-IB/InternalBeyond 无关，本域为自研实现）；
- 缓存：进程内 TTL（learner_cache_ttl_s=900）+ invalidate（会话收尾钩子）——单进程模型
  （会话状态/锁同在进程内），多 worker 时需迁 Redis（docs/26 §5 注记）；
- 文案原则：'do not overcorrect'——注入是给模型"温柔处理"的上下文，不是问责清单。
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import get_settings
from app.db import get_session_factory
from app.models import Attempt, UserCorpusMastery
from app.models.base import AttemptKinds, MasteryStatus

logger = logging.getLogger("vocalverse")

# ISE 词级 error_type 中明确表示「无误」的值；其余视为疑似错误信号
# （E0 = 讯飞 ISE 英文标准音；空串/other = ise.py 解析缺省「未判定」，不算错误——A 官 F04 修正）
_NON_ERROR_TYPES = ("", "other", "E0")
# 词总分低于该值同样视为薄弱（独立于 error_type 的弱信号）
_WORD_SCORE_WEAK = 60.0

_cache: dict[int, tuple[str, float]] = {}


@dataclass(frozen=True)
class LearnerProfile:
    """学习者画像快照（全字段可为空；空画像不应注入任何内容）。"""

    weak_phrases: list[str]  # user_corpus_mastery.status=not_mastered，语义最近未掌握在前
    weak_words: list[str]  # 词级错误频次 top-N（窗口 learner_word_error_window 条 attempt）
    est_level: str | None  # user_skill_state.est_level（confidence 达门槛才给）


def _is_weak_word(word: dict) -> bool:
    """词级错误谓词：error_type 非「无误」或 词分 < 60（防 ise.py 空串误判——A 官 F04）。"""
    etype = str(word.get("error_type") or "").strip()
    if etype not in _NON_ERROR_TYPES:
        return True
    score = word.get("score")
    return isinstance(score, (int, float)) and float(score) < _WORD_SCORE_WEAK


def _aggregate_weak_words(db, user_id: int, window: int) -> list[str]:
    """Python 侧聚合最近 window 条 dialog attempt 的 word_level（不用 PG 专属 JSONB 函数，
    SQLite 单测可跑——docs/24 拷问 F03）。"""
    rows = db.execute(
        select(Attempt.details)
        .where(Attempt.user_id == user_id, Attempt.kind == AttemptKinds.DIALOG_SPEECH)
        .order_by(Attempt.id.desc())
        .limit(window)
    ).scalars()
    counter: Counter[str] = Counter()
    for details in rows:
        if not isinstance(details, dict):
            continue  # jsonb 可能被写入非 dict（F08 防御）
        words = details.get("word_level")
        if not isinstance(words, list):
            continue
        for w in words:
            if not isinstance(w, dict):
                continue
            word = str(w.get("word") or "").strip()
            if word and _is_weak_word(w):
                counter[word] += 1
    return [w for w, _ in counter.most_common()]  # 同频次按词序稳定（Counter 保持插入序）


def build_profile(db, user_id: int) -> LearnerProfile:
    """从库只读聚合（无副作用）；无任何数据 → 全空画像。"""
    cfg = get_settings()
    weak_phrases = list(
        db.execute(
            select(UserCorpusMastery.phrase)
            .where(
                UserCorpusMastery.user_id == user_id,
                UserCorpusMastery.status == MasteryStatus.NOT_MASTERED,
            )
            .order_by(UserCorpusMastery.last_practiced_at.desc().nulls_last())
            .limit(cfg.learner_max_items)
        ).scalars()
    )
    weak_words = _aggregate_weak_words(db, user_id, cfg.learner_word_error_window)[
        : cfg.learner_max_items
    ]
    est_level: str | None = None
    try:
        from app.models.skill import UserSkillState

        row = db.execute(
            select(UserSkillState).where(UserSkillState.user_id == user_id)
        ).scalar_one_or_none()
        if row is not None and float(row.confidence) >= cfg.skill_confidence_min:
            est_level = row.est_level
    except Exception as exc:  # 水平域异常不阻塞画像构建
        logger.debug("learner est_level skipped: %s", exc)
    return LearnerProfile(weak_phrases=weak_phrases, weak_words=weak_words, est_level=est_level)


def render(profile: LearnerProfile) -> str:
    """纯函数渲染注入块；空画像返回 ""（调用方整行省略）。"""
    parts: list[str] = []
    if profile.weak_phrases:
        parts.append("weak phrases: " + "; ".join(profile.weak_phrases))
    if profile.weak_words:
        parts.append("frequent word errors: " + "; ".join(profile.weak_words))
    if not parts:
        return ""
    line = "Learner profile (internal): " + "; ".join(parts)
    if profile.est_level:
        line += f"; est. level: {profile.est_level}"
    line += ". Gently address these, do not overcorrect."
    return line


def get_rendered(user_id: int) -> str:
    """带 TTL 缓存的注入行；开关关闭 / 任何异常 → ""（不阻塞回合）。"""
    try:
        cfg = get_settings()
        if not cfg.learner_injection_enabled:
            return ""
        now = time.time()
        hit = _cache.get(int(user_id))
        if hit is not None and hit[1] > now:
            return hit[0]
        db = get_session_factory()()
        try:
            text = render(build_profile(db, int(user_id)))
        finally:
            db.close()
        _cache[int(user_id)] = (text, now + cfg.learner_cache_ttl_s)
        return text
    except Exception as exc:  # 画像失败静默降级为空（同 ai4u memory-injector 失败不阻塞原则）
        logger.warning("learner profile skipped user=%s: %s", user_id, exc)
        return ""


def invalidate(user_id: int) -> None:
    """会话收尾后失效（新评分/掌握度已落库，下次构建应读到新数据）。幂等。"""
    _cache.pop(int(user_id), None)


__all__ = ["LearnerProfile", "build_profile", "render", "get_rendered", "invalidate"]
