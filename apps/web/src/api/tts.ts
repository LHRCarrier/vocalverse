/**
 * TTS 合成封装（POST /api/v1/tts → hex 音频 → Blob）。
 *
 * 2026-09-21 从 api/practice.ts 抽出：酒馆（TRPG）与自由对话、场景对话共用，
 * 避免酒馆依赖「练习域」模块命名；api/practice.ts 保留同名 re-export（旧引用零改动）。
 */
import { request } from './client'

import { DEFAULT_TTS_RATE, DEFAULT_TTS_VOICE } from '@/audio/tts-config'

export async function tts(text: string, rate = DEFAULT_TTS_RATE): Promise<Blob> {
  const form = new FormData()
  form.append('text', text)
  form.append('voice', DEFAULT_TTS_VOICE)
  form.append('rate', rate)
  const resp = await request<{
    audio_bytes: string
    length: number
    /** 后端自报的输出容器（2026-09 契约增补）；旧后端无此字段时回落 audio/mpeg */
    media_type?: string
  }>('/api/v1/tts', {
    method: 'POST',
    body: form,
  })
  // ⚠️ 不能一律写死 'audio/mpeg'：本地引擎（KittenTTS/OmniVoice）出的是 24kHz WAV，
  // Blob type 标错会让 <audio> 解码失败（docs/46 B-3 同类问题）。
  return new Blob([hexToBytes(resp.data.audio_bytes)], {
    type: resp.data.media_type || 'audio/mpeg',
  })
}

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2)
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16)
  return out
}
