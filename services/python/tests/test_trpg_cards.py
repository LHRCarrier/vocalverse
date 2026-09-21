"""酒馆场景卡 + 用户偏好测试（docs/52 §12）。

覆盖：
- 偏好：默认值 / 更新 / 部分字段 / 非法 lang / 跨设备语义（重新登录同一 user 读回）；
- 回合语言：lang 传参影响 DM system prompt；偏好兜底；语音开关关闭 → 不合成 TTS；
- 用户卡：手建 / 列表（我的在前 + 平台卡）/ 编辑 / 归档 / 越权（他人卡 404）；
- 生成：Fake LLM（非 JSON）→ 47003；脚本化 LLM 合法 JSON → 草稿；关键词长度校验；
- 开局：卡片模板落 campaign（场景/HP/任务/线索/关系）+ 开场卡 + 开场叙述，首回合不重复开卡；
- 管理端：列表/新建/编辑/上架（含 46011 violations）/权限不足 46002/随机生成。
"""

from __future__ import annotations

import json

from app.trpg.cards import normalize_card

from tests.console.helpers import console_headers

CARD_PERMS = ("content:scenario:read", "content:scenario:write", "content:scenario:publish")

GOOD_CARD = {
    "title": "灯塔与幽灵船",
    "summary": "暴风雨夜，灯塔守夜人看见一艘不该存在的船。",
    "language": "zh",
    "tags": ["悬疑", "海"],
    "scene": "灯塔",
    "opening_line": "风把雨点甩在窗上。\n\n老守夜人压低声音：「那艘船，三年前就沉了。」",
    "template": {
        "pc_name": "主角",
        "pc": {"hp": 10, "location": "灯塔顶层", "inventory": "提灯"},
        "facts": [{"key": "rel.老守夜人.attitude", "value": "友善", "modality": "fact"}],
        "tasks": ["查明幽灵船的真相"],
        "clues": [{"title": "航海日志", "content": "缺了最后三页", "scene": "灯塔"}],
    },
}


# ---------------------------------------------------------------------------
# 纯函数：归一/白名单
# ---------------------------------------------------------------------------
def test_normalize_card_tolerates_and_filters():
    card = normalize_card(
        {
            "title": " 测试卡 ",
            "tags": ["a", "b", "a"] + [str(i) for i in range(10)],
            "template": {
                "pc": {"hp": 12, "mana": 99, "location": ""},
                "facts": [
                    {"key": "rel.莉亚.attitude", "value": "敌对"},
                    {"key": "rel.莉亚.mana", "value": "5"},  # 属性不在白名单 → 丢
                    {"key": "bad", "value": "x"},  # 结构非法 → 丢
                    {"key": "scene.current", "value": "酒馆"},  # 场景由 scene 字段承载 → 丢
                    {"key": "pc.主角.hp", "value": "9"},
                ],
                "tasks": ["任务1", "", "任务2"],
                "clues": [{"title": "线索A"}, {"content": "无标题"}],
            },
        }
    )
    assert card["title"] == "测试卡"
    assert card["tags"] == ["a", "b", "0", "1", "2", "3"]  # 去重 + 上限 6
    assert card["template"]["pc"] == {"hp": "12"}
    assert [f["key"] for f in card["template"]["facts"]] == ["rel.莉亚.attitude", "pc.主角.hp"]
    assert card["template"]["tasks"] == ["任务1", "任务2"]
    assert len(card["template"]["clues"]) == 1 and card["template"]["clues"][0]["title"] == "线索A"


def test_normalize_card_requires_title():
    import pytest

    with pytest.raises(ValueError):
        normalize_card({"summary": "没有标题"})


# ---------------------------------------------------------------------------
# 偏好 + 回合语言/语音
# ---------------------------------------------------------------------------
def test_preferences_default_update_and_validation(client, auth_headers):
    resp = client.get("/api/v1/trpg/preferences", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["lang"] == "zh" and data["voice_enabled"] is True and data["persisted"] is False

    resp = client.put(
        "/api/v1/trpg/preferences",
        json={"lang": "en", "voice_enabled": False},
        headers=auth_headers,
    )
    data = resp.json()["data"]
    assert data["lang"] == "en" and data["voice_enabled"] is False and data["persisted"] is True

    # 部分更新：只改语音开关，lang 保持
    data = client.put(
        "/api/v1/trpg/preferences", json={"voice_enabled": True}, headers=auth_headers
    ).json()["data"]
    assert data["lang"] == "en" and data["voice_enabled"] is True

    # 非法 lang → 47001
    bad = client.put("/api/v1/trpg/preferences", json={"lang": "fr"}, headers=auth_headers)
    assert bad.status_code == 422 and bad.json()["code"] == 47001

    # 另一用户不共享（跨用户隔离）
    other = client.get("/api/v1/trpg/preferences", headers={"X-Test-User-Id": "2"}).json()["data"]
    assert other["lang"] == "zh" and other["persisted"] is False


def test_dm_prompt_language_switch():
    from app.trpg.prompts import build_dm_system_prompt

    zh = build_dm_system_prompt("迷雾酒馆", None, "zh")
    en = build_dm_system_prompt("迷雾酒馆", None, "en")
    assert "输出语言：用中文叙述" in zh
    assert "Output language: narrate and role-play in natural English" in en
    assert "中文冒号" in en  # NPC 段协议不随语言变（前端分段依赖）


def test_turn_language_and_voice_switch(client, auth_headers):
    """偏好 voice_enabled=false → 回合不再合成 TTS（无 audio_chunk）；lang=en 生效。"""
    campaign_id = client.post(
        "/api/v1/trpg/campaigns", json={"name": "语言测试"}, headers=auth_headers
    ).json()["data"]["id"]
    client.put(
        "/api/v1/trpg/preferences",
        json={"lang": "en", "voice_enabled": False},
        headers=auth_headers,
    )
    with client.stream(
        "POST",
        f"/api/v1/trpg/campaigns/{campaign_id}/turns",
        data={"text": "I look around"},
        headers=auth_headers,
    ) as resp:
        events = [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert "turn_end" in types
    assert "audio_chunk" not in types  # 语音开关关闭

    # 非法 lang → 47001（流外预检）
    bad = client.post(
        f"/api/v1/trpg/campaigns/{campaign_id}/turns",
        data={"text": "hi", "lang": "fr"},
        headers=auth_headers,
    )
    assert bad.status_code == 422 and bad.json()["code"] == 47001


# ---------------------------------------------------------------------------
# 用户卡 CRUD + 开局
# ---------------------------------------------------------------------------
def test_user_card_crud_and_isolation(client, auth_headers):
    other = {"X-Test-User-Id": "2"}
    created = client.post("/api/v1/trpg/cards", json=GOOD_CARD, headers=auth_headers)
    assert created.status_code == 200
    card = created.json()["data"]
    card_id = card["id"]
    assert card["source"] == "user" and card["status"] == "published"

    # 列表：我的卡在前；他人看不到
    mine = client.get("/api/v1/trpg/cards", headers=auth_headers).json()["data"]["items"]
    assert mine[0]["id"] == card_id
    assert client.get("/api/v1/trpg/cards", headers=other).json()["data"]["items"] == []

    # 越权改/删 → 404
    assert (
        client.put(
            f"/api/v1/trpg/cards/{card_id}", json={**GOOD_CARD, "title": "改"}, headers=other
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/trpg/cards/{card_id}", headers=other).status_code == 404

    updated = client.put(
        f"/api/v1/trpg/cards/{card_id}",
        json={**GOOD_CARD, "title": "灯塔（改）"},
        headers=auth_headers,
    ).json()["data"]
    assert updated["title"] == "灯塔（改）"

    assert client.delete(f"/api/v1/trpg/cards/{card_id}", headers=auth_headers).json()["data"]["ok"]
    assert client.get("/api/v1/trpg/cards", headers=auth_headers).json()["data"]["items"] == []


def test_card_start_applies_template_and_opening(client, auth_headers):
    """开局：模板落 campaign（场景/HP/位置/任务/线索/关系）+ 开场卡 + 开场叙述。"""
    card_id = client.post("/api/v1/trpg/cards", json=GOOD_CARD, headers=auth_headers).json()[
        "data"
    ]["id"]
    started = client.post(f"/api/v1/trpg/cards/{card_id}/start", headers=auth_headers)
    assert started.status_code == 200
    campaign_id = started.json()["data"]["campaign_id"]

    state = client.get(f"/api/v1/trpg/campaigns/{campaign_id}", headers=auth_headers).json()["data"]
    assert state["campaign"]["name"] == GOOD_CARD["title"]
    assert state["scene"] == "灯塔"
    facts = {f["key"]: f["value"] for f in state["facts"]}
    assert facts["pc.主角.hp"] == "10" and facts["pc.主角.location"] == "灯塔顶层"
    assert facts["rel.老守夜人.attitude"] == "友善"
    assert [t["title"] for t in state["tasks"]] == ["查明幽灵船的真相"]
    assert [c["title"] for c in state["clues"]] == ["航海日志"]

    messages = state["messages"]
    assert messages[0]["kind"] == "system" and messages[0]["payload"]["trpg_sys"] == "open"
    assert messages[1]["role"] == "assistant" and "老守夜人" in messages[1]["content"]

    # 首回合不再补开场卡（已由卡片开局落库）
    events = _turn(client, campaign_id, auth_headers, "我上楼看看")
    assert not [e for e in events if e.get("trpg_sys") == "open"]


def _turn(client, campaign_id: int, headers, text: str) -> list[dict]:
    with client.stream(
        "POST",
        f"/api/v1/trpg/campaigns/{campaign_id}/turns",
        data={"text": text},
        headers=headers,
    ) as resp:
        return [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: ")]


def test_card_generate_with_scripted_llm(client, auth_headers, monkeypatch):
    class ScriptedLLM:
        async def chat(self, messages, temperature=0.7, max_tokens=512):
            assert "场景卡" in messages[0]["content"]
            return "```json\n" + json.dumps(GOOD_CARD, ensure_ascii=False) + "\n```"

    monkeypatch.setattr("app.api.routes.trpg.get_llm_client", lambda: ScriptedLLM())
    resp = client.post(
        "/api/v1/trpg/cards/generate", json={"keywords": "海盗 灯塔 幽灵船"}, headers=auth_headers
    )
    assert resp.status_code == 200
    draft = resp.json()["data"]
    assert draft["title"] == GOOD_CARD["title"] and draft["template"]["tasks"]

    # 关键词过长 → 47003（不消耗 LLM）
    bad = client.post(
        "/api/v1/trpg/cards/generate", json={"keywords": "x" * 201}, headers=auth_headers
    )
    assert bad.status_code == 422 and bad.json()["code"] == 47003


def test_card_generate_bad_llm_output(client, auth_headers):
    """Fake LLM 返回非 JSON → 47003（用户可换词重试）。"""
    resp = client.post(
        "/api/v1/trpg/cards/generate", json={"keywords": "沙漠 商队"}, headers=auth_headers
    )
    assert resp.status_code == 422 and resp.json()["code"] == 47003


# ---------------------------------------------------------------------------
# 管理端（Python 控制台）
# ---------------------------------------------------------------------------
def test_console_card_crud_publish_and_violations(client):
    read_headers = console_headers(role="operator", perms=("content:scenario:read",))
    write_headers = console_headers(role="operator", perms=CARD_PERMS)

    # 权限不足：read 只有读
    denied = client.post("/api/v1/console/trpg/cards", json=GOOD_CARD, headers=read_headers)
    assert denied.status_code == 403 and denied.json()["code"] == 46002

    created = client.post("/api/v1/console/trpg/cards", json=GOOD_CARD, headers=write_headers)
    assert created.status_code == 200
    card = created.json()["data"]
    assert card["status"] == "draft" and card["owner_user_id"] is None
    card_id = card["id"]

    listed = client.get("/api/v1/console/trpg/cards", headers=read_headers).json()["data"]
    assert listed["total"] == 1 and listed["items"][0]["id"] == card_id

    # 缺字段的上架 → 46011 + violations
    client.put(
        f"/api/v1/console/trpg/cards/{card_id}",
        json={"title": "缺场景", "opening_line": ""},
        headers=write_headers,
    )
    bad_publish = client.post(
        f"/api/v1/console/trpg/cards/{card_id}/publish",
        json={"status": "published"},
        headers=write_headers,
    )
    assert bad_publish.status_code == 422 and bad_publish.json()["code"] == 46011
    fields = {v["field"] for v in bad_publish.json()["data"]["violations"]}
    assert "scene" in fields and "opening_line" in fields

    # 补全后上架，且用户侧可见
    client.put(f"/api/v1/console/trpg/cards/{card_id}", json=GOOD_CARD, headers=write_headers)
    ok_publish = client.post(
        f"/api/v1/console/trpg/cards/{card_id}/publish",
        json={"status": "published"},
        headers=write_headers,
    )
    assert ok_publish.status_code == 200 and ok_publish.json()["data"]["status"] == "published"

    user_headers = {"X-Test-User-Id": "1"}
    items = client.get("/api/v1/trpg/cards", headers=user_headers).json()["data"]["items"]
    assert any(c["id"] == card_id and c["source"] == "admin" for c in items)

    # 归档后用户侧不可见
    client.post(
        f"/api/v1/console/trpg/cards/{card_id}/publish",
        json={"status": "archived"},
        headers=write_headers,
    )
    items = client.get("/api/v1/trpg/cards", headers=user_headers).json()["data"]["items"]
    assert all(c["id"] != card_id for c in items)


def test_console_card_generate(client, monkeypatch):
    class ScriptedLLM:
        async def chat(self, messages, temperature=0.7, max_tokens=512):
            theme = messages[0]["content"]
            assert "主题：" in theme
            return json.dumps(GOOD_CARD, ensure_ascii=False)

    monkeypatch.setattr("app.console.api.routes.trpg_cards.get_llm_client", lambda: ScriptedLLM())
    headers = console_headers(role="operator", perms=CARD_PERMS)
    resp = client.post("/api/v1/console/trpg/cards/generate", json={}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == GOOD_CARD["title"]
