"""会话收尾挂钩（_post_session_skills）：更新动态水平/掌握度后应主动失效推荐缓存。"""

from __future__ import annotations

import app.practice.service as ps


class _Db:
    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class _Session:
    id = 1
    user_id = 7


def test_post_session_skills_invalidates_rec_cache(monkeypatch) -> None:
    """写完 user_mastery / user_skill_state 后必须 invalidate_recommendation_cache(user_id)。"""
    calls: dict[str, list] = {"mastery": [], "level": [], "inv": []}

    def fake_mastery(db, sid: int) -> None:
        calls["mastery"].append(sid)

    def fake_level(uid: int, db) -> None:
        calls["level"].append(uid)

    def fake_inv(uid: int) -> None:
        calls["inv"].append(uid)

    monkeypatch.setattr("app.mastery.service.update_session_mastery", fake_mastery)
    monkeypatch.setattr("app.skill.service.update_user_level", fake_level)
    monkeypatch.setattr("app.rec.service.invalidate_recommendation_cache", fake_inv)

    ps._post_session_skills(_Db(), _Session())

    # 顺序：先写掌握度/水平，再失效缓存
    assert calls["mastery"] == [1]
    assert calls["level"] == [7]
    assert calls["inv"] == [7], "写路径后必须主动失效推荐缓存"
