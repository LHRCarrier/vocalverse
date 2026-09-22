"""跑团闭环纯函数测试（docs/56 §7）：progress / encounter / items + writer 白名单。

纯模块无 DB、无 IO（红线 9），边界：夹取 / 满格 / 自动档位 / 回绕 / 数量校验 / 未知道具。
"""

from __future__ import annotations

from app.trpg import encounter, items, progress
from app.trpg.facts import FactOp, adjudicate_upsert, check_key_whitelist
from app.trpg.snapshot import SnapshotFact, SnapshotInput, build_state_snapshot

# ---------------------------------------------------------------------------
# progress：解析 / 格式 / tick / 满格 / 自动档位 / 尾声模板
# ---------------------------------------------------------------------------


def test_progress_parse_and_format():
    assert progress.parse_progress("3/6") == (3, 6)
    assert progress.parse_progress(" 3 / 6 ") == (3, 6)
    assert progress.parse_progress("2") == (2, progress.DEFAULT_SEGMENTS)
    assert progress.parse_progress("") is None
    assert progress.parse_progress(None) is None
    assert progress.parse_progress("abc") is None
    assert progress.parse_progress("-1/6") is None
    assert progress.parse_progress("3/0") is None
    assert progress.parse_progress("3/6/9") is None

    assert progress.format_progress(3, 6) == "3/6"
    assert progress.format_progress(9, 6) == "6/6"  # 超格夹取
    assert progress.format_progress(-2, 6) == "0/6"
    assert progress.format_progress(0, 0) == "0/1"  # 空钟无意义 → 至少 1 格


def test_progress_clamp_and_tick():
    assert progress.clamp_progress(-5, 6) == 0
    assert progress.clamp_progress(99, 6) == 6

    tick = progress.tick_progress("3/6", 2)
    assert (tick.current, tick.segments, tick.full, tick.text) == (5, 6, False, "5/6")
    full = progress.tick_progress("5/6", 3)
    assert full.current == 6 and full.full is True
    down = progress.tick_progress("1/6", -3)
    assert down.current == 0 and down.full is False  # 负向也夹在 0
    fresh = progress.tick_progress(None, 1)
    assert (
        fresh.current == 1 and fresh.segments == progress.DEFAULT_SEGMENTS and fresh.full is False
    )
    assert progress.tick_progress("3/6", 0).current == 3  # 纯算术不校验 delta


def test_progress_judge_outcome_positive_and_threat():
    assert progress.judge_outcome(6, 6, "positive") == "strong"
    assert progress.judge_outcome(4, 6, "positive") == "strong"  # 0.66 边界
    assert progress.judge_outcome(3, 6, "positive") == "weak"
    assert progress.judge_outcome(1, 6, "positive") == "miss"
    assert progress.judge_outcome(0, 6, "positive") == "miss"
    # 威胁钟语义反转：越满越糟
    assert progress.judge_outcome(6, 6, "threat") == "miss"
    assert progress.judge_outcome(3, 6, "threat") == "weak"
    assert progress.judge_outcome(0, 6, "threat") == "strong"
    assert progress.judge_outcome(0, 0, "positive") == "miss"  # 非法格数兜底
    assert progress.normalize_kind(None) == "positive"
    assert progress.normalize_kind("threat") == "threat"
    assert progress.normalize_kind("weird") == "positive"


def test_progress_render_ending_templates():
    strong = progress.render_ending("寻找失落的戒指", "strong")
    assert set(strong) == {"title", "text", "epilogue"}
    assert "寻找失落的戒指" in strong["title"]
    assert "寻找失落的戒指" in strong["text"] and "寻找失落的戒指" in strong["epilogue"]
    assert progress.render_ending("找戒指", "miss")["title"].startswith("遗憾收场")
    with_stage = progress.render_ending("找戒指", "weak", stage="收束")
    assert "收束·落幕" in with_stage["epilogue"]
    custom = progress.render_ending(
        "找戒指", "strong", templates={"strong": {"title": "T", "text": "X", "epilogue": "E"}}
    )
    assert custom == {"title": "T", "text": "X", "epilogue": "E"}
    assert progress.is_full("6/6") is True and progress.is_full("5/6") is False


def test_progress_roll_tick_delta_rule():
    """掷骰 → 进度格数（docs/57 §3.1）：成功 +1、余量≥5 +2；失败只推威胁钟。"""
    assert progress.roll_tick_delta("success", 1, "positive") == 1
    assert progress.roll_tick_delta("success", 4, "threat") == 1
    assert progress.roll_tick_delta("success", 5, "positive") == 2
    assert progress.roll_tick_delta("success", 12, "threat") == 2
    assert progress.roll_tick_delta("failure", -3, "threat") == 1
    assert progress.roll_tick_delta("failure", -3, "positive") == 0
    assert progress.roll_tick_delta(None, None, "positive") == 0  # 无 vs 不判定


def test_progress_plan_settlement():
    """结算计划（纯函数，工具与路由共用）：显式档位优先；已结算幂等兜底。"""
    auto = progress.plan_settlement("找戒指", progress="6/6", kind="positive")
    assert auto.outcome == "strong" and auto.status == "done"
    assert "找戒指" in auto.title and auto.text and auto.epilogue

    explicit = progress.plan_settlement("找戒指", requested="weak", progress="6/6", kind="positive")
    assert explicit.outcome == "weak" and explicit.status == "done"

    failed = progress.plan_settlement("找戒指", requested="miss", progress="6/6")
    assert failed.outcome == "miss" and failed.status == "failed"

    threat = progress.plan_settlement("蚀影", progress="6/6", kind="threat")
    assert threat.outcome == "miss"

    settled_done = progress.plan_settlement(
        "找戒指", status="done", progress="1/6", kind="positive"
    )
    assert settled_done.outcome == "weak"  # 已 done 但无卡：不判 miss
    settled_failed = progress.plan_settlement("找戒指", status="failed")
    assert settled_failed.outcome == "miss"
    # 显式档位不覆盖已结算状态（幂等路径不受 requested 影响）
    assert progress.plan_settlement("找戒指", requested="strong", status="failed").outcome == "miss"


# ---------------------------------------------------------------------------
# encounter：参战者键 / 先攻 / 回绕 / 战报文案
# ---------------------------------------------------------------------------


def test_encounter_participant_keys():
    assert encounter.participant_key("主角", "pc") == "pc.主角"
    assert encounter.participant_key("地精", "npc") == "npc.地精"
    assert encounter.participant_key("pc.主角") == "pc.主角"
    assert encounter.participant_key("地精", "dragon") is None
    assert encounter.participant_key("", "npc") is None
    assert encounter.participant_key("xp.名") is None
    assert encounter.parse_participant("npc.地精") == ("npc", "地精")
    assert encounter.parse_participant("地精") is None


def test_encounter_normalize_participants():
    keys, error = encounter.normalize_participants(
        ["pc.主角", "地精", "pc.主角"], resolve_kind=lambda name: "npc"
    )
    assert error is None and keys == ["pc.主角", "npc.地精"]
    keys, error = encounter.normalize_participants(["主角"], resolve_kind=lambda name: "pc")
    assert keys == ["pc.主角"] and error is None
    assert encounter.normalize_participants([])[0] == []
    assert encounter.normalize_participants([])[1]
    assert encounter.normalize_participants([1, None])[1]
    many = [f"npc.兵{i}" for i in range(20)]
    keys, _ = encounter.normalize_participants(many)
    assert len(keys) == encounter.ENCOUNTER_MAX_PARTICIPANTS  # 截断上限


def test_encounter_initiative_and_advance():
    order = encounter.initiative_order(["pc.主角", "npc.地精", "npc.狼"], rolls=[5, 18, 12])
    assert order == ["npc.地精", "npc.狼", "pc.主角"]
    tied = encounter.initiative_order(["a", "b", "c"], rolls=[7, 7, 7])
    assert tied == ["a", "b", "c"]  # 同点按声明序

    advanced = encounter.advance_turn(3, 2, 1)
    assert (advanced.turn, advanced.round, advanced.wrapped) == (0, 2, True)
    assert (encounter.advance_turn(3, 0, 1).turn, encounter.advance_turn(3, 0, 1).round) == (1, 1)
    single = encounter.advance_turn(1, 0, 1)
    assert single.turn == 0 and single.round == 2
    assert encounter.advance_turn(0, 0, 0).turn == 0  # count<=0 兜底


def test_encounter_order_json_roundtrip():
    order = ["pc.主角", "npc.地精"]
    encoded = encounter.encode_order(order)
    assert encoded.startswith("[") and "地精" in encoded
    assert encounter.decode_order(encoded) == order
    assert encounter.decode_order("not json") == []
    assert encounter.decode_order(None) == []
    assert encounter.decode_order('{"a":1}') == []


def test_encounter_attack_report_no_formula():
    hit = encounter.format_attack_report(
        "pc.洛可", "npc.地精", hit=True, damage=7, target_hp=3, weapon="短剑"
    )
    assert "造成 7 点伤害" in hit and "剩余 HP 3" in hit and "短剑" in hit
    assert "d20" not in hit and "对抗" not in hit and "=" not in hit
    miss = encounter.format_attack_report("pc.洛可", "npc.地精", hit=False)
    assert "落空" in miss and "伤害" not in miss
    plain = encounter.format_attack_report("pc.洛可", "npc.地精", hit=True, damage=0)
    assert "没有造成实质伤害" in plain
    turn_text = encounter.format_turn_report(["pc.主角", "npc.地精"], 1, 2)
    assert "第 2 轮" in turn_text and "地精" in turn_text


def test_encounter_state_change_display_names():
    """判定卡摘要去内部键（docs/57 §3.1）：``pc.主角.hp`` → ``主角 HP``。"""
    assert encounter.state_key_label("pc.主角.hp") == "主角 HP"
    assert encounter.state_key_label("npc.地精.hp") == "地精 HP"
    assert encounter.state_key_label("weird") == "weird"
    assert encounter.state_key_label("item.药水.qty") == "药水 数量"
    assert encounter.format_state_change("pc.主角.hp", "7", -5) == "主角 HP 7（-5）"
    assert encounter.format_state_change("npc.地精.hp", "3", -2) == "地精 HP 3（-2）"
    assert "pc." not in encounter.format_state_change("pc.主角.hp", "7", -5)


def test_encounter_attack_card_wording():
    """战报卡：命中/失手玩家语言，含伤害与剩余 HP，无内部键。"""
    hit = encounter.format_attack_card(
        "pc.洛可", "npc.地精", hit=True, damage=7, target_hp=3, weapon="短剑"
    )
    assert "命中" in hit and "造成 7 点伤害" in hit and "剩余 HP 3" in hit
    assert "pc." not in hit and "npc." not in hit
    miss = encounter.format_attack_card("pc.洛可", "npc.地精", hit=False)
    assert "失手" in miss and "pc." not in miss and "npc." not in miss
    plain = encounter.format_attack_card("pc.洛可", "npc.地精", hit=True, damage=0)
    assert "命中" in plain and "没有造成实质伤害" in plain


# ---------------------------------------------------------------------------
# items：键 / 数量 / 消耗 / 扣减 / 效果归一
# ---------------------------------------------------------------------------


def test_items_key_helpers_and_qty():
    assert items.item_key("治疗药水", "qty") == "item.治疗药水.qty"
    assert items.item_key("治疗药水", "mana") is None
    assert items.item_key("", "qty") is None
    assert items.parse_item_name("item.治疗药水.qty") == "治疗药水"
    assert items.parse_item_name("item.治疗药水.mana") is None
    assert items.parse_item_name("rel.莉亚.attitude") is None

    assert items.parse_qty("3") == 3
    assert items.parse_qty(3) == 3
    assert items.parse_qty(3.0) == 3
    assert items.parse_qty("3.5") is None
    assert items.parse_qty("-1") is None
    assert items.parse_qty(-1) is None
    assert items.parse_qty(True) is None
    assert items.parse_qty(None) is None
    assert items.parse_qty("") is None


def test_items_consumable_and_decrement():
    assert items.parse_consumable(None) is True  # 缺省 = 消耗
    assert items.parse_consumable("true") is True
    assert items.parse_consumable("false") is False
    assert items.parse_consumable(False) is False
    assert items.parse_consumable("0") is False

    assert items.decrement(3) == 2
    assert items.decrement(1) == 0
    assert items.decrement(0) is None
    assert items.decrement(1, amount=2) is None
    assert items.decrement(3, amount=-1) is None


def test_items_effect_normalize_and_hp_delta():
    assert items.normalize_effect("  回复 5  ") == "回复 5"
    assert len(items.normalize_effect("x" * 100)) == items.ITEM_EFFECT_MAX
    assert items.normalize_effect(None) == ""

    assert items.parse_hp_delta("hp+5") == 5
    assert items.parse_hp_delta("HP - 3") == -3
    assert items.parse_hp_delta("回复 5 点生命") == 5
    assert items.parse_hp_delta("恢复1") == 1
    assert items.parse_hp_delta("损失2") == -2
    assert items.parse_hp_delta("提灯") is None
    assert items.parse_hp_delta("hp+0") is None
    assert items.parse_hp_delta("hp+999") is None  # 增量上限
    assert items.parse_hp_delta(None) is None


# ---------------------------------------------------------------------------
# writer 白名单（docs/56 §2）+ 快照 NPC 行
# ---------------------------------------------------------------------------


def test_writer_dimension_rejects_system_only_props():
    known = {"戒指", "药水"}
    # 默认 writer=system：旧行为不变（系统直写全属性）
    assert check_key_whitelist("quest.戒指.progress", known).ok is True
    assert check_key_whitelist("quest.戒指.kind", known).ok is True
    assert check_key_whitelist("item.药水.qty", known).ok is True
    assert check_key_whitelist("encounter.main.turn", {"main"}).ok is True
    # 提取器（writer="llm"）：系统专有属性一律拒绝
    for key, entities in (
        ("quest.戒指.progress", known),
        ("quest.戒指.kind", known),
        ("quest.戒指.stage", known),
        ("item.药水.qty", known),
        ("item.药水.owner", known),
        ("item.药水.consumable", known),
        ("encounter.main.order", {"main"}),
        ("encounter.main.turn", {"main"}),
        ("encounter.main.round", {"main"}),
    ):
        result = check_key_whitelist(key, entities, writer="llm")
        assert result.ok is False and result.reason == "system-only", key
    # 提取器仍可写叙事事实（quest.status / rel.attitude）
    assert check_key_whitelist("quest.戒指.status", known, writer="llm").ok is True
    assert check_key_whitelist("rel.戒指.attitude", known, writer="llm").ok is True

    # 裁决矩阵同口径：llm 拒 system-only；system 放行
    llm_rejected = adjudicate_upsert(
        FactOp(op="create", key="quest.戒指.progress", value="1/6"), [], known
    )
    assert llm_rejected.action == "reject" and llm_rejected.reason == "system-only"
    system_ok = adjudicate_upsert(
        FactOp(op="create", key="quest.戒指.progress", value="1/6", writer="system"), [], known
    )
    assert system_ok.action == "create"
    npc_state = adjudicate_upsert(FactOp(op="create", key="npc.地精.hp", value="7"), [], {"地精"})
    assert npc_state.action == "reject" and npc_state.reason == "llm-state"
    npc_system = adjudicate_upsert(
        FactOp(op="create", key="npc.地精.hp", value="7", writer="system"), [], {"地精"}
    )
    assert npc_system.action == "create"


def test_snapshot_includes_npc_state_line():
    snapshot = build_state_snapshot(
        SnapshotInput(
            facts=[
                SnapshotFact(key="pc.主角.hp", kind="state", value="12"),
                SnapshotFact(key="npc.地精.hp", kind="state", value="7"),
                SnapshotFact(key="npc.地精.status", kind="state", value="受伤"),
                SnapshotFact(key="np.路人.hp", kind="state", value="3"),
            ],
            tasks=[],
            clues=[],
            scene=None,
        )
    )
    assert "PC：HP 12" in snapshot
    assert "地精：HP 7｜状态 受伤" in snapshot
    assert "路人" not in snapshot  # 非法域不进快照


def test_snapshot_includes_item_bag_line():
    """P1-3：item.* 事实进快照（DM 才能看见道具）；NPC 持有物不进玩家行囊。"""
    snapshot = build_state_snapshot(
        SnapshotInput(
            facts=[
                SnapshotFact(key="pc.主角.hp", kind="state", value="12"),
                SnapshotFact(key="pc.主角.inventory", kind="state", value="行囊与短刀"),
                SnapshotFact(key="item.短剑.qty", kind="fact", value="1"),
                SnapshotFact(key="item.短剑.owner", kind="fact", value="pc.主角"),
                SnapshotFact(key="item.治疗药剂.qty", kind="fact", value="2"),
                SnapshotFact(key="item.治疗药剂.effect", kind="fact", value="hp+5"),
                SnapshotFact(key="item.赃物.qty", kind="fact", value="1"),
                SnapshotFact(key="item.赃物.owner", kind="fact", value="npc.商人"),
            ],
            tasks=[],
            clues=[],
            scene="酒馆",
        )
    )
    assert "行囊：短剑×1、治疗药剂×2（hp+5）" in snapshot
    assert "赃物" not in snapshot  # NPC 持有
    assert "行囊与短刀" not in snapshot  # item.* 行优先，不再重复 inventory 字符串


def test_snapshot_bag_falls_back_to_inventory_string():
    """无 item.* 行 → pc.*.inventory 字符串兜底进「行囊」行（不再混在 PC 行）。"""
    snapshot = build_state_snapshot(
        SnapshotInput(
            facts=[
                SnapshotFact(key="pc.主角.hp", kind="state", value="12"),
                SnapshotFact(key="pc.主角.inventory", kind="state", value="行囊与短刀"),
            ],
            tasks=[],
            clues=[],
            scene=None,
        )
    )
    assert "行囊：行囊与短刀" in snapshot
    assert "持有" not in snapshot
    assert "PC：HP 12" in snapshot


def test_snapshot_bag_line_limit():
    """行囊条目按 SNAPSHOT_ITEM_MAX 截断（预算纪律）。"""
    from app.trpg.constants import SNAPSHOT_ITEM_MAX

    facts = [SnapshotFact(key=f"item.杂物{i}.qty", kind="fact", value="1") for i in range(12)]
    snapshot = build_state_snapshot(SnapshotInput(facts=facts, tasks=[], clues=[], scene=None))
    assert "行囊：" in snapshot
    assert snapshot.count("×1") == SNAPSHOT_ITEM_MAX
    assert "杂物11" not in snapshot


# ---------------------------------------------------------------------------
# 场景卡模板：道具种子（docs/57 §3.1）
# ---------------------------------------------------------------------------


def test_card_template_accepts_item_facts_without_owner():
    """模板可预置道具（qty/effect/consumable），但 owner 由系统解析、非法数量丢弃。"""
    from app.trpg.cards import normalize_card

    card = normalize_card(
        {
            "title": "道具种子卡",
            "template": {
                "facts": [
                    {"key": "item.治疗药水.qty", "value": "2"},
                    {"key": "item.治疗药水.effect", "value": "hp+5"},
                    {"key": "item.治疗药水.consumable", "value": "true"},
                    {"key": "item.治疗药水.owner", "value": "pc.主角"},
                    {"key": "item.治疗药水.qty", "value": "abc"},
                    {"key": "item.铁剑.mana", "value": "9"},  # 属性不在白名单 → 丢
                ]
            },
        }
    )
    facts = card["template"]["facts"]
    keys = [f["key"] for f in facts]
    assert keys.count("item.治疗药水.qty") == 1
    assert "item.治疗药水.effect" in keys and "item.治疗药水.consumable" in keys
    assert "item.治疗药水.owner" not in keys
    assert "item.铁剑.mana" not in keys
