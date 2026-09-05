"""LLM 语法判定 + QA 相关度标签单测（阶段 F1：A1 grammar 模块 + B2 qa 标签）。

用 stub LLM（mock ``get_llm_client``）驱动，覆盖：
- judge_grammar 快路径（合法 JSON → {score, errors}）；非 JSON / 空转写 → None（fail-open）；
- judge_qa_answer 快路径（grammar + relevance）；非法 relevance 标签 → None；非 JSON → None。
"""

from __future__ import annotations

import asyncio

import app.placement.grammar as gm


class _StubLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    async def chat(self, messages, temperature: float = 0.0, max_tokens: int = 200) -> str:
        return self._text


def _run(coro):
    return asyncio.run(coro)


def _stub_monkey(monkeypatch, text: str) -> None:
    monkeypatch.setattr(gm, "get_llm_client", lambda: _StubLLM(text))


def test_judge_grammar_happy(monkeypatch):
    """合法 JSON → {score, errors}。"""
    _stub_monkey(monkeypatch, '{"score": 78, "errors": [{"word": "go", "fix": "went"}]}')
    assert _run(gm.judge_grammar("I go yesterday", "I went yesterday")) == {
        "score": 78,
        "errors": [{"word": "go", "fix": "went"}],
    }


def test_judge_grammar_nonjson_fail_open(monkeypatch):
    _stub_monkey(monkeypatch, "no braces here yay")
    assert _run(gm.judge_grammar("hi", "hi")) is None


def test_judge_grammar_empty_transcript():
    assert _run(gm.judge_grammar("", "ref")) is None


def test_judge_grammar_score_clamped(monkeypatch):
    """score 越界钳到 [0,100]（防御）。"""
    _stub_monkey(monkeypatch, '{"score": 120, "errors": []}')
    assert _run(gm.judge_grammar("hi", "hi"))["score"] == 100


def test_judge_qa_answer_happy(monkeypatch):
    _stub_monkey(
        monkeypatch,
        '{"grammar": {"score": 80, "errors": []}, "relevance": "related"}',
    )
    assert _run(gm.judge_qa_answer("I like coffee", "Tell me about yourself")) == {
        "grammar": {"score": 80, "errors": []},
        "relevance": "related",
    }


def test_judge_qa_bad_relevance_becomes_none(monkeypatch):
    """非白名单标签 → relevance=None（relevance 缺失不阻塞）。"""
    _stub_monkey(
        monkeypatch,
        '{"grammar": {"score": 60, "errors": []}, "relevance": "weird"}',
    )
    r = _run(gm.judge_qa_answer("hi", "hi"))
    assert r is not None
    assert r["relevance"] is None


def test_judge_qa_nonjson_fail_open(monkeypatch):
    _stub_monkey(monkeypatch, "oops not json")
    assert _run(gm.judge_qa_answer("hi", "hi")) is None


def test_extract_json_edge():
    """宽松抽取首个 {...}；无闭合 / 非 dict → None。"""
    assert gm._extract_json('text {"a": 1} tail') == {"a": 1}
    assert gm._extract_json('{"a": 1') is None
    assert gm._extract_json("plain") is None
