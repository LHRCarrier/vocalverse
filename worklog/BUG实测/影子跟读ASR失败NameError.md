# BUG：影子跟读 ASR 失败 → NameError（用户只看到「管线提示：internal」）

> 发现：2026-09-21（酒馆迁移重构时静态审查发现，非线上实测；已补回归用例）
> 归档：`services/python/app/practice/orchestrator.py:_shadow_turn` · 执行人：LHRCarrier

## 复现

1. 进入影子跟读会话（`POST /api/v1/sessions` `{kind:"shadow", shadow_material_id}`）；
2. 提交跟读录音（`POST /api/v1/sessions/{id}/turns`，`action=normal` + audio）；
3. 让 ASR 转写抛错（引擎崩溃 / 上游 503 / 模型文件缺失）。

**修复前现象**：SSE 收到 `{"type":"error","code":"internal"}`，无 `turn_end`；前端提示「管线提示：internal」——用户不知道是自己的录音问题还是服务故障，也不会被引导重录。

**修复后现象**：正常 `turn_start → meta_block(coach_note=「听不清请再试」) → turn_end`，评分缺省降级（不伪造分数）。

## 根因

`_shadow_turn` 的 ASR 段：

```python
try:
    res = await asr.transcribe(audio)   # 抛错 → res 从未绑定
    ...
except Exception as exc:
    logger.warning("shadow asr failed: %s", exc)

coach = coach_note(sc) or (
    ("It sounds quiet ..." if getattr(res, "no_speech", False) else "Couldn't catch that ...")
    if not transcript else None
)
```

`res` 只在 try 内赋值；异常路径下 `getattr(res, ...)` 抛 `NameError: name 'res' is not defined`，被路由层 `except Exception` 兜成 `error(internal)`。该分支同时是 vasr-10「静音/听不清分流」提示的入口，属**必然触发但一直无测试覆盖**的路径。

## 修复

`try` 前显式 `res = None`（no_speech 判定失败即按「听不清」提示，语义正确）。

## 验证

新增 `services/python/tests/test_shadow_asr_failure.py`（2 例）：

- `test_shadow_asr_failure_degrades_gracefully`：ASR 桩抛错 → 断言 SSE 无 `error` 且有 `turn_end`；
- `test_shadow_asr_none_speech_still_notes`：正常 Fake ASR 路径不回归。

**修复前必失败实测**：临时移除 `res = None` 后跑用例 → `FAILED ... test_shadow_asr_failure_degrades_gracefully`；恢复修复后 `2 passed`（`uv run pytest tests/test_shadow_asr_failure.py -q`）。

## 踩坑

- 该类「异常路径引用 try 内变量」的问题在静态类型检查（ruff/mypy 未启用 F821 到局部变量运行期检测）下不会暴露；SSE 路由的 `except Exception` 又会把任何异常压成 `internal`，**错误信息零可观测**——迁移/重构时应优先给「降级分支」补用例（本次即迁移酒馆时顺手审查出）。
