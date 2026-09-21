"""酒馆（TRPG 跑团）测试：三件套纯函数 + 工具/裁决 + API/SSE 回合（docs/30）。

覆盖（对齐 ai4u 单测 + 冒烟基线）：
- facts：key 解析/白名单/提取解析/upsert 裁决矩阵（llm 写 state 拒、墓碑、用户手改、未知实体注册）；
- dice：解析/判定/文本/增量算术（'3/12' 不可算）；
- snapshot：State/任务/线索/关系四条规则与上限；
- verify：悬空/落差/矛盾/【待记住】补丁；
- API：剧本归属（越权 404）、面板 CRUD、桌骰落表 + 事件日志、SSE 回合（开场卡/文本流/判定卡/TTS）、
  工具调用（roll_dice + set_scene，脚本化 LLM）、墓碑不被提取复活。
"""

from __future__ import annotations

import json

from app.trpg.dice import delta_value, format_dice_text, parse_dice
from app.trpg.facts import (
    FactOp,
    FactRowLike,
    adjudicate_upsert,
    check_key_whitelist,
    make_key,
    parse_fact_ops,
    parse_key,
)
from app.trpg.snapshot import (
    SnapshotClue,
    SnapshotFact,
    SnapshotInput,
    SnapshotTask,
    build_state_snapshot,
)
from app.trpg.verify import (
    build_missing_patch,
    detect_contradiction,
    detect_dangling,
    title_token,
    verify_gap,
)

# ---------------------------------------------------------------------------
# facts 纯函数
# ---------------------------------------------------------------------------


def test_parse_and_make_key():
    assert parse_key("pc.主角.hp") == parse_key("pc.主角.hp")
    parsed = parse_key("rel.莉亚.attitude")
    assert parsed is not None and parsed.domain == "rel" and parsed.entity == "莉亚"
    scene = parse_key("scene.current")
    assert scene is not None and scene.entity is None
    assert parse_key("scene") is None
    assert parse_key("quest.戒指") is None
    assert parse_key("a.b.c.d") is None
    assert parse_key(" pc.主角.hp ") is not None
    assert make_key("quest", "戒指", "status") == "quest.戒指.status"
    assert make_key("scene", None, "current") == "scene.current"
    assert make_key("pc", "主角", "hp") == "pc.主角.hp"


def test_check_key_whitelist():
    ok = check_key_whitelist("pc.主角.hp", {"主角"})
    assert ok.ok is True
    assert check_key_whitelist("pc.主角.mana", {"主角"}).reason == "unknown-property"
    assert check_key_whitelist("hp.主角.hp", {"主角"}).reason == "unknown-domain"
    assert check_key_whitelist("pc.路人.hp", {"主角"}).reason == "unknown-entity"
    assert check_key_whitelist("nonsense", set()).reason == "malformed"
    assert check_key_whitelist(f"pc.{'x' * 61}.hp", set()).reason == "entity-overlong"


def test_parse_fact_ops_tolerant():
    raw = """```json
    [{"op":"create","key":"rel.莉亚.attitude","value":"敌对","modality":"claim","speaker":"莉亚","importance":0.9},
     {"key":"quest.戒指.status","value":"active"},
     {"key":"","value":"x"},
     {"key":"pc.主角.hp","value":"7"}]
    ```"""
    ops = parse_fact_ops(raw)
    assert len(ops) == 3
    assert ops[0].modality == "claim" and ops[0].speaker == "莉亚"
    assert abs((ops[0].importance or 0) - 0.9) < 1e-9
    assert ops[1].op == "create"
    assert ops[2].key == "pc.主角.hp"
    assert parse_fact_ops("not json") == []
    assert parse_fact_ops("") == []


def test_adjudicate_matrix():
    existing = [
        FactRowLike(key="rel.莉亚.attitude", value="友好", id=1, kind="fact"),
        FactRowLike(
            key="rel.守卫.status", value="active", id=2, kind="fact", user_touched_at=object()
        ),
        FactRowLike(
            key="clue.钥匙.found",
            value="found",
            id=3,
            kind="fact",
            user_deleted_at=object(),
        ),
    ]
    known = {"莉亚", "守卫", "主角"}

    created = adjudicate_upsert(
        FactOp(op="create", key="rel.酒保.attitude", value="友善"), existing, known
    )
    assert created.action == "create" and created.register_entity is True

    updated = adjudicate_upsert(
        FactOp(op="create", key="rel.莉亚.attitude", value="信任"), existing, known
    )
    assert updated.action == "update" and updated.existing is not None

    llm_state = adjudicate_upsert(FactOp(op="create", key="pc.主角.hp", value="5"), existing, known)
    assert llm_state.action == "reject" and llm_state.reason == "llm-state"

    untouched = adjudicate_upsert(
        FactOp(op="create", key="rel.守卫.status", value="dead"), existing, known
    )
    assert untouched.action == "reject" and untouched.reason == "user-touched"

    tombstone = adjudicate_upsert(
        FactOp(op="create", key="clue.钥匙.found", value="found"), existing, known
    )
    assert tombstone.action == "reject" and tombstone.reason == "tombstone"

    malformed = adjudicate_upsert(FactOp(op="create", key="bad", value="x"), existing, known)
    assert malformed.action == "reject" and malformed.reason == "malformed"

    system_state = adjudicate_upsert(
        FactOp(op="create", key="pc.主角.hp", value="7", writer="system"), existing, known
    )
    assert system_state.action == "create"


# ---------------------------------------------------------------------------
# dice 纯函数
# ---------------------------------------------------------------------------


def test_parse_dice_and_format():
    result = parse_dice({"dice": "d20", "modifier": 2, "vs": 12})
    assert result is not None
    assert result.total == result.rolls[0] + 2
    assert result.outcome in ("success", "failure")
    assert parse_dice({"dice": "2d6"}) is not None
    assert parse_dice({"dice": "2d6", "effects": [{"key": "pc.主角.hp", "delta": -5}]}) is not None
    # 非法：格式/骰面/骰数/对抗值/调整值/effects 非 State 域
    assert parse_dice({"dice": "d1"}) is None
    assert parse_dice({"dice": "d1001"}) is None
    assert parse_dice({"dice": "11d6"}) is None
    assert parse_dice({"dice": "d20", "vs": 0}) is None
    assert parse_dice({"dice": "d20", "modifier": 51}) is None
    assert (
        parse_dice({"dice": "d20", "effects": [{"key": "rel.莉亚.attitude", "delta": 1}]}) is None
    )
    assert parse_dice({"dice": ""}) is None

    text = format_dice_text(parse_dice({"dice": "2d6", "modifier": -1, "vs": 5}))  # type: ignore[arg-type]
    assert text.startswith("掷出 ") and "对抗 5" in text


def test_delta_value():
    assert delta_value("12", -5) == "7"
    assert delta_value("0", 3) == "3"
    assert delta_value("", -5) == "-5"
    assert delta_value("3/12", -5) is None
    assert delta_value(None, -5) is None
    assert delta_value("abc", 1) is None
    assert delta_value("2.5", -0.5) == "2"


# ---------------------------------------------------------------------------
# snapshot 纯函数
# ---------------------------------------------------------------------------


def test_snapshot_rules():
    snapshot = build_state_snapshot(
        SnapshotInput(
            facts=[
                SnapshotFact(key="pc.主角.hp", kind="state", value="7"),
                SnapshotFact(key="pc.主角.location", kind="state", value="酒馆"),
                SnapshotFact(key="scene.current", kind="state", value="酒馆"),
                SnapshotFact(
                    key="rel.莉亚.attitude",
                    kind="fact",
                    value="敌对",
                    modality="claim",
                    speaker="莉亚",
                    importance=0.9,
                ),
                SnapshotFact(key="rel.酒保.attitude", kind="fact", value="友善", importance=0.1),
            ],
            tasks=[
                SnapshotTask(title="找戒指", status="active"),
                SnapshotTask(title="离城", status="done"),
                SnapshotTask(title="旧账", status="failed"),
            ],
            clues=[
                SnapshotClue(title="钥匙", found=True, recovered=False, scene="酒馆"),
                SnapshotClue(title="符文", found=True, recovered=True, scene="酒馆"),
                SnapshotClue(title="别处的线索", found=True, recovered=False, scene="地城"),
            ],
            scene="酒馆",
        )
    )
    assert "PC：HP 7｜位置 酒馆" in snapshot
    assert "场景：酒馆" in snapshot
    assert "任务：[进行中] 找戒指" in snapshot
    assert "任务统计：已完成 1，失败 1" in snapshot
    assert "线索：钥匙" in snapshot
    assert "符文" not in snapshot and "别处的线索" not in snapshot
    assert "莉亚（敌对（莉亚 声称））" in snapshot
    assert snapshot.index("莉亚") < snapshot.index("酒保")  # importance 降序


def test_snapshot_limits():
    facts = [
        SnapshotFact(key=f"rel.N{i}.attitude", kind="fact", value="友好", importance=1 - i * 0.01)
        for i in range(10)
    ]
    clues = [
        SnapshotClue(title=f"线索{i}", found=True, recovered=False, last_mentioned_at=i)
        for i in range(12)
    ]
    snapshot = build_state_snapshot(SnapshotInput(facts=facts, tasks=[], clues=clues, scene=None))
    assert snapshot.count("（友好") == 6  # SNAPSHOT_FACT_REL_MAX
    assert "线索11" in snapshot and "线索3" not in snapshot  # 上限 8，按时间倒序

    assert build_state_snapshot(SnapshotInput(facts=[], tasks=[], clues=[], scene=None)) == ""


# ---------------------------------------------------------------------------
# verify 纯函数
# ---------------------------------------------------------------------------


def test_verify_dangling_gap_patch():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    old = now - timedelta(days=3)
    tasks = [
        {"id": 1, "title": "找戒指", "status": "active", "last_mentioned_at": old},
        {"id": 2, "title": "刚接的任务", "status": "active", "last_mentioned_at": now},
        {"id": 3, "title": "已完成", "status": "done", "last_mentioned_at": old},
    ]
    clues = [
        {
            "id": 4,
            "title": "地下室钥匙",
            "found": True,
            "recovered": False,
            "last_mentioned_at": old,
        },
        {"id": 5, "title": "已回收", "found": True, "recovered": True, "last_mentioned_at": old},
    ]
    dangling = detect_dangling(tasks, clues, now, 2 * 24 * 3600 * 1000)
    assert {d.title for d in dangling} == {"找戒指", "地下室钥匙"}

    gap, missing = verify_gap(dangling, "你已经接下了「找戒指」的委托")
    assert gap is True
    assert [m.title for m in missing] == ["地下室钥匙"]

    patch = build_missing_patch(missing)
    assert patch is not None and "【待记住】" in patch and "地下室钥匙" in patch
    assert build_missing_patch([]) is None
    assert title_token("找戒指") == "找戒指"
    assert title_token("地下室钥匙") == "地下室钥"


def test_verify_contradiction():
    facts = [{"key": "rel.莉亚.attitude", "value": "敌对"}]
    assert detect_contradiction("莉亚对你很友好，递来一杯酒", facts) is True
    assert detect_contradiction("你在酒馆里坐下", facts) is False
    assert detect_contradiction("", facts) is False


# ---------------------------------------------------------------------------
# API / SSE
# ---------------------------------------------------------------------------


def _create_campaign(client, headers, name="迷雾酒馆") -> int:
    resp = client.post("/api/v1/trpg/campaigns", json={"name": name}, headers=headers)
    assert resp.status_code == 200
    return int(resp.json()["data"]["id"])


def _sse_events(client, campaign_id, headers, *, text=None, audio=None, timeout=30):
    data = {"text": text} if text is not None else None
    files = {"audio": audio} if audio is not None else None
    with client.stream(
        "POST",
        f"/api/v1/trpg/campaigns/{campaign_id}/turns",
        data=data,
        files=files,
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        events = []
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events


def test_campaign_ownership_and_crud(client, auth_headers):
    campaign_id = _create_campaign(client, auth_headers)
    other = {"X-Test-User-Id": "2"}
    assert client.get(f"/api/v1/trpg/campaigns/{campaign_id}", headers=other).status_code == 404
    assert (
        client.post(
            f"/api/v1/trpg/campaigns/{campaign_id}/facts/edit",
            json={"key": "pc.主角.hp", "value": "1"},
            headers=other,
        ).status_code
        == 404
    )
    listed = client.get("/api/v1/trpg/campaigns", headers=auth_headers).json()["data"]
    assert len(listed) == 1 and listed[0]["name"] == "迷雾酒馆"
    assert client.get("/api/v1/trpg/campaigns", headers=other).json()["data"] == []


def test_panel_crud_snapshot_and_dice(client, auth_headers):
    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    assert (
        client.post(f"{base}/scene", json={"scene": "酒馆"}, headers=auth_headers).json()["code"]
        == 0
    )
    for key, value in (("pc.主角.hp", "12"), ("pc.主角.location", "吧台")):
        assert (
            client.post(
                f"{base}/facts/edit", json={"key": key, "value": value}, headers=auth_headers
            ).json()["code"]
            == 0
        )
    assert (
        client.post(f"{base}/tasks", json={"title": "打听怪谈"}, headers=auth_headers).json()[
            "code"
        ]
        == 0
    )
    assert (
        client.post(
            f"{base}/clues",
            json={"title": "暗门", "scene": "酒馆"},
            headers=auth_headers,
        ).json()["code"]
        == 0
    )

    state = client.get(base, headers=auth_headers).json()["data"]
    assert "PC：HP 12｜位置 吧台" in state["snapshot"]
    assert "任务：[进行中] 打听怪谈" in state["snapshot"]
    assert "线索：暗门" in state["snapshot"]
    assert state["scene"] == "酒馆"
    assert any(f["key"] == "quest.打听怪谈.status" for f in state["facts"])

    roll = client.post(
        f"{base}/roll",
        json={"dice": "d20", "vs": 1, "effects": [{"key": "pc.主角.hp", "delta": -5}]},
        headers=auth_headers,
    ).json()
    assert roll["code"] == 0
    assert "pc.主角.hp=7" in roll["data"]["summary"]
    state = client.get(base, headers=auth_headers).json()["data"]
    hp = next(f for f in state["facts"] if f["key"] == "pc.主角.hp")
    assert hp["value"] == "7"
    assert state["events"][0]["summary"].startswith("第 1 回合：")

    # 非法骰子 → 47001（登记码）
    bad = client.post(f"{base}/roll", json={"dice": "d1"}, headers=auth_headers)
    assert bad.status_code == 422 and bad.json()["code"] == 47001


def test_fact_tombstone_and_user_touched(client, auth_headers):
    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    client.post(
        f"{base}/facts/edit",
        json={"key": "rel.莉亚.attitude", "value": "敌对"},
        headers=auth_headers,
    )
    # 用户手改 → LLM 提取拒写（user-touched）
    from app.trpg.facts import FactOp
    from app.trpg.state import list_facts, upsert_facts

    results = upsert_facts(
        campaign_id, [FactOp(op="update", key="rel.莉亚.attitude", value="友好")]
    )
    assert results[0]["action"] == "reject" and results[0]["reason"] == "user-touched"

    assert (
        client.post(
            f"{base}/facts/delete", json={"key": "rel.莉亚.attitude"}, headers=auth_headers
        ).json()["data"]["ok"]
        is True
    )
    assert not any(f["key"] == "rel.莉亚.attitude" for f in list_facts(campaign_id))
    # 墓碑防复活
    results = upsert_facts(
        campaign_id, [FactOp(op="create", key="rel.莉亚.attitude", value="友好")]
    )
    assert results[0]["action"] == "reject" and results[0]["reason"] == "tombstone"
    # 用户恢复路径可清墓碑
    assert (
        client.post(
            f"{base}/facts/restore",
            json={"key": "rel.莉亚.attitude", "value": "中立"},
            headers=auth_headers,
        ).json()["data"]["ok"]
        is True
    )
    restored = [f for f in list_facts(campaign_id) if f["key"] == "rel.莉亚.attitude"]
    assert (
        restored and restored[0]["value"] == "中立" and restored[0]["user_touched_at"] is not None
    )


def test_turn_sse_text_flow(client, auth_headers):
    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    client.post(f"{base}/scene", json={"scene": "酒馆"}, headers=auth_headers)
    client.post(
        f"{base}/facts/edit", json={"key": "pc.主角.hp", "value": "12"}, headers=auth_headers
    )
    events = _sse_events(client, campaign_id, auth_headers, text="我走向吧台")
    types = [e["type"] for e in events]
    assert types[0] == "trpg_ready" and events[0]["is_first"] is True
    assert types[1] == "system" and events[1]["trpg_sys"] == "open"
    assert any(e["type"] == "text_delta" for e in events)
    assert any(e["type"] == "turn_end" for e in events)
    assert any(e["type"] == "audio_chunk" for e in events)

    state = client.get(base, headers=auth_headers).json()["data"]
    roles = [(m["role"], m["kind"]) for m in state["messages"]]
    assert roles[0] == ("assistant", "system")
    assert ("user", "text") in roles and ("assistant", "text") in roles
    # 系统卡不进 DM 历史；快照/摘要按 kind=text 过滤后注入
    from app.trpg.service import _build_dm_context

    messages = _build_dm_context(campaign_id, "迷雾酒馆", "再来一句", None)
    assert all(m["role"] != "assistant" or m["content"] for m in messages)
    assert any(m["role"] == "system" and m["content"].startswith("【当前状态】") for m in messages)
    assert messages[-1] == {"role": "user", "content": "再来一句"}
    # 摘要已增量刷新（P2-45）
    assert "【当前状态】" in (state["narrative_summary"] or "")


def test_turn_requires_input(client, auth_headers):
    campaign_id = _create_campaign(client, auth_headers)
    resp = client.post(f"/api/v1/trpg/campaigns/{campaign_id}/turns", data={}, headers=auth_headers)
    assert resp.status_code == 422 and resp.json()["code"] == 47001


def test_turn_with_tool_calls(client, auth_headers, monkeypatch):
    """脚本化 LLM：第一轮 roll_dice + set_scene，第二轮正文 → HP 落表 + 过场/判定卡。"""
    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    client.post(
        f"{base}/facts/edit", json={"key": "pc.主角.hp", "value": "12"}, headers=auth_headers
    )

    class ScriptedLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def stream_with_tools(self, messages, *, tools=None, tool_choice="auto", **kwargs):
            self.calls += 1
            if self.calls == 1:
                assert tool_choice == "auto" and tools
                yield ("delta", "你挥剑劈向地精——")
                yield (
                    "tool_calls",
                    [
                        {
                            "id": "call_1",
                            "name": "roll_dice",
                            "arguments": json.dumps(
                                {
                                    "dice": "d20",
                                    "modifier": 2,
                                    "vs": 1,
                                    "effects": [{"key": "pc.主角.hp", "delta": -5}],
                                }
                            ),
                        },
                        {
                            "id": "call_2",
                            "name": "set_scene",
                            "arguments": json.dumps({"scene": "地城入口"}),
                        },
                    ],
                )
            else:
                assert tool_choice == "auto"  # 第 2 轮仍可调工具；无工具调用即收尾
                yield ("delta", "剑锋划过，你退入地城入口。")
            yield ("usage", {"model": "scripted", "prompt_tokens": 10, "completion_tokens": 5})

        async def chat(self, messages, temperature=0.7, max_tokens=512):
            return "[]"

    scripted = ScriptedLLM()
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: scripted)

    events = _sse_events(client, campaign_id, auth_headers, text="我攻击地精")
    stages = [e["stage"] for e in events if e["type"] == "status"]
    assert stages == ["rolling", "scene"]
    cards = [e["trpg_sys"] for e in events if e["type"] == "system"]
    assert cards == ["open", "scene", "dice"]
    dice_card = next(e for e in events if e["type"] == "system" and e["trpg_sys"] == "dice")
    assert "pc.主角.hp=7" in dice_card["payload"]["text"]
    text = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert "剑锋划过" in text

    state = client.get(base, headers=auth_headers).json()["data"]
    assert state["scene"] == "地城入口"
    hp = next(f for f in state["facts"] if f["key"] == "pc.主角.hp")
    assert hp["value"] == "7"


def test_turn_audio_asr(client, auth_headers):
    """语音轮：Fake ASR 回显 + 用户录音落盘 + words 元数据链路。"""
    campaign_id = _create_campaign(client, auth_headers)
    audio = b"fake-audio-bytes" + b"\x00" * 2048
    events = _sse_events(client, campaign_id, auth_headers, audio=("voice.webm", audio))
    transcript = next(e for e in events if e["type"] == "user_transcript")
    assert transcript["text"]
    assert transcript["audio_url"].startswith("/api/v1/audio/")
    assert transcript["words"] is None or isinstance(transcript["words"], list)


def test_narrative_refresh_and_clear_messages(client, auth_headers):
    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    client.post(f"{base}/scene", json={"scene": "酒馆"}, headers=auth_headers)
    client.post(f"{base}/tasks", json={"title": "找戒指"}, headers=auth_headers)
    refreshed = client.post(f"{base}/narrative/refresh", headers=auth_headers).json()["data"]
    assert "任务：[进行中] 找戒指" in refreshed["narrative_summary"]

    _sse_events(client, campaign_id, auth_headers, text="继续")
    assert client.delete(f"{base}/messages", headers=auth_headers).json()["data"]["removed"] >= 2
    assert client.get(base, headers=auth_headers).json()["data"]["messages"] == []
    # 事实/任务保留
    assert client.get(base, headers=auth_headers).json()["data"]["scene"] == "酒馆"
