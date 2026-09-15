/**
 * 内容表单纯函数层的单元测试（值解析 / 预检 / payload 映射）。
 *
 * 为什么这一层值得单独测：它是**唯一**同时接触"运营填的字符串"和"服务端线格式"的地方，
 * 三处最贵的缺陷都在这一类转换上——
 * ① 空的可选字段发 `""` 而不是 `null`（服务端会把 `""` 当真实值写库）；
 * ② 必填的 `@NotNull` 字段发 null（吃 42201，且文案读起来像"不能为 null"，运营看不懂）；
 * ③ LRC 乱序提交（服务端按**数组下标**重排 `seq`，乱了会让整首歌的歌词与时间轴错位）。
 * 这三条都不是"UI 问题"，跑界面看不出来，只有把函数单独钉住才可回归。
 *
 * 另外这里顺带覆盖 `*FromForm`（"只发改动字段"的补丁构造器）：它**当前未被提交路径使用**
 * （服务端 `applyXxx` 对每个字段无条件覆盖，发补丁会把未提交字段写成 null，故实际发全量），
 * 但它表达的口径必须在——将来服务端补上"缺省即不变"的语义时，这里是唯一能立刻复用的实现。
 */
import { describe, expect, it } from 'vitest'

import {
  emptyQuestionForm,
  emptySongForm,
  parseDecimal,
  parseWhole,
  trimmedOrNull,
  validateLrcRows,
  validateSongForm,
} from '../contentFormModel'
import {
  fillSongForm,
  questionPatchFromForm,
  songUpsertFromForm,
  toLrcFormRows,
  toLrcUpsert,
  toSongUpsert,
} from '../contentFormPayload'
import { patchOf, sameValue } from '../contentFormTypes'

// ── 标量解析 ──────────────────────────────────────────────────────────────

describe('标量解析（预检与转换共用同一个实现）', () => {
  it('parseWhole：空 → undefined（未填）；非法 → null（填错）；合法 → 数字', () => {
    expect(parseWhole('')).toBeUndefined()
    expect(parseWhole('   ')).toBeUndefined()
    expect(parseWhole('abc')).toBeNull()
    expect(parseWhole('-1')).toBeNull() // 负号不是 \d：LRC 毫秒与 level 都不接受负数
    expect(parseWhole('90')).toBe(90)
  })

  it('parseDecimal：接受本地化逗号，空 → undefined，非法 → null', () => {
    expect(parseDecimal('')).toBeUndefined()
    expect(parseDecimal('120.5')).toBe(120.5)
    expect(parseDecimal('120,5')).toBe(120.5)
    expect(parseDecimal('1.2.3')).toBeNull()
  })

  it('trimmedOrNull：空白 → null（不是空串 —— 空串会被服务端当真实值写库）', () => {
    expect(trimmedOrNull('')).toBeNull()
    expect(trimmedOrNull('   ')).toBeNull()
    expect(trimmedOrNull('  x  ')).toBe('x')
  })

  it('sameValue 忽略首尾空白（只差空格不算改动，避免制造无意义的审计流水）', () => {
    expect(sameValue(' a ', 'a')).toBe(true)
    expect(sameValue('a', 'b')).toBe(false)
    expect(sameValue(null, null)).toBe(true)
    expect(sameValue(0, 0)).toBe(true)
  })

  it('patchOf：未改动 → null（服务端保持原值）；改动 → 新值', () => {
    expect(patchOf('a', 'a')).toBeNull()
    expect(patchOf('b', 'a')).toBe('b')
  })
})

// ── 新建体（全量） ────────────────────────────────────────────────────────

describe('toSongUpsert（表单 → 新建体）', () => {
  const base = () => ({ ...emptySongForm(), title: '  Song  ', level: 2, audioUrl: ' u ' })

  it('必填文本 trim；空的可选字段发 null 而不是空串', () => {
    const body = toSongUpsert(base())
    expect(body.title).toBe('Song')
    expect(body.audioUrl).toBe('u')
    expect(body.artist).toBeNull()
    expect(body.lrcUrl).toBeNull()
    expect(body.coverUrl).toBeNull()
    expect(body.interestTags).toBeNull()
  })

  it('数字字段：空 → null；非法文本 → null（靠本地预检先拦住，不让它变成服务端错误）', () => {
    expect(toSongUpsert({ ...base(), durationS: '', bpm: '' }).durationS).toBeNull()
    expect(toSongUpsert({ ...base(), durationS: 'abc' }).durationS).toBeNull()
    expect(toSongUpsert({ ...base(), durationS: '90', bpm: '120,5' })).toMatchObject({
      durationS: 90,
      bpm: 120.5,
    })
  })

  it('level 是 @NotNull：表单为 null 时回落 1（类型收敛用，正常路径会被预检拦住）', () => {
    expect(toSongUpsert({ ...emptySongForm(), title: 'x', audioUrl: 'u', level: null }).level).toBe(1)
  })
})

// ── 本地预检 ──────────────────────────────────────────────────────────────

describe('validateSongForm（每条都是服务端约束的子集，宁可漏报不许误报）', () => {
  it('标题空白 / 未选等级 → 各自报错', () => {
    const errors = validateSongForm({ ...emptySongForm(), audioUrl: 'u' })
    expect(errors.title).toBeTruthy()
    expect(errors.level).toBeTruthy()
  })

  it('数字字段填了非数字 → "请填数字" 而不是静默通过', () => {
    const errors = validateSongForm({
      ...emptySongForm(),
      title: 't',
      audioUrl: 'u',
      level: 1,
      bpm: 'abc',
    })
    expect(errors.bpm).toBe('请填数字')
  })

  it('超过 @Size 上限 → 提示里带数值上限', () => {
    const errors = validateSongForm({
      ...emptySongForm(),
      title: 'x'.repeat(129),
      audioUrl: 'u',
      level: 1,
    })
    expect(errors.title).toContain('128')
  })

  it('interestTags 是 JSON 数组文本：非法 JSON / 非数组 / 元素非字符串都要拦', () => {
    const withTags = (tags: string) =>
      validateSongForm({ ...emptySongForm(), title: 't', audioUrl: 'u', level: 1, interestTags: tags })
    expect(withTags('not json').interestTags).toBe('不是合法 JSON')
    expect(withTags('{"a":1}').interestTags).toContain('JSON 数组')
    expect(withTags('[1,2]').interestTags).toContain('字符串')
    expect(withTags('["pop"]').interestTags).toBeUndefined()
  })
})

describe('validateLrcRows（三条都对着 Java 写，不是前端自加的规矩）', () => {
  it('零行 → 整表错误（上架要求 lrc 行数 ≥ 1）', () => {
    const { errors, rowErrors } = validateLrcRows([])
    expect(errors.form).toContain('至少 1 行')
    expect(rowErrors).toEqual([])
  })

  it('起始毫秒必填；结束毫秒可留空但填了就必须是非负整数', () => {
    const { errors, rowErrors } = validateLrcRows([
      { offsetMs: '', endOffsetMs: '', lineText: 'hello' },
      { offsetMs: '1000', endOffsetMs: 'abc', lineText: 'world' },
    ])
    expect(rowErrors[0].offsetMs).toBeTruthy()
    expect(rowErrors[0].endOffsetMs).toBeUndefined() // 留空是合法的（= 与起始同值）
    expect(rowErrors[1].endOffsetMs).toBeTruthy()
    expect(errors.form).toContain('未填完整')
  })

  it('歌词行为空 → 该行 lineText 报错（服务端 @NotBlank）', () => {
    const { rowErrors } = validateLrcRows([{ offsetMs: '0', endOffsetMs: '', lineText: '   ' }])
    expect(rowErrors[0].lineText).toBeTruthy()
  })
})

// ── LRC 提交体 ────────────────────────────────────────────────────────────

describe('toLrcUpsert（排序是硬要求：服务端按数组下标写 seq）', () => {
  it('按 offsetMs 升序重排 —— 乱序录入不会让歌词与时间轴错位', () => {
    const body = toLrcUpsert([
      { offsetMs: '3000', endOffsetMs: '', lineText: 'third' },
      { offsetMs: '1000', endOffsetMs: '', lineText: 'first' },
      { offsetMs: '2000', endOffsetMs: '', lineText: 'second' },
    ])
    expect(body.lines.map((l) => l.lineText)).toEqual(['first', 'second', 'third'])
  })

  it('相同 offsetMs 保持用户录入顺序（不依赖 Array.sort 的稳定性）', () => {
    const body = toLrcUpsert([
      { offsetMs: '1000', endOffsetMs: '', lineText: 'a' },
      { offsetMs: '1000', endOffsetMs: '', lineText: 'b' },
    ])
    expect(body.lines.map((l) => l.lineText)).toEqual(['a', 'b'])
  })

  it('结束毫秒留空 → 与起始同值（该列 NOT NULL，发 null 会直接报错）', () => {
    const body = toLrcUpsert([{ offsetMs: '500', endOffsetMs: '', lineText: 'x' }])
    expect(body.lines[0]).toEqual({ offsetMs: 500, endOffsetMs: 500, lineText: 'x' })
  })

  it('toLrcFormRows：已保存的 null 结束时间回落成空串（让运营自己决定填不填）', () => {
    const rows = toLrcFormRows([
      { offsetMs: 0, endOffsetMs: 900, lineText: 'a' },
      { offsetMs: 900, endOffsetMs: null, lineText: 'b' },
    ])
    expect(rows).toEqual([
      { offsetMs: '0', endOffsetMs: '900', lineText: 'a' },
      { offsetMs: '900', endOffsetMs: '', lineText: 'b' },
    ])
  })
})

// ── 回读与补丁 ────────────────────────────────────────────────────────────

describe('fillSongForm（详情 → 表单值）', () => {
  it('null → 空串（输入框不认 null，直接给会显示成字符串 "null"）；枚举缺省回落', () => {
    // 注：`status` **不可能是 null**（`ContentRowBase.status` 非空，对应列也就 `NOT NULL`），
    // 所以这里传真实形状；`source` 可空，用 null 验证回落。
    const form = fillSongForm({
      id: 1,
      title: 'T',
      artist: null,
      level: 3,
      durationS: null,
      bpm: 120.5,
      musicalKey: null,
      audioUrl: 'u',
      lrcUrl: null,
      coverUrl: null,
      interestTags: null,
      source: null,
      status: 'published',
      pitchRefStatus: 'ready',
      updatedAt: '2026-09-10T00:00:00Z',
    })
    expect(form.artist).toBe('')
    expect(form.durationS).toBe('')
    expect(form.bpm).toBe('120.5')
    expect(form.source).toBe('public_domain')
    expect(form.status).toBe('published')
  })
})

describe('songUpsertFromForm / questionPatchFromForm（只发改动字段）', () => {
  it('没改动 → 每个字段都是 null（服务端保持原值，不会重置 status/source）', () => {
    const form = { ...emptySongForm(), title: 'same', level: 1, audioUrl: 'u' }
    const patch = songUpsertFromForm({ ...form }, { ...form })
    expect(Object.values(patch).every((v) => v === null)).toBe(true)
  })

  it('只改标题 → 只有 title 有值，其余仍是 null', () => {
    const before = { ...emptySongForm(), title: 'old', level: 1, audioUrl: 'u' }
    const after = { ...before, title: 'new' }
    const patch = songUpsertFromForm(after, before)
    expect(patch.title).toBe('new')
    expect(patch.audioUrl).toBeNull()
    expect(patch.status).toBeNull()
    expect(patch.source).toBeNull()
  })

  it('original 为 null（新建）→ 返回全量体，不是空补丁', () => {
    const patch = songUpsertFromForm({ ...emptySongForm(), title: 't', level: 1, audioUrl: 'u' }, null)
    expect(patch.title).toBe('t')
    expect(patch.audioUrl).toBe('u')
  })

  it('题目补丁只含题干 / 参考答案 / 状态三个字段（后端 QuestionPatch 不接受身份字段）', () => {
    const before = { ...emptyQuestionForm(), prompt: 'old' }
    const patch = questionPatchFromForm({ ...before, prompt: 'new' }, before)
    expect(Object.keys(patch).sort()).toEqual(['prompt', 'referenceAnswer', 'status'])
    expect(patch.prompt).toBe('new')
  })
})
