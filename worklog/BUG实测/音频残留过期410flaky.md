# BUG：test_save_audio_and_ownership 顺序依赖 flaky（残留音频过期 mtime → 410）

> 归档：2026-09-03（9/3 框架重构基线核查时发现；属既有缺陷，非本次改动引入）

## 复现

全量 `uv run pytest -q`（services/python）→ `tests/test_m2_core.py::test_save_audio_and_ownership` 失败：
`assert 410 == 403`（期望未归属音频返回 403，实际 410）。

单跑 `uv run pytest tests/test_m2_core.py::test_save_audio_and_ownership -q` → **绿**。
即：**全量红、单跑绿**，且取决于 `data/audio-test/` 磁盘残留状态——同一命令连跑两次，第二次绿（第一次把过期文件惰性删除了）。

## 根因

1. `save_audio_bytes`（`app/practice/orchestrator.py:63-74`）以 `sha1(data)[:32].mp3` 做文件名 + `if not os.path.exists(path)` 才写盘——**去重命中时不刷新 mtime**（这是产品侧的既定去重行为，docs/19-架构与实现模式评审报告.md:212 已登记同类跨用户共享隐患：过期判定按首次创建 mtime）。
2. 测试音频内容固定（`b"MP3 data for test"`）→ 跨测试运行文件名恒定。上一轮运行残留的文件若其 mtime 已超过 `audio_ttl_hours`（24h→测试环境也可能有旧文件）或运行/机器时间偏移，`GET /audio` 路由（`app/api/routes/practice.py:240-243`）先判过期 → **410** 并**惰性删除**该文件；本轮测试重跑时文件已删、重新写盘 → 绿。顺序与残留状态耦合 → flaky。
3. 测试基建没有像 DB 那样做**每测试隔离**（conftest `_fresh_db` 只重置 DB，不重置音频目录）。

## 修复

`services/python/tests/conftest.py` 的 `_fresh_db` autouse fixture 增加音频目录隔离：
`shutil.rmtree(get_settings().audio_dir, ignore_errors=True)`（每个测试函数运行前清空，与 DB 隔离同语义；`save_audio_bytes` 会自建目录）。

## 验证

- 修复前：全量 pytest 出现 1 failed（410≠403），单跑绿；
- 修复后：全量 `uv run pytest -q` 连续 2 次 **83 passed**（含该用例），顺序无关；
- 无生产行为变更（仅测试夹具；生产 sha1 去重 + 惰性过期是 docs/19 R 系列登记项，另案处理）。

## 踩坑

- 测试隔离不止 DB：**凡有确定性文件名的既有状态（本仓 = 音频目录 sha1 文件名），都要纳入 `_fresh_db` 级别的清理**；
- 「全量红单跑绿」先怀疑**共享文件系统残留**，再看测试顺序（本次 1 分钟内定位）；用两次连跑验证「自愈性」可以锁定「惰性删除」类根因（第一次删、第二次绿）。
