package com.vocalverse.console.rbac;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 登录尝试流水（docs/50 §5.3.6；Java 写方）。
 *
 * <p>账号锁定与 IP 限流**都走本表窗口计数**（docs/50 §4.1：Redis 不参与）—— 好处是「为什么锁的」在库里可追溯， 代价是每次登录多两条 count 查询（控制台
 * QPS 极低，可接受）。
 *
 * <p>{@code reason} 为归因快照：{@code ok|bad_password|locked|disabled|unknown_user|throttled}。 注意 {@code
 * unknown_user} <b>只落库不对外</b>：对外错误码统一 46004，避免用户名枚举（见 ConsoleAuthService 注释）。
 */
@Entity
@Table(name = "admin_login_attempts")
public class AdminLoginAttemptEntity {

  public static final String REASON_OK = "ok";

  /** 成功登录（与 {@link #REASON_OK} 同义，保留一个更直白的别名供登录路径引用）。 */
  public static final String REASON_LOGIN = "ok";

  public static final String REASON_BAD_PASSWORD = "bad_password";
  public static final String REASON_LOCKED = "locked";
  public static final String REASON_DISABLED = "disabled";
  public static final String REASON_UNKNOWN_USER = "unknown_user";
  public static final String REASON_THROTTLED = "throttled";

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "username", nullable = false, length = 32)
  private String username;

  @Column(name = "admin_user_id")
  private Long adminUserId;

  @Column(name = "ip", length = 45)
  private String ip;

  @Column(name = "success", nullable = false)
  private boolean success;

  @Column(name = "reason", length = 32)
  private String reason;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public Long getId() {
    return id;
  }

  public String getUsername() {
    return username;
  }

  public void setUsername(String username) {
    this.username = username;
  }

  public Long getAdminUserId() {
    return adminUserId;
  }

  public void setAdminUserId(Long adminUserId) {
    this.adminUserId = adminUserId;
  }

  public String getIp() {
    return ip;
  }

  public void setIp(String ip) {
    this.ip = ip;
  }

  public boolean isSuccess() {
    return success;
  }

  public void setSuccess(boolean success) {
    this.success = success;
  }

  public String getReason() {
    return reason;
  }

  public void setReason(String reason) {
    this.reason = reason;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
