"""orchestrator × 补偿调用接线回归（docs/26 §9.4，PR#26 补测）。

修复前必失败语义：若不接线（orchestrator 不调用 compensate_meta），NoMetaLLM 流的回合
MetaBlock.coach_note 为 None；接线后 = 补偿 JSON 的 "Nice!"。本测试在「接线 commit」
之前运行必红。
"""

from __future__ import annotations

import pytest
from app.audio.stubs import FakeASRClient, FakeScorerClient, FakeTTSClient
from app.db import get_session_factory
from app.models import Scenario, User
from app.models import Session as DbSession
from app.models.base import SessionKinds, SessionStatus
from app.practice import events as ev
from app.practice.orchestrator import _dialog_turn
from app.practice.state import SessionState, get_state_store


class _NoMetaLLM:
    """流式不带 META（触发补偿）；chat 返回合法 META JSON（补偿成功）。"""

    async def stream(self, messages, temperature=0.6, max_tokens=512):
        yield "That'll be three dollars, please."

    async def chat(self, messages, temperature=0.7, max_tokens=512):
        return (
            '{"grammar":{"score":90,"errors":[]},"coach_note":"Nice!",'
            '"corpus_hits":[{"phrase":"I\'d like a coffee, please.","state":"ok"}],'
            '"difficulty_delta":0,"conclude":false}'
        )


@pytest.mark.anyio
async def test_dialog_turn_missing_meta_goes_through_compensation() -> None:
    from app.db import get_session_factory

    db = get_session_factory()()
    try:
        uid = User(username="wiring-u", nickname="w", password_hash="x")
        db.add(uid)
        db.flush()
        sc = Scenario(
            title="wiring-s", scene_type="cafe", difficulty=2,
            system_prompt="You are Bella, a friendly barista.",
            opening_line="Hi there!",
            target_corpus="I'd like a coffee, please.|请给我来杯咖啡",
        )
        db.add(sc)
        db.flush()
        sess = DbSession(
            user_id=int(uid.id), kind=SessionKinds.DIALOG, scenario_id=int(sc.id),
            status=SessionStatus.ACTIVE,
        )
        db.add(sess)
        db.flush()
        sid, sc_id = int(sess.id), int(sc.id)
        db.commit()
    finally:
        db.close()

    state = SessionState(session_id=sid, kind="dialog", state="awaiting_user", next_seq=1)
    await get_state_store().put(state)

    events: list = []
    async for event in _dialog_turn(
        state, "normal", b"fake-audio", None,
        FakeASRClient(), FakeScorerClient(), _NoMetaLLM(), FakeTTSClient(),
    ):
        events.append(event)

    metas = [e for e in events if isinstance(e, ev.MetaBlock)]
    assert metas, "应产出 MetaBlock"
    # 接线证据：补偿调用返回的 coach_note（未接线时此值为 None → 测试必红）
    assert metas[0].coach_note == "Nice!"
    assert any(h.get("phrase") == "I'd like a coffee, please." for h in metas[0].corpus_hits)
