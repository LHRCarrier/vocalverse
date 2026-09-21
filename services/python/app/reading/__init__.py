"""读书域（英文小说阅读）：split / normalize / service / orchestrator / events。

- 写方矩阵：全部 Python（docs/10 §3 增补）；Java 零改动；
- 契约：docs/45 §4（/api/v1/reading/*）；错误码段 45xxx（docs/api/error-codes.md）；
- 听书：provider 解析与合成缓存已**上收到** ``app/audio``（统一注册表
  ``app.audio.registry`` + 统一缓存 ``app.audio.tts_cache``）——本域不再自带
  ``tts_client`` / ``tts_cache``（2026-09 重构去重，见
  docs/audit/ASR-TTS链路架构调研与重构方案.md §4）。
"""

from __future__ import annotations
