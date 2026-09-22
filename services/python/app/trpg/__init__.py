"""酒馆（TRPG 跑团）域：三件套（事实表 / 状态快照 / 防遗忘校验）、工具循环与 SSE 回合。

模块地图（迁移自 ai4u，纯函数与服务分层一一对应）：
- :mod:`app.trpg.facts`：规范化 key / 提取解析 / upsert 裁决（纯函数）；
- :mod:`app.trpg.dice`：骰子解析/判定/文本（纯函数）；
- :mod:`app.trpg.snapshot`：状态快照组装（纯函数）；
- :mod:`app.trpg.verify`：悬空/落差/矛盾（纯函数）；
- :mod:`app.trpg.state`：事实/任务/线索/实体/事件的唯一写入口（DB）；
- :mod:`app.trpg.tools`：roll_dice / set_scene 工具定义与执行；
- :mod:`app.trpg.turn`：LLM 工具循环（流式正文 + 工具回放）；
- :mod:`app.trpg.service`：DM 门面（上下文组装 + SSE 事件流 + 系统卡）；
- :mod:`app.trpg.extractor`：叙事事实提取（每 2 回合，后台 fire-and-forget）；
- :mod:`app.trpg.events`：SSE 事件模型（前端手写镜像，不进 gen:api）。
"""
