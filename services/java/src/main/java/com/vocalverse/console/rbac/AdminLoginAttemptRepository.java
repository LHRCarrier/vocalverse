package com.vocalverse.console.rbac;

import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 登录尝试仓库（docs/50 §5.3.6）：窗口计数即锁定/限流的唯一依据（无 Redis）。 */
public interface AdminLoginAttemptRepository extends JpaRepository<AdminLoginAttemptEntity, Long> {

  /** 同账号失败次数（窗口内；只数失败行，成功登录会清零 failed_attempts）。 */
  @Query(
      "select count(a) from AdminLoginAttemptEntity a "
          + "where lower(a.username) = lower(:username) and a.success = false and a.createdAt > :since")
  long countFailuresSince(@Param("username") String username, @Param("since") Instant since);

  /** 同 IP 尝试总数（成功+失败；docs/50 §4.1：20 次 / 5 分钟）。 */
  @Query(
      "select count(a) from AdminLoginAttemptEntity a "
          + "where a.ip = :ip and a.createdAt > :since")
  long countByIpSince(@Param("ip") String ip, @Param("since") Instant since);

  /** 窗口内最早一条的时间（用于算 retryAfter）。 */
  @Query(
      "select min(a.createdAt) from AdminLoginAttemptEntity a "
          + "where a.ip = :ip and a.createdAt > :since")
  Instant earliestByIpSince(@Param("ip") String ip, @Param("since") Instant since);
}
