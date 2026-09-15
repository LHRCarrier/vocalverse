"""读书域（英文小说阅读）：split / normalize / service / tts_cache / tts_client /
orchestrator / events。

- 写方矩阵：全部 Python（docs/10 §3 增补）；Java 零改动；
- 契约：docs/45 §4（/api/v1/reading/*）；错误码段 45xxx（docs/api/error-codes.md）；
- 听书：provider 链 edge/kitten（docs/45 §5）+ 预合成任务（VoiceStudio jobs 借鉴·自研）。
"""

from __future__ import annotations
