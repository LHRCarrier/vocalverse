"""控制台 API（docs/50 §3.3）：鉴权依赖 + 路由。

Python 侧只负责 ``ops`` 与 ``library`` 两个子路径（Java 负责 ``auth|admins|roles|…``，
子路径不重叠，docs/50 §3.2）。
"""
