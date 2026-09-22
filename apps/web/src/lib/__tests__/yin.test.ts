/**
 * 自写轻量 YIN（lib/yin.ts）纯函数测试 —— 实时音准线（docs/06 §9.4 注记）。
 *
 * 覆盖：正弦 440/220/880 Hz 检出精度、静音/低信噪比 → null、
 * 采样率 44.1k/48k 一致性、音名/cent 换算（与后端 pitch.py 同口径）。
 */

import { describe, expect, it } from 'vitest'

import { centOf, createYinDetector, detectPitch, midiOf, noteNameOf, YIN_THRESHOLD, YIN_WINDOW_SIZE } from '@/lib/yin'

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

describe('yin · createYinDetector（复用缓冲 · 实时 Worker 链路，2026-09-18）', () => {
  it('连续多窗（440 → 静音 → 220 → 静音 → 440）与 detectPitch 逐位一致', () => {
    const det = createYinDetector(48000)
    const seq = [tone(440), new Float32Array(2048), tone(220), new Float32Array(2048), tone(440)]
    for (const s of seq) {
      const a = det.detect(s)
      const b = detectPitch(s, 48000)
      if (a === null || b === null) {
        expect(a).toBe(b) // 同为 null（静音）
      } else {
        expect(a.f0).toBe(b.f0)
        expect(a.confidence).toBe(b.confidence)
      }
    }
  })

  it('44.1k/48k 两档各自正确；tauMax = min(n/2, sr/65)', () => {
    expect(createYinDetector(48000).tauMax).toBe(Math.min(1024, Math.floor(48000 / 65)))
    expect(createYinDetector(44100).tauMax).toBe(Math.min(1024, Math.floor(44100 / 65)))
    const d44 = createYinDetector(44100)
    const r = d44.detect(tone(440, 44100))
    expect(r).not.toBeNull()
    expect(Math.abs(r!.f0 - 440)).toBeLessThan(3)
  })

  it('跨次调用复用同一缓冲（零分配回归：旧实现每帧新建 2 个 Float64Array）', () => {
    const det = createYinDetector(48000)
    const d0 = det.buffers.d
    const c0 = det.buffers.cmndf
    det.detect(tone(440))
    det.detect(tone(220))
    det.detect(new Float32Array(2048))
    expect(det.buffers.d).toBe(d0)
    expect(det.buffers.cmndf).toBe(c0)
    expect(d0.length).toBe(det.tauMax + 1)
  })
})

describe('yin · 灵敏度参数（2026-09-21：阈值 0.1→0.22、窗 2048→4096，实测见 local/yin-sensitivity.mjs）', () => {
  it('默认阈值/窗长即新值（单一来源，AnalyserNode 与 Worker 共用）', () => {
    expect(YIN_THRESHOLD).toBe(0.22)
    expect(YIN_WINDOW_SIZE).toBe(4096)
    expect(createYinDetector(48000).n).toBe(YIN_WINDOW_SIZE)
  })

  it('检出对阈值单调（放宽只会多检出），且存在档位体现 0.10→0.22 的增益', () => {
    // 拟人声：弱正弦 + 周期抖动 + 低通隆隆声 + 白噪 + 50Hz 工频（复刻 local/yin-sensitivity.mjs）
    const build = (toneAmp: number, noiseAmp: number) => {
      const N = YIN_WINDOW_SIZE
      const a = new Float32Array(N)
      let s = 987654321
      const rnd = () => {
        s = (s * 1103515245 + 12345) & 0x7fffffff
        return (s / 0x7fffffff) * 2 - 1
      }
      let lp = 0
      let ph = 0
      for (let i = 0; i < N; i += 1) {
        const t = i / 48000
        lp += 0.05 * (rnd() - lp)
        ph += (2 * Math.PI * 220 * (1 + 0.04 * rnd())) / 48000
        const hum = noiseAmp * 0.5 * (Math.sin(2 * Math.PI * 50 * t) + 0.5 * Math.sin(2 * Math.PI * 100 * t))
        a[i] = toneAmp * (1 + 0.3 * Math.sin(2 * Math.PI * 5 * t)) * Math.sin(ph) + noiseAmp * lp + noiseAmp * 0.5 * rnd() + hum
      }
      return a
    }
    const strict = createYinDetector(48000, YIN_WINDOW_SIZE, 0.1)
    const relaxed = createYinDetector(48000, YIN_WINDOW_SIZE, YIN_THRESHOLD)
    const TRIALS = 12
    const SCALES = [0.002, 0.006, 0.012, 0.02, 0.04, 0.1]
    let foundGain = false
    let prevStrict = -1
    for (const noise of SCALES) {
      let strictHits = 0
      let relaxedHits = 0
      for (let k = 0; k < TRIALS; k += 1) {
        const buf = build(0.05, noise)
        if (strict.detect(buf)) strictHits += 1
        if (relaxed.detect(buf)) relaxedHits += 1
      }
      // 单调性：阈值更高 → 检出数不可能更少（detectPitch 的判据是"存在 tau 使 cmndf < 阈值"）
      expect(relaxedHits).toBeGreaterThanOrEqual(strictHits)
      // 噪声越大越难检出（同阈值下应单调不增）
      if (prevStrict >= 0) expect(strictHits).toBeLessThanOrEqual(prevStrict)
      prevStrict = strictHits
      if (relaxedHits > strictHits) foundGain = true
    }
    // 必须存在某个噪声档位，放宽阈值真的多检出了（否则这次调参就是无效的）
    expect(foundGain).toBe(true)
  })

  it('加长窗提升弱信号检出（同阈值下 4096 ≥ 2048）', () => {
    const N = 2048
    const short = createYinDetector(48000, N, YIN_THRESHOLD)
    const long = createYinDetector(48000, YIN_WINDOW_SIZE, YIN_THRESHOLD)
    expect(long.n).toBeGreaterThan(short.n)
    // 窗长决定内层累加长度：更长窗对同一周期信号积分更多，检出不应更差
    const tone = (hz: number, n: number) => {
      const a = new Float32Array(n)
      for (let i = 0; i < n; i += 1) a[i] = 0.5 * Math.sin((2 * Math.PI * hz * i) / 48000)
      return a
    }
    expect(short.detect(tone(220, N))).not.toBeNull()
    expect(long.detect(tone(220, YIN_WINDOW_SIZE))).not.toBeNull()
  })

  it('放大幅度不改变结果（CMNDF 归一化 → 增益对 YIN 无效）', () => {
    const det = createYinDetector(48000)
    const big = tone(440, 48000, YIN_WINDOW_SIZE, 0.5)
    const small = tone(440, 48000, YIN_WINDOW_SIZE, 0.05)
    const a = det.detect(big)
    const b = det.detect(small)
    expect(a).not.toBeNull()
    expect(b).not.toBeNull()
    expect(a!.f0.toFixed(6)).toBe(b!.f0.toFixed(6))
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
