"""管理端控制台 · Python 侧（docs/50）。

两个子域：

- ``trace``：LLM 调用链采集（recorder + 有界批量 sink），Python 写 ``llm_*`` 三表；
- ``ops``：指标采集器 / 预警评估 / 依赖探测，Python 写 ``ops_*`` 三表。

控制台 Java 侧只**读**这些表（docs/50 §5.1 写方矩阵），写路径经 ``/api/v1/console/**`` 端点。
"""
