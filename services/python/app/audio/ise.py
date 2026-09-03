"""讯飞 ISE 发音评测客户端（docs/06 §9.3 基线；并发信号量 2 由编排器控制，无 Key 时走 Fake）。

流式版接口（wss://ise-api.xfyun.cn/v2/open-ise，官方现行文档，2026-09-03 实测）：
- 鉴权：url 查询参数 authorization/date/host（HMAC-SHA256，见 _ws_url）；
- 协议三阶段：参数帧（data.status=0, cmd=ssb）→ 音频帧（cmd=auw, aus=1/2/4,
  status=1/1/2，business **每帧都带**，仅 common 首帧）→ 服务端回 status=2 结果帧
  （data.data 为 base64(JSON)，其 data.ise_res.xml 为 XML 字符串）；
- 结果：句子属性 total_score/pron_score(accuracy_score)/fluency_score/integrity_score
  + 词级 word(content/total_score)/phone(error_type) 细评；
- **音频格式**：16k 单声道 16bit 裸 PCM（auf=audio/L16;rate=16000, aue=raw），单帧
  base64 ≤ 26000 字符；编辑器传入的是原始上传字节（WebM/opus）→ 转码后再发；
- 解析失败抛异常由编排器降级（"未评测"），不伪造分数（docs/10 §4.3 attempts.error 语义）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from app.audio.asr import _ffmpeg_bin
from app.audio.base import ScorerClient, ScoreResult

ISE_URL = "wss://ise-api.xfyun.cn/v2/open-ise"

# 音频帧大小：服务端校验 data.data（base64）≤ 26000 字符 → 原始 PCM 每帧 ≤ ~19KB
_FRAME_BYTES = 19000


def _to_pcm16(audio_bytes: bytes) -> bytes:
    """任意音频容器 → 16k 单声道 s16le 裸 PCM（ISE 唯一接受格式）。"""
    with tempfile.NamedTemporaryFile(suffix=".in", delete=False) as tmp:
        tmp.write(audio_bytes)
        src = tmp.name
    pcm = src + ".pcm"
    try:
        subprocess.run(
            [
                _ffmpeg_bin(),
                "-y",
                "-i",
                src,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                "-f",
                "s16le",
                pcm,
            ],
            check=True,
            capture_output=True,
        )
        return Path(pcm).read_bytes()
    finally:
        Path(src).unlink(missing_ok=True)
        Path(pcm).unlink(missing_ok=True)


def _ise_frames(pcm: bytes, size: int = _FRAME_BYTES) -> list[tuple[int, int, str]]:
    """裸 PCM → [(aus, status, base64帧)]（aus: 首帧1/中间2/末帧4；status: 1/1/2）。

    单帧场景：发 (aus=1,status=1,数据) + 空末帧 (aus=4,status=2) 结束信号。
    """
    chunks = [pcm[i : i + size] for i in range(0, len(pcm), size)] or [b""]
    n = len(chunks)
    if n == 1:
        return [(1, 1, base64.b64encode(chunks[0]).decode()), (4, 2, "")]
    frames: list[tuple[int, int, str]] = []
    for idx, chunk in enumerate(chunks):
        aus = 1 if idx == 0 else (2 if idx < n - 1 else 4)
        status = 1 if idx < n - 1 else 2
        frames.append((aus, status, base64.b64encode(chunk).decode()))
    return frames


class ISEClient(ScorerClient):
    def __init__(self, app_id: str, api_key: str, api_secret: str):
        self._app_id = app_id
        self._api_key = api_key
        self._api_secret = api_secret

    def _ws_url(self) -> str:
        """讯飞通用鉴权（authorization/date/host 查询参数，HMAC-SHA256）。"""
        import hmac

        host = "ise-api.xfyun.cn"
        date = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
        origin = f"host: {host}\ndate: {date}\nGET /v2/open-ise HTTP/1.1"
        signature = base64.b64encode(
            hmac.new(
                self._api_secret.encode("utf-8"), origin.encode("utf-8"), hashlib.sha256
            ).digest()
        ).decode()
        auth_origin = (
            f'api_key="{self._api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(auth_origin.encode("utf-8")).decode()
        return (
            f"wss://{host}/v2/open-ise"
            f"?authorization={quote(authorization)}&date={quote(date)}&host={host}"
        )

    async def score(self, audio_bytes: bytes, reference: str, language: str = "en") -> ScoreResult:
        from websockets.asyncio.client import connect

        pcm = _to_pcm16(audio_bytes)
        if not pcm:
            raise RuntimeError("ISE: 转码后音频为空")
        ent = "cn_vip" if language == "zh" else "en_vip"
        # 文本需带 UTF8 BOM 头（官方文档规定）；英文句子跟读题型（自由题 category=topic 可扩展）
        text = "\ufeff" + reference
        # 参数上传阶段（cmd=ssb）：业务参数 + 多维度分（rst=entirety 且 ise_unite=1）
        business = {
            "sub": "ise",
            "ent": ent,
            "category": "read_sentence",
            "cmd": "ssb",
            "text": text,
            "tte": "utf-8",
            "ttp_skip": True,
            "rst": "entirety",
            "ise_unite": "1",
            "extra_ability": "multi_dimension",
            "aue": "raw",  # 默认是讯飞定制 speex！裸 PCM 必须显式 raw（2026-09-03 实测 40007）
            "auf": "audio/L16;rate=16000",
        }
        async with connect(self._ws_url(), open_timeout=10, close_timeout=5) as ws:
            # 1) 参数帧
            await ws.send(
                json.dumps(
                    {
                        "common": {"app_id": self._app_id},
                        "business": business,
                        "data": {"status": 0, "data": ""},
                    }
                )
            )
            # 2) 音频帧（business 每帧带，cmd 切 auw + aus；仅 common 首帧，2026-09-03 实测）
            for aus, status, chunk_b64 in _ise_frames(pcm):
                await ws.send(
                    json.dumps(
                        {
                            "business": {**business, "cmd": "auw", "aus": aus},
                            "data": {"status": status, "data": chunk_b64},
                        }
                    )
                )
            payload = await _recv_result(ws)
        xml_text = payload.decode("utf-8", "replace")
        parsed = _parse_ise({"code": 0, "data": {"ise_res": {"xml": xml_text}}})
        return ScoreResult(
            overall=parsed["overall"],
            pronunciation=parsed["pron"],
            fluency=parsed["flu"],
            completeness=parsed["completeness"],
            word_level=parsed["words"],
        )


async def _recv_result(ws) -> bytes:
    """循环收帧直到 status=2；结果帧 data.data = base64(XML 结果字符串)（2026-09-03 实测）。"""
    while True:
        frame = json.loads(await ws.recv())
        if frame.get("code") not in (None, 0):
            raise RuntimeError(f"ISE 错误: {frame.get('code')} {frame.get('message')}")
        data = frame.get("data") or {}
        if int(data.get("status", 0)) != 2 or not data.get("data"):
            continue
        return base64.b64decode(data["data"])


def _attr_f(sentence: ET.Element, *names: str) -> float:
    """从多个候选属性名取首个可解析浮点（旧 pron_score / 新 accuracy_score 并存）。"""
    for name in names:
        try:
            v = float(sentence.get(name, 0) or 0)
            if v:
                return v
        except (TypeError, ValueError):
            continue
    return 0.0


def _parse_ise(payload: dict) -> dict:
    """解析结果 payload（xml 为 XML 字符串）；字段缺失时保守降级。

    真实结构（2026-09-03 实测）：sentence 层有 accuracy_score/fluency_score/
    standard_score/total_score；integrity_score 只在 read_chapter 层 → 句子层缺失时回退。
    """
    overall = pron = flu = completeness = 0.0
    words: list[dict] = []
    try:
        ise_res = payload.get("data", {}).get("ise_res", {})
        xml_str = ise_res.get("xml") or ""
        root = ET.fromstring(xml_str if isinstance(xml_str, str) else xml_str.decode())
        first_sentence = next(root.iter("sentence"), None)
        if first_sentence is not None:
            pron = _attr_f(first_sentence, "accuracy_score", "pron_score")
            flu = _attr_f(first_sentence, "fluency_score")
            completeness = _attr_f(first_sentence, "integrity_score", "completeness_score")
            overall = _attr_f(first_sentence, "total_score") or (pron + flu + completeness) / 3
            if not completeness:
                chapter = next(root.iter("read_chapter"), None)
                if chapter is not None:
                    completeness = _attr_f(chapter, "integrity_score")
            for word in list(first_sentence.iter("word")):
                plain = word.get("content", "") or (word.text or "").strip()
                error_type = "other"
                phone = word.find("phone")
                if phone is not None:
                    error_type = phone.get("error_type", "other")
                words.append(
                    {
                        "word": str(plain),
                        "error_type": error_type,
                        "score": _attr_f(word, "total_score"),
                    }
                )
    except (KeyError, TypeError, ValueError, ET.ParseError):
        pass
    return {
        "overall": overall,
        "pron": pron,
        "flu": flu,
        "completeness": completeness,
        "words": words,
    }


__all__ = ["ISEClient", "_parse_ise", "_to_pcm16", "_ise_frames"]
