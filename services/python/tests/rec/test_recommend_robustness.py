"""推荐引擎健壮性 + 掌握度联动（水平档 × 兴趣 × 未掌握 + user_corpus_mastery，None 不崩）。

重点：规则推荐引擎只读场景级 ``user_mastery``（未掌握判定 P0 键，由句级
user_corpus_mastery 聚合而来）；本文件验证「聚合结果 → 排序」链路正确，且两张
掌握度表的 None 值不导致崩溃。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.db import get_session_factory
from app.mastery.service import _attempt_score, _status_from
from app.models import (
    MaterialDifficulty,
    Scenario,
    User,
    UserCorpusMastery,
    UserMastery,
    UserProfile,
    UserSkillState,
)
from app.models.base import MasteryStatus
from app.rec.service import recommend_scenes


def _mk_user(level: str, tags: list[str]) -> int:
    db = get_session_factory()()
    try:
        u = User(username=f"r{uuid4().hex[:8]}", nickname="t", password_hash="x")
        db.add(u)
        db.flush()
        db.add(UserProfile(user_id=u.id, interest_tags=tags, cefr_level=level))
        db.add(
            UserSkillState(
                user_id=u.id,
                pron_est=0,
                flu_est=0,
                est_score=0,
                est_level=level,
                confidence=Decimal("1.0"),
            )
        )
        db.commit()
        return int(u.id)
    finally:
        db.close()


def _mk_scene(title: str, diff_level: str, tags: list[str], scene_type: str = "cafe") -> int:
    db = get_session_factory()()
    try:
        s = Scenario(
            title=title,
            scene_type=scene_type,
            difficulty=2,
            system_prompt="p",
            opening_line="o",
            target_corpus="Hi|你好",
            interest_tags=tags,
            status="published",
        )
        db.add(s)
        db.flush()
        db.add(
            MaterialDifficulty(
                content_type="scene",
                content_id=s.id,
                diff_score=Decimal("70"),
                diff_level=diff_level,
                version="expert-v1",
            )
        )
        db.commit()
        return int(s.id)
    finally:
        db.close()


def _mk_mastery(
    user_id: int,
    scene_id: int,
    status: str,
    days_ago: int | None,
    last_score: Decimal | None = None,
) -> None:
    db = get_session_factory()()
    try:
        lp = datetime.now(UTC) - timedelta(days=days_ago) if days_ago is not None else None
        db.add(
            UserMastery(
                user_id=user_id,
                content_type="scene",
                content_id=scene_id,
                status=status,
                last_score=last_score,
                last_practiced_at=lp,
                attempt_count=1,
                pass_count=1 if status == "mastered" else 0,
            )
        )
        db.commit()
    finally:
        db.close()


class TestLevelTagMasteryFilter:
    def test_level_window_tag_mastery_order(self) -> None:
        """水平档过滤（无 L4）× 兴趣命中 × 未掌握优先：排序 = 未掌握>难度>兴趣>已掌握。"""
        uid = _mk_user("L2", ["coffee"])
        a_nm = _mk_scene("A_nm_L2_coffee", "L2", ["coffee"], "cafe")
        e_notag = _mk_scene("E_nm_L2_notag", "L2", [], "other")
        c_l3 = _mk_scene("C_nm_L3", "L3", ["coffee"], "library")
        b_ms = _mk_scene("B_ms_L2", "L2", ["coffee"], "airport")
        _mk_scene("D_l4_L4", "L4", ["coffee"], "interview")  # 仅验证水平窗排除，不绑定变量
        _mk_mastery(uid, a_nm, "not_mastered", None)
        _mk_mastery(uid, e_notag, "not_mastered", None)
        _mk_mastery(uid, c_l3, "not_mastered", None)
        _mk_mastery(uid, b_ms, "mastered", 30)
        db = get_session_factory()()
        try:
            items = recommend_scenes(uid, limit=6, db=db)
            titles = [it["title"] for it in items]
            levels = [it["diff_level"] for it in items]
            # 1) 水平窗：L2 用户看不到 L4（各场景 scene_type 互异，避免同类型上限挤掉）
            assert "D_l4_L4" not in titles
            assert all(lv != "L4" for lv in levels)
            # 2) 未掌握(L2) 排在 已掌握(L2) 之前
            assert titles.index("A_nm_L2_coffee") < titles.index("B_ms_L2")
            # 3) 同档未掌握：兴趣命中(1) 排在 未命中(0) 之前
            assert titles.index("A_nm_L2_coffee") < titles.index("E_nm_L2_notag")
            # 4) 同级难度距离：L2(距离0) 在 L3(距离1) 之前（同为未掌握/同兴趣）
            assert titles.index("A_nm_L2_coffee") < titles.index("C_nm_L3")
            # 5) 已掌握应垫底（在全部未掌握之后）
            assert titles.index("B_ms_L2") == max(titles.index(t) for t in titles)
        finally:
            db.close()


class TestNoneRobustness:
    def test_none_mastery_fields_no_crash(self) -> None:
        """user_mastery / user_corpus_mastery 的 last_score、last_practiced_at=None 不崩。"""
        uid = _mk_user("L2", ["coffee"])
        s = _mk_scene("x", "L2", ["coffee"], "cafe")
        db = get_session_factory()()
        try:
            db.add(
                UserMastery(
                    user_id=uid,
                    content_type="scene",
                    content_id=s,
                    status=MasteryStatus.NOT_MASTERED,
                    last_score=None,
                    last_practiced_at=None,
                    attempt_count=0,
                    pass_count=0,
                )
            )
            db.add(
                UserCorpusMastery(
                    user_id=uid,
                    scenario_id=s,
                    line_index=1,
                    phrase="Hi",
                    status=MasteryStatus.NOT_MASTERED,
                    last_score=None,
                    last_practiced_at=None,
                )
            )
            db.commit()
            items = recommend_scenes(uid, limit=6, db=db)
            assert items  # 不崩溃且返回有效场景
            assert any(it["id"] == s for it in items)
            # 未掌握会话仍语义正确：全部 not_mastered
            assert all(it["mstatus"] == MasteryStatus.NOT_MASTERED for it in items)
        finally:
            db.close()

    def test_mastery_helpers_skip_none_scores(self) -> None:
        """聚合路径：pron/flu 缺分被跳过；attempt_count=0 → not_mastered。"""
        # 两维缺一 → 该 attempt 不计分
        assert _attempt_score(SimpleNamespace(pron_score=None, flu_score=80)) is None
        assert _attempt_score(SimpleNamespace(pron_score=70, flu_score=None)) is None
        assert _attempt_score(SimpleNamespace(pron_score=70, flu_score=80)) == 0.6 * 70 + 0.4 * 80
        # 状态判定在 0 样本下不崩
        assert _status_from(0.0, 0, 0) == MasteryStatus.NOT_MASTERED
        assert _status_from(80.0, 3, 2) == MasteryStatus.MASTERED
        assert _status_from(70.0, 3, 1) == MasteryStatus.IN_PROGRESS

    def test_recommend_reads_scene_mastery_not_corpus(self) -> None:
        """联动锁定：推荐只读场景级 UserMastery；句级 UserCorpusMastery 不影响排序。

        场景级已 mastered，但句级故意写成 not_mastered——若推荐误读句级，该场景会被顶到前面，
        下面断言会变红；实际应凭场景级 mastered 排在末位。
        """
        uid = _mk_user("L2", ["coffee"])
        link = _mk_scene("link_mastered", "L2", ["coffee"], "cafe")
        _mk_scene("fresh_nm", "L2", ["coffee"], "library")
        _mk_mastery(uid, link, "mastered", days_ago=30)
        db = get_session_factory()()
        try:
            db.add(
                UserCorpusMastery(
                    user_id=uid,
                    scenario_id=link,
                    line_index=1,
                    phrase="Hi",
                    status=MasteryStatus.NOT_MASTERED,  # 与场景级相反，不应影响推荐
                    last_score=None,
                    last_practiced_at=None,
                )
            )
            db.commit()
            items = recommend_scenes(uid, limit=6, db=db)
            titles = [it["title"] for it in items]
            # 场景级 mastered → link 应排最后（fresh 未掌握在前）
            assert "fresh_nm" in titles and "link_mastered" in titles
            assert titles.index("fresh_nm") < titles.index("link_mastered")
            link_item = next(it for it in items if it["title"] == "link_mastered")
            assert link_item["mstatus"] == MasteryStatus.MASTERED
        finally:
            db.close()


class TestOrderingEdgeCases:
    def test_freshness_ordering(self) -> None:
        """新鲜靠后：同档、同未掌握、同兴趣 → 从未练 排在 练过 之前。"""
        uid = _mk_user("L2", ["coffee"])
        # 先创建 practiced（低 id）；若缺少「新鲜」排序维度，按 id 序 practiced 会排前 → 用例变红
        practiced = _mk_scene("practiced_cafe", "L2", ["coffee"], "cafe")
        _mk_mastery(uid, practiced, "not_mastered", days_ago=1)  # 练过 1 天前
        _mk_scene("fresh_cafe", "L2", ["coffee"], "cafe")  # 无 mastery → last_practiced=None
        db = get_session_factory()()
        try:
            items = recommend_scenes(uid, limit=6, db=db)
            titles = [it["title"] for it in items]
            assert "fresh_cafe" in titles and "practiced_cafe" in titles
            assert titles.index("fresh_cafe") < titles.index("practiced_cafe")
        finally:
            db.close()

    def test_main_window_diversity_cap(self) -> None:
        """主窗内同 scene_type ≤2：即使 limit 有空间，同类型最多 2 条。"""
        uid = _mk_user("L2", ["coffee"])
        _mk_scene("cafeA_main", "L2", ["coffee"], "cafe")
        _mk_scene("cafeB_main", "L2", ["coffee"], "cafe")
        _mk_scene("cafeC_main", "L2", ["coffee"], "cafe")  # 第 3 条 cafe，应被挤出
        _mk_scene("lib_main", "L2", [], "library")
        _mk_scene("airport_main", "L2", [], "airport")
        db = get_session_factory()()
        try:
            items = recommend_scenes(uid, limit=6, db=db)
            titles = [it["title"] for it in items]
            cafe_present = sum(titles.count(t) for t in ("cafeA_main", "cafeB_main", "cafeC_main"))
            assert cafe_present == 2, f"主窗同类型应 ≤2：{titles}"
            assert "cafeC_main" not in titles
            # 应兜底填充其它类型
            assert "lib_main" in titles or "airport_main" in titles
        finally:
            db.close()

    def test_ordering_by_difficulty_distance(self) -> None:
        """同未掌握/同兴趣：难度距离近(L2) 在远(L3) 之前。"""
        uid = _mk_user("L2", ["coffee"])
        # far 先创建（低 id）；若缺「难度距离」排序维度，按 id 序 far 会排前 → 用例变红
        _mk_scene("far_L3", "L3", ["coffee"], "library")
        _mk_scene("near_L2", "L2", ["coffee"], "cafe")
        db = get_session_factory()()
        try:
            items = recommend_scenes(uid, limit=6, db=db)
            titles = [it["title"] for it in items]
            assert titles.index("near_L2") < titles.index("far_L3")
        finally:
            db.close()


class TestExpansionAndReviewEdge:
    def test_expansion_respects_pm1_band(self) -> None:
        """扩档只在 ±1 档内：L3 用户 主窗不足 → 补 L2(距离1)；不补 L1(距离2)。"""
        uid = _mk_user("L3", ["coffee"])
        _mk_scene("l3a", "L3", ["coffee"], "library")
        _mk_scene("l4a", "L4", ["coffee"], "other")
        _mk_scene("l2a", "L2", ["coffee"], "cafe")  # ±1 内，应被扩档补入
        _mk_scene("l1a", "L1", ["coffee"], "airport")  # 距离 2，不应补入
        db = get_session_factory()()
        try:
            items = recommend_scenes(uid, limit=6, db=db)
            titles = [it["title"] for it in items]
            assert "l2a" in titles, f"L2(±1) 应被扩档补入：{titles}"
            assert "l1a" not in titles, f"L1(距离2) 不应被扩档：{titles}"
        finally:
            db.close()

    def test_expansion_only_when_insufficient(self) -> None:
        """主窗已够 limit → 不扩档：L1 素材不会出现。"""
        uid = _mk_user("L2", ["coffee"])
        _mk_scene("e_cafe", "L2", ["coffee"], "cafe")
        _mk_scene("e_airport", "L2", ["coffee"], "airport")
        _mk_scene("e_lib", "L2", ["coffee"], "library")
        _mk_scene("e_interview", "L3", ["coffee"], "interview")
        _mk_scene("e_other", "L3", ["coffee"], "other")
        _mk_scene("l1_x", "L1", ["coffee"], "cafe")
        db = get_session_factory()()
        try:
            items = recommend_scenes(uid, limit=5, db=db)
            titles = [it["title"] for it in items]
            assert len(items) == 5
            assert "l1_x" not in titles, "主窗已足，不应扩档 L1"
        finally:
            db.close()

    def test_review_slot_not_when_main_full(self) -> None:
        """L4 用户主窗已满(limit) → 复习席不再补（无空位），stale L3 不出现。"""
        uid = _mk_user("L4", ["coffee"])
        _mk_scene("rv_a", "L4", ["coffee"], "cafe")
        _mk_scene("rv_b", "L4", ["coffee"], "airport")
        _mk_scene("rv_c", "L4", ["coffee"], "library")
        stale = _mk_scene("l3_stale", "L3", ["coffee"], "other")
        _mk_mastery(uid, stale, "mastered", days_ago=30)  # 复习席候选，但主窗已满
        db = get_session_factory()()
        try:
            items = recommend_scenes(uid, limit=3, db=db)
            titles = [it["title"] for it in items]
            assert len(items) == 3  # 主窗填满，不再扩档/补复习
            assert "l3_stale" not in titles
        finally:
            db.close()
