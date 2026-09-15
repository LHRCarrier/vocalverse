# BUG：流利度时间戳特征 · 词级时间戳恒为空（words=0 → wpm/停顿全零）

- **发现**：2026-09-04 · 联调测试页（`/preview/fluency`）上传 `ref-2.wav`（6.12s SAPI 合成音）
  分析 → 转写文本正确（"Could I have a cappuccino? Please. I would really appreciate it."），
  但 **FLUENCY FEATURES 全零**：0 WORDS / wpm 0 / 停顿 0 次。
- **执行人**：LHRCarrier（AI 代工整理）

## 复现

1. `POST /api/v1/fluency-preview/analyze`（audio=ref-2.wav）→ `data.words=[]`、`features` 全零；
2. 排除法矩阵（同文件/同参数）：
   - 直调 `WhisperModel('small',cpu,int8).transcribe(..., word_timestamps=True)` × flac → **17 词** ✓
   - 直调同 model × ref-2.wav（22.05k 未转码）→ **11 词** ✓
   - `FasterWhisperClient.transcribe_sync`（走 ffmpeg 转码 + 封装层）× flac → **0 词** ✗
   - 矩阵锁定：**不是文件、不是转码、不是模型，是封装层**。

## 根因

`model.transcribe()` 返回的是**生成器**（`(generator, info)`），不是列表。`transcribe_sync` 里：

```python
segments, info = model.transcribe(...)          # 生成器
text = "".join(s.text for s in segments).strip() # ① 拉平文本——生成器被消费殆尽
words = []
for s in segments:                               # ② 再迭代——恒空！
```

第二次迭代同一个已耗尽生成器 → `words` 恒 `[]`。**旧代码的 `ASRResult.segments` 同样恒空**
（`segments` 字段也是第二遍迭代）——因无消费方、无测试断言，从 M2 起一直静默存在。
2026-09-04 给 `segments` 加词级时间戳消费方（② 特征）后立刻暴露。

**踩坑提示**：faster-whisper 的 `transcribe()` 返回生成器，**任何要迭代两次的用法必须先
`list()` 物化一次**；直调测试恰好用了 `list()` 所以「直调正常、封装异常」非常迷惑人。

## 修复

`transcribe_sync` 在解包后立即 `segments = list(segments)`（物化一次，后续文本/段/词
三处迭代共用同一份列表），并加注释说明生成器契约。`app/audio/asr.py`。

## 验证

1. **回归测试** `tests/test_asr_words.py`（假模型返回生成器 + 断言 `word_timestamps` 透传）：
   - 删除 `list()` 物化行 → **必红**（words==[]，实测 1 failed）；
   - 恢复修复行 → **绿**（实测通过）；全量 **149 passed** + ruff 全绿；
2. **真链路**（重启 :8000 后 `POST /api/v1/fluency-preview/analyze` × ref-2.wav）：
   - 修复前：words=0 / wpm=0 / pause=0；
   - 修复后：**words=11 / duration=6.12 / wpm=124.06 / pause=2 / max_pause=0.96s /
     ISE overall=84.94 / flu=89.66 / pron=82.01** —— 特征与评分双双真出。

## 影响面

- 仅影响 2026-09-04 新加的「词级时间戳→流利度特征」链路（`ASRResult.words/duration`）；
- 顺带修复 `ASRResult.segments` 恒空的**历史缺陷**（/asr 响应 segments 字段此前也一直是空）；
- 对外契约无变化（字段早已定义，只是内容从空变有值）；无前端改动。
