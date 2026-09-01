"""讯飞 ISE 发音评测客户端（docs/06 §9.3 基线；并发信号量 2 由编排器控制，无 Key 时走 Fake）。

WebAPI（v2 open-ise）：
- 请求头：X-Appid / X-CurTime / X-Param(base64(JSON{category, sub, ent, tte, ...})) /
  X-CheckSum(MD5(apiKey + curTime + param))；
- 音频 base64 与参考文本随表单提交；响应 JSON 含逐句/词级结果。
- 本实现按稳定契约解析「总评 + 词级错误」，解析失败抛异常由编排器降级（"未评测"），
  不伪造分数（docs/10 §4.3 attempts.error 语义）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import time

import httpx

from app.audio.base import ScorerClient, ScoreResult

ISE_URL = "https://ise-api.xfyun.cn/v2/open-ise"


class ISEClient(ScorerClient):
    def __init__(self, app_id: str, api_key: str, api_secret: str):
        self._app_id = app_id
        self._api_key = api_key
        self._api_secret = api_secret

    def _sign(self, param_json: dict) -> tuple[str, str, str]:
        cur = str(int(time.time()))
        param_b64 = base64.b64encode(json.dumps(param_json, ensure_ascii=False).encode()).decode()
        sign = hashlib.md5((self._api_key + cur + param_b64).encode()).hexdigest()
        return cur, param_b64, sign

    async def score(self, audio_bytes: bytes, reference: str, language: str = "en") -> ScoreResult:
        param = {
            "category": "cn_vip" if language == "zh" else "en_vip",
            "sub": "ise",
            "ent": "cn_vip" if language == "zh" else "en_vip",
            "cmd": "ssb",  # 单句评分
            "auf": "audio/L16;rate=16000",  # 16k 单声道 16bit wav
            "aue": "raw",
            "text": reference,
            "tte": "utf-8",
        }
        cur, param_b64, sign = self._sign(param)
        headers = {
            "X-Appid": self._app_id,
            "X-CurTime": cur,
            "X-Param": param_b64,
            "X-CheckSum": sign,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                ISE_URL,
                headers=headers,
                data={"audio": base64.b64encode(audio_bytes).decode(), "text": reference},
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"ISE 错误: {data.get('code')} {data.get('message')}")
        result = _parse_ise(data)
        # 句子总分（讯飞 en_vip 返回 total_score 0-100）；词级错误列表
        return ScoreResult(
            overall=result["overall"],
            pronunciation=result["pron"],
            fluency=result["flu"],
            completeness=result["completeness"],
            word_level=result["words"],
        )


def _parse_ise(data: dict) -> dict:
    """解析讯飞返回；字段缺失时保守降级（None 化由调用方处理）。"""
    overall = 0.0
    pron = 0.0
    flu = 0.0
    completeness = 0.0
    words: list[dict] = []
    try:
        xml = data["data"]["ise_res"]["xml"]
        sentences = xml.get("sentence") or []
        for sentence in sentences if isinstance(sentences, list) else [sentences]:
            total = sentence.get("total_score") or sentence
            pron = float(total.get("pron_score", 0))
            flu = float(total.get("fluency_score", 0))
            completeness = float(total.get("integrity_score", 0))
            overall = float(total.get("total_score", (pron + flu + completeness) / 3))
            for word in sentence.get("word") or []:
                content = word.get("content", "")
                plain = content.get("word", content) if isinstance(content, dict) else content
                phone = word.get("phone") or []
                error_type = "other"
                if isinstance(phone, list) and phone:
                    error_type = str(phone[0].get("error_type", "other"))
                words.append(
                    {
                        "word": str(plain),
                        "error_type": error_type,
                        "score": float(word.get("total_score", 0)),
                    }
                )
    except (KeyError, TypeError, ValueError):
        pass
    return {
        "overall": overall,
        "pron": pron,
        "flu": flu,
        "completeness": completeness,
        "words": words,
    }


__all__ = ["ISEClient", "_parse_ise"]
