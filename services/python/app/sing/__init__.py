"""唱歌域（参考旋律提取 + 跟唱评分编排；2026-09-09 唱歌 P0）。

- ``jobs``：pitch_extract_jobs 事实源（扫描/工作器/内部 REST 委托）；
- ``service``（P4）：评分任务态（Redis+内存兜底）、sing 桶、ISE 抽样句、结果落库。
"""
