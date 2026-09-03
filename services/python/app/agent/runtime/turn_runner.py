"""回合执行器（docs/26 runtime/turn-runner：ai4u turn-runner 的 VocalVerse 版）。

职责：LLM 流式循环 + `[-META-]` 边界拆分（跨 chunk 安全）+ **META 泄漏门**（模型把标记
当正文透传 / 尾部再出现标记时防污染回复）+ 结果归一。上下文组装在 context_builder，
结构化输出的**权威执行**在 meta_executor——本层只负责"拿回文本并拆出 META"。

泄漏防护（对应 ai4u DsmlLeakGate 同族隐患，docs/16 有 M2 先例性讨论）：
- 正文中第一个 `[-META-]` 是协议边界（既有行为）；
- **第二个标记出现在 META 尾部** → 现有实现 rfind 会锚定到第二个标记，导致 reply
  被污染为「正文 + 标记 + 前半段 meta」——本门在此处截断并丢弃尾部，让 meta 解析
  失败降级为纯正文回复（泄漏内容不再进入用户可见文本）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.audio.base import LLMClient
from app.practice.meta import MARKER, MetaResult, extract_meta

logger = logging.getLogger("vocalverse")


@dataclass
class TurnRunResult:
    reply_text: str  # 完整正文（不含 META；泄漏降级时为纯正文）
    meta: MetaResult
    leaked: bool  # 泄漏门触发（第二个标记被截断）
    usage: dict | None = None  # {"model","prompt_tokens","completion_tokens"}（docs/26 §10.3②）


def _partial_marker_len(s: str) -> int:
    """chunk 尾部是否为 MARKER 的前缀（跨 chunk 拆分场景）；返回保留长度。"""
    for k in range(1, len(MARKER)):
        if s.endswith(MARKER[:k]):
            return k
    return 0


class MetaStreamSplitter:
    """流式 chunk → (放行正文 / META 尾部) 的确定性状态机。"""

    def __init__(self) -> None:
        self._full: list[str] = []
        self._meta: str = ""
        self._held = ""
        self.found = False  # 已见过第一个 MARKER
        self.leak_count = 0  # 尾部再次出现 MARKER 次数（截断点）

    def push(self, chunk: str) -> list[str]:
        """喂一个 chunk，返回应放行的正文 delta 列表（语义与旧 orchestrator 循环一致）。"""
        out: list[str] = []
        if self.found:
            idx = chunk.find(MARKER)
            if idx >= 0:
                self.leak_count += 1
                self._meta += chunk[:idx]  # 截断：第二个标记及其后不入尾段
                logger.warning("META leak: duplicated marker in tail (truncated)")
            else:
                self._meta += chunk
            return out
        payload = self._held + chunk
        idx = payload.find(MARKER)
        if idx >= 0:
            # 与旧实现语义一致：meta 尾段**不含**边界标记（extract_meta 侧会补 MARKER 重建）
            pre, post = payload[:idx], payload[idx + len(MARKER) :]
            self.found = True
            self._full.append(pre)
            self._meta = post
            sub = post.find(MARKER)
            if sub >= 0:
                self.leak_count += 1
                self._meta = post[:sub]
                logger.warning("META leak: duplicated marker in tail (truncated)")
            return [pre] if pre.strip() else []
        keep = _partial_marker_len(payload)
        emit = payload[:-keep] if keep else payload
        if emit:
            self._full.append(emit)
        self._held = payload[-keep:] if keep else ""
        return [emit] if emit else []

    def finish(self) -> tuple[str, str, str | None]:
        """收尾：返回 (完整正文, meta 尾部, 未放行的 pending delta)。"""
        pending: str | None = None
        if not self.found and self._held:
            self._full.append(self._held)
            pending = self._held
            self._held = ""
        return "".join(self._full), self._meta, pending


class TurnRunner:
    """单次 LLM 回合执行：async 生成器产出正文 delta；结果经 .result 领取（单次使用）。"""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.result: TurnRunResult | None = None

    async def run(self, messages: list[dict[str, str]]):
        splitter = MetaStreamSplitter()
        usage: dict | None = None
        rich = getattr(self._llm, "stream_rich", None)
        try:
            if rich is not None:
                async for kind, payload in rich(messages):
                    if kind == "usage":
                        usage = payload if isinstance(payload, dict) else None
                        continue
                    for delta in splitter.push(payload):
                        yield delta
            else:
                async for chunk in self._llm.stream(messages):
                    for delta in splitter.push(chunk):
                        yield delta
        except Exception:
            raise  # 调用方决定降级（保持旧 orchestrator 双层结构）
        full, meta_buf, pending = splitter.finish()
        if pending:
            yield pending
        if splitter.found and not splitter.leak_count:
            meta = extract_meta(full + MARKER + meta_buf)
        elif splitter.leak_count:
            # 泄漏：尾部被截断后不拼接标记，解析纯正文 → 降级为无 meta 回复（不污染可见文本）
            meta = extract_meta(full)
        else:
            meta = extract_meta(full)
        reply = meta.reply or full
        self.result = TurnRunResult(
            reply_text=reply, meta=meta, leaked=splitter.leak_count > 0, usage=usage
        )


__all__ = ["MetaStreamSplitter", "TurnRunner", "TurnRunResult"]
