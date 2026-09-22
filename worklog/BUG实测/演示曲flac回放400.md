# BUG：演示曲 flac「听参考旋律」全部 400 `bad audio name`（回放白名单缺 flac）

- **发现**：2026-09-22 · 演示联调（用户浏览器网络面板：`demo_honkai-moon-halo.flac` 等 7 首连续 400，mp3 那首正常）。
- **修复**：2026-09-22 · 执行人：LHRCarrier（AI 代工）。
- **影响面**：`GET /api/v1/audio/{name}`（`app/api/routes/practice.py`）——本地演示曲库 8 首里 **7 首 flac** 的「听参考旋律」全不可用（曲库展示/封面/列表不受影响）；评分链路不受影响（读盘不经 HTTP）。
- **严重级**：P1（演示阻断：用户答辩曲目一半以上点「原唱」直接弹「参考旋律播放失败，请重试」）。

## 复现

1. 本地演示曲库（`local/_import_demo_songs.py`）8 首，其中 5 首 flac（Moon Halo / NIGHT DANCER / Cyberangel / Myra / アイネクライネ / The Other Side of Paradise / 经过，共 7 首）+ 1 首 mp3（○○は受信机なんです）；
2. `/m/sing` → 打开任一 flac 曲 → 点「原唱」（`useReferenceAudio.toggle` → `loadAudioBlob('/api/v1/audio/demo_*.flac')`）；
3. 实际：**400 `{"code":40001,"message":"bad audio name"}`**；mp3 那首 200 正常。
4. 接口级复现（修复前）：`curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/audio/demo_honkai-moon-halo.flac` → `400`。

## 根因

两层都不认 flac，且第一层在路由入口就把请求挡掉：

```python
# app/api/routes/practice.py:47（修复前）
_SAFE_NAME = re.compile(r"^[0-9a-zA-Z_-]{1,64}\.(mp3|wav|m4a|ogg|webm)$")   # ← 无 flac → 400
# app/audio/upload.py AUDIO_MEDIA_TYPE 同样无 flac → 即使放行也会回落 audio/mpeg
```

- 白名单的历史口径是「用户录音（webm/mp3…）+ 公有领域演示素材（wav）」——**导入商用真歌（flac）时没有同步扩展**（`_import_demo_songs.py` 与 `_make_songs_singable.py` 都按原扩展名落 `data/audio/demo_*.<ext>`）；
- `sniff_audio_ext` 也不认 `fLaC` 魔数 → `resolve_media_type` 回落 `audio/mpeg`（内容与 MIME 不符，严格客户端可能拒播——与 BUG-5 同类）。

## 修复

1. `practice.py`：`_SAFE_NAME` 补 `flac`（白名单是防路径穿越，不是格式政策）。
2. `upload.py`：`AUDIO_MEDIA_TYPE` 补 `"flac": "audio/flac"`；`sniff_audio_ext` 补 `fLaC` 魔数分支。

## 验证

- **接口**：8 首全部 `200`，flac 回 `Content-Type: audio/flac`、mp3 回 `audio/mpeg`（修复前 7 首 400）。
- **回归测试（修复前必失败已实测）**：`test_m2_core.py::test_published_song_flac_asset_playable`——`git stash` 两个生产文件后报 `AssertionError: {"code":40001,"message":"bad audio name"} / 400 == 200`，恢复即绿；`test_audio_container.py` 补 flac 嗅探与 MIME 断言；全量 **826 passed / 4 skipped**；`ruff check` + `format --check` 通过。
- **端到端**：桌面 CDP 探针打开 Moon Halo（flac）点「原唱」→ 按钮转「停止原唱」、底部/歌词时钟推进 `00:03`、`GET demo_honkai-moon-halo.flac` 200、无错误 toast（截图 `local/ui-check/sing-flac-play.png`）。

## 踩坑

- **uvicorn `--reload` 在 Windows 上偶发「看着在跑但不重载」**：改完文件 curl 仍 400，但监听 PID 后来自己变了（9512 → 46988）才生效——真机/演示前改后端代码，**用一次真实请求复验**，别只信「--reload 已开」。
- **同时暴露的两个相邻问题（未修，登记）**：① 10 首公有领域曲在库内是 `archived` → `_is_published_song_asset` 不豁免、`GET /songs` 也不列出（它们的 `song_*.wav` 现为 403）；② `vocal_ref_url`（人声分离轨）不在素材豁免里（豁免只查 `audio_url`），直接点该 URL 会 403——前端不请求它，属潜在缺口。
