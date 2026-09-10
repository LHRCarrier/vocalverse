# BUG：录音回放 Content-Type 与内容不符（WebM/Opus 被一律存成 `.mp3`）

- **发现**：2026-09-10 · 唱歌模块容器端到端功能测试（顺带发现：为评估 onset 检测读取历史录音时，
  `librosa`/`soundfile` 报 "Giving up searching valid MPEG header after 65536 bytes of junk"）。
- **修复**：2026-09-10 · 执行人：AI 代签（正式署名待组长确认）。
- **影响面**：`app/practice/orchestrator.py:save_audio_bytes`（保存命名）、
  `app/api/routes/practice.py:get_audio`（回放 Content-Type）；影响**所有用户录音回放**
  （跟读回放、对话声泡点播、跟唱录音回放）。

## 复现

1. 用浏览器/MediaRecorder 录一段（默认容器 `audio/webm;codecs=opus`）并上传；
2. 保存产物为 `data/audio/<sha1>.mp3` —— 但**内容是 WebM**（实测 4 段历史录音魔数均为
   `1A 45 DF A3`（EBML/Matroska））；
3. `GET /api/v1/audio/<sha1>.mp3` 按扩展名给出 `Content-Type: audio/mpeg`，与内容不符；
4. 命令行解码直接失败（mpg123 报 junk 头）；浏览器多靠内容嗅探容忍，但严格客户端/部分
   WebView 可能拒播——且 `Content-Type` 是显式契约字段，不该"靠客户端猜"。

## 根因

两处都把"音频 = mp3"当成了事实：

```python
name = hashlib.sha1(data).hexdigest()[:32] + ".mp3"          # 保存侧：固定扩展名
media_type = _AUDIO_MEDIA_TYPE.get(path.suffix..., "audio/mpeg")  # 回放侧：只信扩展名
```

而上传来自 `MediaRecorder`：Chrome/Android 默认 `audio/webm;codecs=opus`，Safari 为 `audio/mp4`——
`.mp3` 只是历史命名习惯（TTS 产物确实多为 mp3，用户录音不是）。

## 修复（组长拍板：修，含老文件兼容）

1. `app/audio/upload.py` 增**魔数嗅探**（纯函数，可单测）：
   - `sniff_audio_ext(head)` → `webm`（EBML）/`ogg`/`wav`（RIFF…WAVE）/`mp3`（ID3 或 MPEG 帧同步
     `FF Ex`）/`m4a`（ISO BMFF `ftyp`）→ 识别不出返回 None；
   - `resolve_media_type(head, ext)` → **嗅探优先**，不可识别才按扩展名，最后回落 `audio/mpeg`；
   - `AUDIO_MEDIA_TYPE` 收敛为扩展名→MIME 的单一真源（routes 侧复用，删除重复表）。
2. 保存侧 `save_audio_bytes`：扩展名 `= sniff_audio_ext(data) or "mp3"`（未知容器保持旧行为；
   同内容哈希不变 → 仍幂等）。
3. 回放侧 `get_audio`：先读文件头 64B → `resolve_media_type(head, ext)`——**老文件（`.mp3` 名 +
   WebM 内容）无需迁移即可正确回放**（读头失败则回落扩展名，不阻塞回放）。

## 验证

- 单测 `tests/test_audio_container.py`（+4）：六类容器魔数嗅探、未知/空输入、
  **`resolve_media_type(EBML, "mp3") == "audio/webm"`（BUG-5 核心回归）**、
  `save_audio_bytes` 按内容定扩展名 + 未知容器回落 + 幂等；
- 容器端到端（`local/sing_e2e_test.py` 第 12 段，真 ffmpeg 生成 WebM/Opus 上传）：
  - 保存产物 `audio_url` 以 **`.webm`** 结尾 ✔
  - 回放响应 `Content-Type: audio/webm` ✔
  - 历史录音（`.mp3` 名 + EBML 内容）识别 ✔
- 全量门禁：`pytest -q` **423 passed**（415 + 8 新增），ruff/format 全绿，契约快照零 diff。

## 踩坑

1. **命名习惯被当成事实**：`.mp3` 是 TTS 时代的遗留命名，用户录音从来不是 mp3；
   由于回放只按扩展名给 MIME，这个不一致一直"看起来正常"（浏览器嗅探兜底），
   直到本次用命令行工具解码历史录音才暴露。
2. **靠客户端嗅探 = 把契约漏洞藏起来**：显式声明的 `Content-Type` 错但能播，属于"隐性可用"，
   真机/严格环境才翻车——本次修复把它变成可断言的事实（单测 + e2e 双重锁定）。
3. 老文件兼容优先于"重命名迁移"：嗅探在回放缓做（每请求多读 64B）比批量重命名安全——
   重命名会波及 `attempts.audio_url` 等历史引用（那是归属校验的键）。
