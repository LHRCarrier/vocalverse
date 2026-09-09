package com.vocalverse.user;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserProfileRepository extends JpaRepository<UserProfileEntity, Long> {

  Optional<UserProfileEntity> findByUserId(Long userId);

  /** 社区 feed 作者批量取（用 user_id 而非 PK——作者 id 是 users.id；2026-09-06 修复潜错） */
  List<UserProfileEntity> findByUserIdIn(List<Long> userIds);

  /**
   * @handle 大小写不敏感占用检查（迁移 0011 已建 lower(handle) 唯一索引兜底）
   */
  boolean existsByHandleIgnoreCaseAndUserIdNot(String handle, Long userId);
}
