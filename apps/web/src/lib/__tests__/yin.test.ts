/**
 * 自写轻量 YIN（lib/yin.ts）纯函数测试 —— 实时音准线（docs/06 §9.4 注记）。
 *
 * 覆盖：正弦 440/220/880 Hz 检出精度、静音/低信噪比 → null、
 * 采样率 44.1k/48k 一致性、音名/cent 换算（与后端 pitch.py 同口径）。
 */

import { describe, expect, it } from 'vitest'

import { centOf, detectPitch, midiOf, noteNameOf } from '@/lib/yin'

function tone(hz: number, sr = 48000, n = 2048, amp = 0.5): Float32Array {
  const a = new Float32Array(n)
  for (let i = 0; i < n; i += 1) a[i] = amp * Math.sin((2 * Math.PI * hz * i) / sr)
  return a
}

describe('yin · detectPitch', () => {
  it('440Hz @48k 检出 437~443', () => {
    const r = detectPitch(tone(440), 48000)
    expect(r).not.toBeNull()
    expect(r!.confidence).toBeGreaterThan(0)
    expect(r!.f0).toBeGreaterThan(437)
    expect(r!.f0).toBeLessThan(443)
  })

  it('220 / 700 Hz 同准（域 65~800 全覆盖；880 超域上限不测）', () => {
    const low = detectPitch(tone(220), 48000)
    const high = detectPitch(tone(700), 48000)
    expect(low).not.toBeNull()
    expect(high).not.toBeNull()
    expect(Math.abs(low!.f0 - 220)).toBeLessThan(2)
    expect(Math.abs(high!.f0 - 700)).toBeLessThan(6)
  })

  it('44.1k 下 440Hz 仍准（不同设备采样率）', () => {
    const r = detectPitch(tone(440, 44100), 44100)
    expect(r).not.toBeNull()
    expect(Math.abs(r!.f0 - 440)).toBeLessThan(3)
  })

  it('静音 → null', () => {
    expect(detectPitch(new Float32Array(2048), 48000)).toBeNull()
  })

  it('低电平白噪声 → null（阈值鲁棒：不把噪声当音高）', () => {
    // 确定性 LCG 噪声（±0.3 幅度，模拟气声/嘈杂环境）
    const n = new Float32Array(2048)
    let s = 12345
    for (let i = 0; i < n.length; i += 1) {
      s = (s * 1103515245 + 12345) & 0x7fffffff
      n[i] = ((s / 0x7fffffff) * 2 - 1) * 0.3
    }
    expect(detectPitch(n, 48000)).toBeNull()
  })

  it('短窗（<2×65Hz 周期）→ null（防御）', () => {
    expect(detectPitch(new Float32Array(128), 48000)).toBeNull()
  })
})

describe('yin · note 工具（与后端 pitch.py 同口径）', () => {
  it('midi/音名：A4=69 → "A4"', () => {
    expect(midiOf(440)).toBe(69)
    expect(noteNameOf(69)).toBe('A4')
    expect(noteNameOf(60)).toBe('C4')
  })

  it('cent：440 → ±0；466.16 相对 A4（midi 69）→ ≈+100', () => {
    expect(Math.abs(centOf(440, 69))).toBeLessThan(0.01)
    expect(Math.abs(centOf(466.1638, 69) - 100)).toBeLessThan(1)
  })
})
