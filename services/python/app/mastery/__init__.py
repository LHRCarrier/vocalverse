"""匹配机制模块（Python 写方）：掌握度写入。

- service.update_session_mastery：会话收尾写 user_corpus_mastery（句级）+ user_mastery（场景级）。
"""

from .service import update_session_mastery

__all__ = ["update_session_mastery"]
