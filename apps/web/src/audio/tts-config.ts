/**
 * TTS 默认参数单一真源（前端侧）。
 *
 * 背景（2026-09 ASR/TTS 可插拔重构）：默认音色此前在 3 处各写一遍
 * （`useChapterTts.ts` / `api/reading.ts` / `api/practice.ts`），换默认音色要改 N 处且
 * 容易漏。后端已在 `services/python/app/audio/voices.py` 暴露 `DEFAULT_VOICE` 作为
 * 音色目录的单一真源；本文件是它在**前端**的同名镜像。
 *
 * ⚠️ 与后端 `app/audio/voices.py:DEFAULT_VOICE` 保持一致（`tts-config.test.ts` 锁住取值）。
 * 后续若要彻底消灭双份，应由 `/api/v1/reading/voices` 返回默认音色后前端读取 ——
 * 那是一次契约变更，登记在 `docs/audit/ASR-TTS链路审计与重构方案.md` §11 残余项。
 */

/** 默认 TTS 音色（edge 在线档；与后端 voices.py 的 DEFAULT_VOICE 同步） */
export const DEFAULT_TTS_VOICE = 'en-US-JennyNeural'

/** 默认语速（edge-tts 记法；本地引擎忽略此参数，倍速由 playbackRate 承担） */
export const DEFAULT_TTS_RATE = '+0%'
