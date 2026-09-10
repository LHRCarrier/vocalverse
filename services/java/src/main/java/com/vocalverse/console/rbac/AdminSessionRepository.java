package com.vocalverse.console.rbac;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 管理端会话仓库（docs/50 §5.3.5）。吊销一律条件更新，避免 read-modify-write 竞态。 */
public interface AdminSessionRepository extends JpaRepository<AdminSessionEntity, Long> {

  Optional<AdminSessionEntity> findByRefreshTokenHash(String refreshTokenHash);

  /** 在线会话列表（未吊销且未过期）。 */
  @Query(
      "select s from AdminSessionEntity s "
          + "where s.revokedAt is null and s.expiresAt > :now "
          + "order by s.issuedAt desc")
  Page<AdminSessionEntity> findActive(@Param("now") Instant now, Pageable pageable);

  /** 吊销单条（已吊销则 0 行，天然幂等）。 */
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      "update AdminSessionEntity s set s.revokedAt = :now, s.revokeReason = :reason "
          + "where s.id = :id and s.revokedAt is null")
  int revoke(@Param("id") Long id, @Param("reason") String reason, @Param("now") Instant now);

  /** 吊销某账号全部会话（停用/改权/改密/强制下线，docs/50 §4.1 补偿项②）。 */
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      "update AdminSessionEntity s set s.revokedAt = :now, s.revokeReason = :reason "
          + "where s.adminUserId = :adminUserId and s.revokedAt is null")
  int revokeAllForUser(
      @Param("adminUserId") Long adminUserId,
      @Param("reason") String reason,
      @Param("now") Instant now);

  List<AdminSessionEntity> findByAdminUserIdOrderByIdDesc(Long adminUserId);
}
