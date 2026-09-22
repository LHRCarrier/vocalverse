"""酒馆（TRPG 跑团）测试：三件套纯函数 + 工具/裁决 + API/SSE 回合（docs/52）。

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
    assert "主角 HP 7（-5）" in roll["data"]["summary"]  # 判定卡用展示名（docs/57 §3.1）
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
    assert "主角 HP 7（-5）" in dice_card["payload"]["text"]
    text = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert "剑锋划过" in text

    state = client.get(base, headers=auth_headers).json()["data"]
    assert state["scene"] == "地城入口"
    hp = next(f for f in state["facts"] if f["key"] == "pc.主角.hp")
    assert hp["value"] == "7"


def test_turn_with_portrait_tool(client, auth_headers, monkeypatch):
    """show_portrait（docs/54 P1 骨架）：已登记实体 → SSE portrait 事件（同回合去重）；
    未登记/已离场实体 → 不发展示信号、不打断回合（工具错误文本回填模型）。"""
    from app.trpg import state as st

    campaign_id = _create_campaign(client, auth_headers)
    st.ensure_entity(campaign_id, "npc", "老陈")

    rounds: list[str] = []

    class ScriptedLLM:
        async def stream_with_tools(self, messages, *, tools=None, tool_choice="auto", **kwargs):
            rounds.append(tool_choice)
            names = [t["function"]["name"] for t in (tools or [])]
            assert "show_portrait" in names
            if len(rounds) == 1:
                yield (
                    "tool_calls",
                    [
                        {
                            "id": "p1",
                            "name": "show_portrait",
                            "arguments": json.dumps({"entity": "老陈", "mood": "戒备"}),
                        },
                        {
                            "id": "p2",
                            "name": "show_portrait",
                            "arguments": json.dumps({"entity": "查无此人"}),
                        },
                        {
                            "id": "p3",
                            "name": "show_portrait",
                            "arguments": json.dumps({"entity": "老陈"}),
                        },
                    ],
                )
            else:
                yield ("delta", "老陈从柜台后抬起头，目光落在你身上。")
            yield ("usage", {"model": "scripted", "prompt_tokens": 1, "completion_tokens": 1})

        async def chat(self, messages, temperature=0.7, max_tokens=512):
            return "[]"

    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: ScriptedLLM())

    events = _sse_events(client, campaign_id, auth_headers, text="我环顾四周")
    portraits = [e for e in events if e["type"] == "portrait"]
    assert len(portraits) == 1  # 同回合重复调用去重；未登记实体不发展示信号
    assert portraits[0]["entity"] == "老陈"
    assert portraits[0]["kind"] == "npc" and portraits[0]["mood"] == "戒备"
    # 实体未挂立绘 → media_id/url 为 null（前端按实体名命中内置素材）
    assert portraits[0].get("media_id") is None and portraits[0].get("url") is None
    assert any(e["type"] == "turn_end" for e in events)
    text = "".join(e["text"] for e in events if e["type"] == "text_delta")
    assert "老陈从柜台后抬起头" in text


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


# ---------------------------------------------------------------------------
# 闭环端到端（docs/56 §7）：进度钟 → 结算 / 人物进出场 / 攻击 / 道具 / 遭遇
# ---------------------------------------------------------------------------


def _tool_call(tool: str, call_id: str, **args) -> dict:
    return {"id": call_id, "name": tool, "arguments": json.dumps(args, ensure_ascii=False)}


class ScriptedRounds:
    """脚本化 LLM：按调用次序消费「轮」脚本（沿用 test_turn_with_tool_calls 模式）。

    ``rounds`` 每项是一轮 stream_with_tools 的事件列表；``tool_texts`` 记录回填给模型的
    工具结果文本（断言错误文本用）。
    """

    def __init__(self, rounds: list[list[tuple]]) -> None:
        self._rounds = list(rounds)
        self.tool_texts: list[str] = []

    async def stream_with_tools(self, messages, *, tools=None, tool_choice="auto", **kwargs):
        for message in messages:
            if message.get("role") == "tool" and message.get("content"):
                self.tool_texts.append(str(message["content"]))
        events = self._rounds.pop(0) if self._rounds else [("delta", "（脚本用尽）")]
        for item in events:
            yield item
        yield ("usage", {"model": "scripted", "prompt_tokens": 1, "completion_tokens": 1})

    async def chat(self, messages, temperature=0.7, max_tokens=512):
        return "[]"


def _facts(client, campaign_id: int, auth_headers) -> dict[str, str]:
    state = client.get(f"/api/v1/trpg/campaigns/{campaign_id}", headers=auth_headers).json()["data"]
    return {f["key"]: f["value"] for f in state["facts"]}


def test_turn_tick_clock_full_and_ending_card(client, auth_headers, monkeypatch):
    """tick_clock → quest 事件 + 事实落表；满格 → complete_quest → ending 事件 + 系统卡持久化。"""
    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    quest = "寻找失落的戒指"
    rounds = [
        [
            ("delta", "你推开暗门——"),
            (
                "tool_calls",
                [_tool_call("tick_clock", "t1", quest=quest, delta=3, reason="破解暗门机关")],
            ),
        ],
        [("delta", "石门在轰鸣中开启。")],
        [
            (
                "tool_calls",
                [_tool_call("tick_clock", "t2", quest=quest, delta=3, reason="祭坛解开封印")],
            )
        ],
        [("delta", "封印在光中崩解。")],
        [("tool_calls", [_tool_call("complete_quest", "t3", quest=quest)])],
        [("delta", "戒指落入你的掌心，这一段故事在这里收束。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    events = _sse_events(client, campaign_id, auth_headers, text="我推开暗门")
    quests = [e for e in events if e["type"] == "quest"]
    assert len(quests) == 1
    assert quests[0]["quest"] == quest and quests[0]["progress"] == "3/6"
    assert quests[0]["segments"] == 6 and quests[0]["kind"] == "positive"
    assert quests[0]["reason"] == "破解暗门机关" and quests[0]["full"] is False

    facts = _facts(client, campaign_id, auth_headers)
    assert facts[f"quest.{quest}.progress"] == "3/6"
    assert facts[f"quest.{quest}.kind"] == "positive"
    state = client.get(base, headers=auth_headers).json()["data"]
    assert any(t["title"] == quest for t in state["tasks"])  # 事实写同步任务行

    events = _sse_events(client, campaign_id, auth_headers, text="我继续破解封印")
    quests = [e for e in events if e["type"] == "quest"]
    assert quests and quests[-1]["progress"] == "6/6" and quests[-1]["full"] is True

    events = _sse_events(client, campaign_id, auth_headers, text="我迎接结局")
    endings = [e for e in events if e["type"] == "ending"]
    assert len(endings) == 1
    ending = endings[0]
    assert ending["quest"] == quest and ending["outcome"] == "strong"  # 6/6 自动判强
    assert ending["title"] and ending["text"] and ending["epilogue"]

    # ending 系统卡落库：刷新（重新 GET 全量状态）后仍在
    state = client.get(base, headers=auth_headers).json()["data"]
    cards = [
        m
        for m in state["messages"]
        if m["kind"] == "system" and m["payload"].get("trpg_sys") == "ending"
    ]
    assert len(cards) == 1
    assert cards[0]["payload"]["quest"] == quest and cards[0]["payload"]["outcome"] == "strong"
    facts = _facts(client, campaign_id, auth_headers)
    assert facts[f"quest.{quest}.status"] == "done"

    from app.trpg import state as st

    assert st.get_campaign_owned(campaign_id, 1).finished_at is not None


def test_turn_character_enter_and_exit(client, auth_headers, monkeypatch):
    """enter_character → character active（不再 pending/arriving）；exit → departed/cleared。"""
    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    rounds = [
        [
            (
                "tool_calls",
                [_tool_call("enter_character", "c1", entity="老陈", note="酒馆老板")],
            )
        ],
        [("delta", "老陈从后厨探出头来。")],
        [
            (
                "tool_calls",
                [_tool_call("exit_character", "c2", entity="老陈", reason="打烊离开")],
            )
        ],
        [("delta", "老陈披上外套，走进雨里。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    events = _sse_events(client, campaign_id, auth_headers, text="我环顾酒馆")
    characters = [e for e in events if e["type"] == "character"]
    assert len(characters) == 1
    assert characters[0]["name"] == "老陈" and characters[0]["status"] == "active"
    assert characters[0]["kind"] == "npc" and characters[0]["note"] == "酒馆老板"

    entities = client.get(base, headers=auth_headers).json()["data"]["entities"]
    chen = next(e for e in entities if e["name"] == "老陈")
    assert chen["pending"] is False and chen["status"] == "active"  # 发现即在场（docs/57 §3.1）

    events = _sse_events(client, campaign_id, auth_headers, text="我目送他离开")
    characters = [e for e in events if e["type"] == "character"]
    assert characters and characters[-1]["status"] == "departed"
    entities = client.get(base, headers=auth_headers).json()["data"]["entities"]
    chen = next(e for e in entities if e["name"] == "老陈")
    assert chen["pending"] is False and chen["status"] == "cleared"  # departed↔cleared


def test_turn_attack_hit_miss_and_hp_writeback(client, auth_headers, monkeypatch):
    """attack：命中写 HP（含 target_hp 建档）；未命中绝不写状态。"""
    from app.trpg import state as st

    campaign_id = _create_campaign(client, auth_headers)
    st.ensure_entity(campaign_id, "pc", "主角")
    st.ensure_entity(campaign_id, "npc", "地精")
    rounds = [
        [
            (
                "tool_calls",
                [
                    _tool_call(
                        "attack",
                        "a1",
                        target="地精",
                        target_hp=10,
                        damage=3,
                        modifier=50,
                        weapon="短剑",
                    ),
                    _tool_call("attack", "a2", target="地精", damage=3, modifier=-50, vs=100),
                ],
            )
        ],
        [("delta", "你一剑劈中地精，追击的一下却落了空。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    events = _sse_events(client, campaign_id, auth_headers, text="我攻击地精")
    attacks = [e for e in events if e["type"] == "encounter" and e["kind"] == "attack"]
    assert len(attacks) == 2
    assert attacks[0]["attacker"] == "pc.主角" and attacks[0]["target"] == "npc.地精"
    assert attacks[0]["hit"] is True and attacks[0]["damage"] == 3
    assert attacks[0]["target_hp"] == 7  # 10 - 3，target_hp 建档后写回
    assert attacks[1]["hit"] is False and attacks[1]["damage"] == 0
    assert attacks[1]["target_hp"] == 7  # 未命中不写状态
    assert _facts(client, campaign_id, auth_headers)["npc.地精.hp"] == "7"

    # 战报卡（docs/57 §3.1）：命中/失手都落 trpg_sys=dice 系统卡，刷新后战斗痕迹仍在
    state = client.get(f"/api/v1/trpg/campaigns/{campaign_id}", headers=auth_headers).json()["data"]
    card_texts = [
        m["payload"]["text"]
        for m in state["messages"]
        if m["kind"] == "system" and m["payload"].get("trpg_sys") == "dice"
    ]
    assert any("命中" in t and "造成 3 点伤害" in t and "剩余 HP 7" in t for t in card_texts)
    assert any("失手" in t for t in card_texts)
    assert all("npc.地精" not in t and "pc.主角" not in t for t in card_texts)  # 不泄露内部键


def test_turn_use_item_decrement_and_exhausted(client, auth_headers, monkeypatch):
    """use_item：consumable 扣减 + hp 效果写回；数量耗尽 → 错误文本、状态不动。"""
    from app.trpg import state as st

    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    st.set_item_facts(
        campaign_id, "治疗药水", qty=2, owner="pc.主角", effect="hp+5", consumable=True
    )
    client.post(
        f"{base}/facts/edit", json={"key": "pc.主角.hp", "value": "3"}, headers=auth_headers
    )
    rounds = [
        [("tool_calls", [_tool_call("use_item", "i1", item="治疗药水")])],
        [("delta", "你把药水一饮而尽。")],
        [("tool_calls", [_tool_call("use_item", "i2", item="治疗药水")])],
        [("delta", "你喝下最后一瓶。")],
        [("tool_calls", [_tool_call("use_item", "i3", item="治疗药水")])],
        [("delta", "瓶子已经空了。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    _sse_events(client, campaign_id, auth_headers, text="我喝一瓶药水")
    facts = _facts(client, campaign_id, auth_headers)
    assert facts["item.治疗药水.qty"] == "1" and facts["pc.主角.hp"] == "8"

    _sse_events(client, campaign_id, auth_headers, text="我再喝一瓶")
    facts = _facts(client, campaign_id, auth_headers)
    assert facts["item.治疗药水.qty"] == "0" and facts["pc.主角.hp"] == "13"

    _sse_events(client, campaign_id, auth_headers, text="我还想再喝")
    facts = _facts(client, campaign_id, auth_headers)
    assert facts["item.治疗药水.qty"] == "0" and facts["pc.主角.hp"] == "13"
    assert any("已经用完" in text for text in llm.tool_texts)  # 校验失败 = 可读错误文本

    unknown = ScriptedRounds(
        [[("tool_calls", [_tool_call("use_item", "i4", item="不存在的圣杯")])], [("delta", "…")]]
    )
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: unknown)
    _sse_events(client, campaign_id, auth_headers, text="我找圣杯")
    assert any("没有" in text and "圣杯" in text for text in unknown.tool_texts)


def test_turn_encounter_start_turn_end(client, auth_headers, monkeypatch):
    """遭遇闭环：start（系统排先攻）→ next_turn（回绕 round+1）→ end（status=done）。"""
    from app.trpg import encounter as encounter_rules
    from app.trpg import state as st

    campaign_id = _create_campaign(client, auth_headers)
    st.ensure_entity(campaign_id, "pc", "主角")
    rounds = [
        [
            (
                "tool_calls",
                [_tool_call("start_encounter", "e1", participants=["pc.主角", "地精"])],
            )
        ],
        [("delta", "地精从阴影里扑出！")],
        [("tool_calls", [_tool_call("next_turn", "e2"), _tool_call("next_turn", "e3")])],
        [("delta", "攻守交换。")],
        [("tool_calls", [_tool_call("end_encounter", "e4", outcome="击退地精")])],
        [("delta", "地精溃逃进夜色。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    events = _sse_events(client, campaign_id, auth_headers, text="我迎战地精")
    starts = [e for e in events if e["type"] == "encounter" and e["kind"] == "start"]
    assert len(starts) == 1
    assert set(starts[0]["order"]) == {"pc.主角", "npc.地精"} and len(starts[0]["order"]) == 2
    assert starts[0]["turn"] == 0 and starts[0]["round"] == 1
    facts = _facts(client, campaign_id, auth_headers)
    assert facts["encounter.main.status"] == "active"
    assert encounter_rules.decode_order(facts["encounter.main.order"]) == starts[0]["order"]
    assert facts["encounter.main.turn"] == "0" and facts["encounter.main.round"] == "1"

    events = _sse_events(client, campaign_id, auth_headers, text="轮到我了")
    turns = [e for e in events if e["type"] == "encounter" and e["kind"] == "turn"]
    assert [(e["turn"], e["round"]) for e in turns] == [(1, 1), (0, 2)]  # 第二位后回绕

    events = _sse_events(client, campaign_id, auth_headers, text="我结束战斗")
    ends = [e for e in events if e["type"] == "encounter" and e["kind"] == "end"]
    assert ends and ends[0]["outcome"] == "击退地精"
    facts = _facts(client, campaign_id, auth_headers)
    assert facts["encounter.main.status"] == "done"


def test_turn_roll_dice_quest_tick_paths(client, auth_headers, monkeypatch):
    """roll_dice 带 quest（docs/57 §3.1）：成功+1/大成功+2、失败推威胁钟、已结算/无 quest 不推。"""
    from app.trpg import state as st

    headers = {"X-Test-User-Id": "7"}  # 独立用户：不吃 user 1 的 llm 限流桶
    campaign_id = _create_campaign(client, headers)
    quest = "找回羊皮卷"
    threat = "蚀影逼近"
    idle = "无事发生"
    settled = "旧日恩怨"
    fresh = "新线索"
    st.set_quest_facts(campaign_id, quest, progress="1/6", kind="positive")
    st.set_quest_facts(campaign_id, threat, progress="1/6", kind="threat")
    st.set_quest_facts(campaign_id, idle, progress="1/6", kind="positive")
    st.set_quest_facts(campaign_id, settled, progress="2/6", kind="positive", status="done")
    rounds = [
        [
            (
                "tool_calls",
                [
                    # 成功且余量 ≥5 → +2
                    _tool_call("roll_dice", "d1", dice="d20", modifier=50, vs=1, quest=quest),
                    # 失败 → 威胁钟 +1
                    _tool_call("roll_dice", "d2", dice="d20", modifier=-50, vs=100, quest=threat),
                    # 失败 → 正向钟不变
                    _tool_call("roll_dice", "d3", dice="d20", modifier=-50, vs=100, quest=idle),
                    # 已结算任务不再推进
                    _tool_call("roll_dice", "d4", dice="d20", modifier=50, vs=1, quest=settled),
                    # 无钟 → 按默认 6 格播种后推进
                    _tool_call("roll_dice", "d5", dice="d20", modifier=50, vs=1, quest=fresh),
                    # 不带 quest → 无 quest 事件（旧行为回归）
                    _tool_call("roll_dice", "d6", dice="d20", modifier=50, vs=1),
                ],
            )
        ],
        [("delta", "浪潮般的攻防告一段落。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    events = _sse_events(client, campaign_id, headers, text="我迎难而上")
    quests = {e["quest"]: e for e in events if e["type"] == "quest"}
    assert set(quests) == {quest, threat, idle, fresh}
    assert quests[quest]["progress"] == "3/6"  # 1 + 2（余量 ≥5）
    assert quests[quest]["reason"] and "大成功" in quests[quest]["reason"]
    assert quests[quest]["kind"] == "positive" and quests[quest]["full"] is False
    assert quests[threat]["progress"] == "2/6" and quests[threat]["kind"] == "threat"
    assert quests[idle]["progress"] == "1/6"  # 正向钟不受挫
    assert quests[fresh]["progress"] == "2/6"  # 无钟按 6 格播种 +2
    assert quests[fresh]["segments"] == 6 and quests[fresh]["kind"] == "positive"
    assert settled not in quests

    facts = _facts(client, campaign_id, headers)
    assert facts[f"quest.{quest}.progress"] == "3/6"
    assert facts[f"quest.{threat}.progress"] == "2/6"
    assert facts[f"quest.{idle}.progress"] == "1/6"
    assert facts[f"quest.{settled}.progress"] == "2/6"
    assert facts[f"quest.{fresh}.progress"] == "2/6"


def test_turn_roll_dice_quest_small_margin_ticks_once(client, auth_headers, monkeypatch):
    """余量 <5 的成功只 +1（骰值固定 → 确定性）。"""
    from app.trpg import dice as dice_rules
    from app.trpg import state as st

    headers = {"X-Test-User-Id": "7"}
    campaign_id = _create_campaign(client, headers)
    quest = "试探虚实"
    st.set_quest_facts(campaign_id, quest, progress="0/6", kind="positive")
    monkeypatch.setattr(dice_rules.random, "randint", lambda low, high: 10)  # d20 → 11
    rounds = [
        [("tool_calls", [_tool_call("roll_dice", "d1", dice="d20", vs=9, quest=quest)])],
        [("delta", "你看清了对方的虚实。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    events = _sse_events(client, campaign_id, headers, text="我试探他")
    quests = [e for e in events if e["type"] == "quest"]
    assert quests and quests[-1]["progress"] == "1/6"  # 11 vs 9 → 余量 2 → +1
    assert quests[-1]["reason"] and "大成功" not in quests[-1]["reason"]
    assert _facts(client, campaign_id, headers)[f"quest.{quest}.progress"] == "1/6"


def test_turn_grant_item_create_increment_owner_and_validation(client, auth_headers, monkeypatch):
    """grant_item：新建/累加、默认持有者、无效 qty 拒绝；不发新 SSE 事件类型。"""
    from app.trpg import state as st

    headers = {"X-Test-User-Id": "7"}
    campaign_id = _create_campaign(client, headers)
    st.ensure_entity(campaign_id, "pc", "主角")
    rounds = [
        [
            (
                "tool_calls",
                [
                    _tool_call("grant_item", "g1", name="短剑", qty=1, effect="hp+3"),
                    _tool_call("grant_item", "g2", name="短剑", qty=2, consumable=False),
                    _tool_call("grant_item", "g3", name="罗盘", qty=1, owner="主角"),
                ],
            )
        ],
        [("delta", "你把战利品收进背包。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    events = _sse_events(client, campaign_id, headers, text="我搜刮尸体")
    assert not any(e["type"] == "item" for e in events)  # 无新事件类型（前端刷事实表）
    facts = _facts(client, campaign_id, headers)
    assert facts["item.短剑.qty"] == "3"  # 1 + 2 累加
    assert facts["item.短剑.owner"] == "pc.主角"  # 默认持首 PC
    assert facts["item.短剑.effect"] == "hp+3"
    assert facts["item.短剑.consumable"] == "false"
    assert facts["item.罗盘.qty"] == "1" and facts["item.罗盘.owner"] == "pc.主角"

    invalid = ScriptedRounds(
        [
            [("tool_calls", [_tool_call("grant_item", "g4", name="毒药", qty=0)])],
            [("delta", "……")],
        ]
    )
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: invalid)
    _sse_events(client, campaign_id, headers, text="我拿毒药")
    assert any("1~99" in text for text in invalid.tool_texts)
    assert "item.毒药.qty" not in _facts(client, campaign_id, headers)


def test_turn_grant_item_owner_fallback_pc_fact_and_none(client, auth_headers, monkeypatch):
    """无 PC 实体时：唯一 pc.* 事实主体成为默认持有者；完全无 PC 则不写 owner。"""
    headers = {"X-Test-User-Id": "7"}
    campaign_id = _create_campaign(client, headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    client.post(
        f"{base}/facts/edit",
        json={"key": "pc.洛可.hp", "value": "10"},
        headers=headers,
    )
    rounds = [
        [("tool_calls", [_tool_call("grant_item", "g1", name="干粮", qty=3)])],
        [("delta", "干粮入袋。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)
    _sse_events(client, campaign_id, headers, text="我拿干粮")
    facts = _facts(client, campaign_id, headers)
    assert facts["item.干粮.qty"] == "3" and facts["item.干粮.owner"] == "pc.洛可"

    # 完全无 PC 信息 → owner 键不落（前端按未知持有者处理）
    bare_id = _create_campaign(client, headers, name="无人酒馆")
    bare_rounds = [
        [("tool_calls", [_tool_call("grant_item", "g2", name="破布", qty=1)])],
        [("delta", "一块破布。")],
    ]
    bare_llm = ScriptedRounds(bare_rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: bare_llm)
    _sse_events(client, bare_id, headers, text="我捡起破布")
    bare_facts = _facts(client, bare_id, headers)
    assert bare_facts["item.破布.qty"] == "1" and "item.破布.owner" not in bare_facts


def test_lazy_registered_entity_is_active(client, auth_headers):
    """提取器懒注册实体不再 pending（docs/57 §3.1）：发现即 active。"""
    from app.trpg.facts import FactOp
    from app.trpg.state import upsert_facts

    campaign_id = _create_campaign(client, auth_headers)
    results = upsert_facts(
        campaign_id, [FactOp(op="create", key="rel.莉亚.attitude", value="友好")]
    )
    assert results[0]["action"] == "create"
    state = client.get(f"/api/v1/trpg/campaigns/{campaign_id}", headers=auth_headers).json()["data"]
    lia = next(e for e in state["entities"] if e["name"] == "莉亚")
    assert lia["pending"] is False and lia["status"] == "active"


def test_settle_endpoint_owner_idempotent_and_finished_state(client, auth_headers):
    """确定性结算端点：owner 校验 / 幂等（同 payload、一张结局卡）/ finished 状态外露。"""
    from app.trpg import state as st

    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    quest = "寻找失落的戒指"
    client.post(f"{base}/tasks", json={"title": quest}, headers=auth_headers)
    st.set_quest_facts(campaign_id, quest, progress="6/6", kind="positive")

    other = {"X-Test-User-Id": "2"}
    denied = client.post(f"{base}/quests/settle", json={"quest": quest}, headers=other)
    assert denied.status_code == 404

    invalid = client.post(
        f"{base}/quests/settle", json={"quest": quest, "outcome": "epic"}, headers=auth_headers
    )
    assert invalid.status_code == 422 and invalid.json()["code"] == 47001
    blank = client.post(f"{base}/quests/settle", json={"quest": "  "}, headers=auth_headers)
    assert blank.status_code == 422 and blank.json()["code"] == 47001

    first = client.post(
        f"{base}/quests/settle", json={"quest": quest}, headers=auth_headers
    ).json()["data"]
    assert first["quest"] == quest and first["outcome"] == "strong"
    assert first["title"] and first["text"] and first["epilogue"] and first["finished"] is True

    state = client.get(base, headers=auth_headers).json()["data"]
    assert state["campaign"]["finished"] is True
    assert state["campaign"]["finished_at"]
    endings = [
        m
        for m in state["messages"]
        if m["kind"] == "system" and m["payload"].get("trpg_sys") == "ending"
    ]
    assert len(endings) == 1 and endings[0]["payload"]["quest"] == quest
    assert _facts(client, campaign_id, auth_headers)[f"quest.{quest}.status"] == "done"

    second = client.post(
        f"{base}/quests/settle", json={"quest": quest}, headers=auth_headers
    ).json()["data"]
    for key in ("quest", "outcome", "title", "text", "epilogue"):
        assert second[key] == first[key]
    assert second["finished"] is True
    state = client.get(base, headers=auth_headers).json()["data"]
    endings = [
        m
        for m in state["messages"]
        if m["kind"] == "system" and m["payload"].get("trpg_sys") == "ending"
    ]
    assert len(endings) == 1  # 幂等：不落第二张结局卡


def test_settle_endpoint_explicit_outcome_syncs_task_row(client, auth_headers):
    """显式 outcome=miss → failed；任务行同步；结算后 finished 可在状态里读回。"""
    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    quest = "未竟之约"
    client.post(f"{base}/tasks", json={"title": quest}, headers=auth_headers)

    data = client.post(
        f"{base}/quests/settle", json={"quest": quest, "outcome": "miss"}, headers=auth_headers
    ).json()["data"]
    assert data["outcome"] == "miss" and data["finished"] is True
    assert _facts(client, campaign_id, auth_headers)[f"quest.{quest}.status"] == "failed"
    state = client.get(base, headers=auth_headers).json()["data"]
    task = next(t for t in state["tasks"] if t["title"] == quest)
    assert task["status"] == "failed"
    assert state["campaign"]["finished_at"]


def test_settle_endpoint_synthesizes_card_for_extractor_done_quest(client, auth_headers):
    """已 done 但无结局卡（如提取器置位）→ 结算端点补渲染并落一张卡（重复调用仍幂等）。"""
    from app.trpg import state as st

    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    quest = "被提取器完结的任务"
    st.set_quest_facts(campaign_id, quest, progress="4/6", kind="positive", status="done")

    first = client.post(
        f"{base}/quests/settle", json={"quest": quest}, headers=auth_headers
    ).json()["data"]
    assert first["finished"] is True and first["title"] and first["text"]
    state = client.get(base, headers=auth_headers).json()["data"]
    endings = [
        m
        for m in state["messages"]
        if m["kind"] == "system" and m["payload"].get("trpg_sys") == "ending"
    ]
    assert len(endings) == 1

    second = client.post(
        f"{base}/quests/settle", json={"quest": quest}, headers=auth_headers
    ).json()["data"]
    assert second["title"] == first["title"] and second["outcome"] == first["outcome"]
    state = client.get(base, headers=auth_headers).json()["data"]
    endings = [
        m
        for m in state["messages"]
        if m["kind"] == "system" and m["payload"].get("trpg_sys") == "ending"
    ]
    assert len(endings) == 1  # 补卡后幂等：不再落第二张


def test_complete_quest_idempotent_no_second_ending(client, auth_headers, monkeypatch):
    """complete_quest 二次结算：幂等文本「已结算」、不新发 ending 事件/系统卡。"""
    headers = {"X-Test-User-Id": "7"}
    campaign_id = _create_campaign(client, headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    quest = "止息怪谈"
    rounds = [
        [("tool_calls", [_tool_call("complete_quest", "q1", quest=quest, outcome="weak")])],
        [("delta", "风停在屋檐上。")],
        [("tool_calls", [_tool_call("complete_quest", "q2", quest=quest)])],
        [("delta", "你合上了笔记本。")],
    ]
    llm = ScriptedRounds(rounds)
    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: llm)

    first_events = _sse_events(client, campaign_id, headers, text="我收尾这一段")
    assert any(e["type"] == "ending" for e in first_events)
    second_events = _sse_events(client, campaign_id, headers, text="再结算一次")
    assert not any(e["type"] == "ending" for e in second_events)  # 防重：无第二张结局卡/事件
    assert any("已结算" in text for text in llm.tool_texts)

    state = client.get(base, headers=headers).json()["data"]
    endings = [
        m
        for m in state["messages"]
        if m["kind"] == "system" and m["payload"].get("trpg_sys") == "ending"
    ]
    assert len(endings) == 1 and endings[0]["payload"]["outcome"] == "weak"
    assert _facts(client, campaign_id, headers)[f"quest.{quest}.status"] == "done"


# ---------------------------------------------------------------------------
# 实体立绘（docs/56 §4）
# ---------------------------------------------------------------------------


def _upload_png(client, headers) -> str:
    import io

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 4096
    resp = client.post(
        "/api/v1/media",
        headers=headers,
        files={"file": ("a.png", io.BytesIO(png), "application/octet-stream")},
        data={"kind": "image"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def test_entity_portrait_attach_expose_and_show_portrait(client, auth_headers, monkeypatch):
    """挂载（owner+媒体归属校验）→ 实体列表带 portrait → show_portrait 带 media_id/url → 卸下。"""
    from app.trpg import state as st

    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    entity_id = st.ensure_entity(campaign_id, "npc", "老陈")

    # 未上传媒体 → 40403（不泄露存在性）
    missing = client.post(
        f"{base}/entities/{entity_id}/portrait",
        json={"media_id": "deadbeefdeadbeef"},
        headers=auth_headers,
    )
    assert missing.status_code == 404 and missing.json()["code"] == 40403

    media_id = _upload_png(client, auth_headers)
    attached = client.post(
        f"{base}/entities/{entity_id}/portrait", json={"media_id": media_id}, headers=auth_headers
    )
    data = attached.json()["data"]
    assert data["ok"] is True and data["url"] == f"/api/v1/media/{media_id}"

    entities = client.get(base, headers=auth_headers).json()["data"]["entities"]
    chen = next(e for e in entities if e["name"] == "老陈")
    assert chen["id"] == entity_id  # 前端持 id 调立绘挂载端点
    assert chen["portrait_media_id"] == media_id
    assert chen["portrait"]["url"] == f"/api/v1/media/{media_id}"

    # show_portrait：事件回带 media_id + url
    monkeypatch.setattr(
        "app.api.routes.trpg.get_llm_client",
        lambda: ScriptedRounds(
            [
                [("tool_calls", [_tool_call("show_portrait", "p1", entity="老陈", mood="戒备")])],
                [("delta", "老陈从柜台后抬起头。")],
            ]
        ),
    )
    events = _sse_events(client, campaign_id, auth_headers, text="我看向柜台")
    portraits = [e for e in events if e["type"] == "portrait"]
    assert len(portraits) == 1
    assert portraits[0]["media_id"] == media_id
    assert portraits[0]["url"] == f"/api/v1/media/{media_id}"

    # 卸下 → 实体列表 portrait 清空
    assert (
        client.delete(f"{base}/entities/{entity_id}/portrait", headers=auth_headers).json()["data"][
            "ok"
        ]
        is True
    )
    entities = client.get(base, headers=auth_headers).json()["data"]["entities"]
    chen = next(e for e in entities if e["name"] == "老陈")
    assert chen["portrait_media_id"] is None and chen["portrait"] is None


def test_entity_portrait_ownership_guards(client, auth_headers):
    """媒体非本人 → 40403；campaign/实体越权或不存在 → 404。"""
    from app.trpg import state as st

    campaign_id = _create_campaign(client, auth_headers)
    base = f"/api/v1/trpg/campaigns/{campaign_id}"
    entity_id = st.ensure_entity(campaign_id, "npc", "老陈")
    mine = _upload_png(client, auth_headers)

    other = {"X-Test-User-Id": "2"}
    other_media = _upload_png(client, other)
    not_mine = client.post(
        f"{base}/entities/{entity_id}/portrait",
        json={"media_id": other_media},
        headers=auth_headers,
    )
    assert not_mine.status_code == 404 and not_mine.json()["code"] == 40403

    cross_campaign = client.post(
        f"{base}/entities/{entity_id}/portrait", json={"media_id": mine}, headers=other
    )
    assert cross_campaign.status_code == 404

    ghost = client.post(
        f"{base}/entities/99999/portrait", json={"media_id": mine}, headers=auth_headers
    )
    assert ghost.status_code == 404 and ghost.json()["code"] == 40401
