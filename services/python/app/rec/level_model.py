"""水平预测模型（docs/06 §9.5 · docs/53 P3）：sklearn 线性回归 + joblib 持久化。

- 训练一次、启动加载（**严禁每请求重训**，docs/06 §9.5）：首次调用训练并 dump 到
  `settings.level_model_path`，之后直接 load；
- 训练数据 = **确定性合成样本**（docs/06 §9.5 明文「用 sklearn 合成数据训练，走接口」；
  真实行为数据不足以训练，答辩口径「demo 验证」）：特征 [近窗均分, 趋势斜率, 录音数, 活跃天数]
  → 目标 = 下一窗均分（生成式：y = clamp(avg + 1.5·slope + 0.8·log1p(n) + 0.3·active, 0, 100)）；
- 用途 = 学习页「进步趋势」展示（预测值 + 方向），**不参与判档**（档位仍由入学测试/复测决定，
  docs/15 B 口径：练习分不直接改档）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.practice import Attempt

logger = logging.getLogger("vocalverse")
MODEL_VERSION = "level-forecast-v1"
_FEATURES = 4


def _synthetic(seed: int = 20260921) -> tuple[list[list[float]], list[float]]:
    """确定性合成训练集（无随机源；150 条覆盖低/中/高分与正负趋势）。"""
    rows: list[list[float]] = []
    ys: list[float] = []
    for i in range(150):
        avg = 45.0 + (i * 7 % 51)  # 45~95
        slope = ((i * 13) % 21 - 10) / 10.0  # -1.0 ~ +1.0
        n = float(i % 25)
        active = float(i % 14)
        y = avg + 1.5 * slope + 0.8 * (n**0.5) + 0.3 * active
        rows.append([avg, slope, n, active])
        ys.append(max(0.0, min(100.0, y)))
    return rows, ys


def _train_and_save(path: Path) -> Any:
    from sklearn.linear_model import Ridge

    x, y = _synthetic()
    model = Ridge(alpha=1.0)
    model.fit(x, y)
    try:
        import joblib

        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, path)
    except Exception as exc:  # 持久化失败不影响本次预测（下次重训）
        logger.warning("水平预测模型持久化失败：%s", exc)
    return model


def get_model() -> Any:
    """训练一次 + 启动加载（进程内缓存；文件缺失/损坏则重训）。"""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    path = Path(get_settings().level_model_path)
    if path.exists():
        try:
            import joblib

            _MODEL = joblib.load(path)
            return _MODEL
        except Exception as exc:
            logger.warning("水平预测模型加载失败，重训：%s", exc)
    _MODEL = _train_and_save(path)
    return _MODEL


_MODEL: Any = None


def forecast(db: Session, user_id: int, *, days: int = 30) -> dict:
    """按最近 attempts 行为预测「下一窗口」综合分（无数据 → 返回空态，不伪造）。"""
    from datetime import UTC, datetime, timedelta

    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    rows = db.execute(
        select(Attempt.overall_score, Attempt.created_at)
        .where(
            Attempt.user_id == user_id,
            Attempt.created_at >= start,
            Attempt.created_at <= end,
            Attempt.overall_score.is_not(None),
        )
        .order_by(Attempt.created_at)
    ).all()
    scores = [float(r[0]) for r in rows if r[0] is not None]
    if not scores:
        return {"available": False, "reason": "no_attempts", "model_version": MODEL_VERSION}

    avg = sum(scores) / len(scores)
    half = max(1, len(scores) // 2)
    first, second = scores[:half], scores[half:]
    slope = (sum(second) / len(second) - sum(first) / len(first)) if second else 0.0
    active_days = len({r[1].date() for r in rows if r[1] is not None})
    model = get_model()
    predicted = float(model.predict([[avg, slope, float(len(scores)), float(active_days)]])[0])
    predicted = round(max(0.0, min(100.0, predicted)), 2)
    delta = round(predicted - avg, 2)
    return {
        "available": True,
        "model_version": MODEL_VERSION,
        "predicted_overall": predicted,
        "current_avg": round(avg, 2),
        "delta": delta,
        "direction": "up" if delta >= 1 else ("down" if delta <= -1 else "flat"),
        "basis": {
            "attempts": len(scores),
            "slope": round(slope, 2),
            "active_days": active_days,
            "window_days": days,
        },
        "note": "合成数据训练的 demo 模型（docs/06 §9.5），仅作进步趋势展示，不参与判档",
    }


def attempts_count(db: Session, user_id: int) -> int:
    stmt = select(func.count()).select_from(Attempt).where(Attempt.user_id == user_id)
    return int(db.execute(stmt).scalar() or 0)
