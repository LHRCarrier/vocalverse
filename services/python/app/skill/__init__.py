"""推荐系统-水平评价模块（Python 写方）：更新用户动态水平。

- service.update_user_level：重算并落库 user_skill_state（冷启动/滞回/低谷/幂等/事务）。
- service.notify_java_level：委托 Java 回写权威档（默认关，考试专属）。
"""
