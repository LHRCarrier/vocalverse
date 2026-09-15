package com.vocalverse.console.rbac;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 管理端账号（docs/50 §5.3.1；Java 写方）。
 *
 * <p><b>与 {@code users} 表无任何外键/字段共享</b>（docs/50 §4.1）：管理端账号不能登录 App，App 账号不能登录控制台。
 *
 * <p>{@code status} 只表达「永久启用/停用」，临时锁定一律用 {@code lockedUntil} —— 避免双真源（docs/50 §5.3.1 决策）。 {@code
 * tokenEpoch} 在停用/改权/改密时 +1：JWT 的 {@code epo} claim 与之比对，使「停用/降权在下一个请求即生效」 （docs/50 §4.1 补偿项②③），无需等
 * 900s TTL。
 */
@Entity
@Table(name = "admin_users")
public class AdminUserEntity {

  public static final String STATUS_ACTIVE = "active";
  public static final String STATUS_DISABLED = "disabled";

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "username", nullable = false, length = 32)
  private String username;

  @Column(name = "display_name", nullable = false, length = 64)
  private String displayName;

  @Column(name = "password_hash", nullable = false, length = 100)
  private String passwordHash;

  @Column(name = "role_id", nullable = false)
  private Long roleId;

  @Column(name = "status", nullable = false, length = 16)
  private String status;

  @Column(name = "failed_attempts", nullable = false)
  private short failedAttempts;

  @Column(name = "locked_until")
  private Instant lockedUntil;

  @Column(name = "token_epoch", nullable = false)
  private int tokenEpoch;

  @Column(name = "last_login_at")
  private Instant lastLoginAt;

  @Column(name = "last_login_ip", length = 45)
  private String lastLoginIp;

  @Column(name = "created_by")
  private Long createdBy;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
  }

  public String getUsername() {
    return username;
  }

  public void setUsername(String username) {
    this.username = username;
  }

  public String getDisplayName() {
    return displayName;
  }

  public void setDisplayName(String displayName) {
    this.displayName = displayName;
  }

  public String getPasswordHash() {
    return passwordHash;
  }

  public void setPasswordHash(String passwordHash) {
    this.passwordHash = passwordHash;
  }

  public Long getRoleId() {
    return roleId;
  }

  public void setRoleId(Long roleId) {
    this.roleId = roleId;
  }

  public String getStatus() {
    return status;
  }

  public void setStatus(String status) {
    this.status = status;
  }

  public short getFailedAttempts() {
    return failedAttempts;
  }

  public void setFailedAttempts(short failedAttempts) {
    this.failedAttempts = failedAttempts;
  }

  public Instant getLockedUntil() {
    return lockedUntil;
  }

  public void setLockedUntil(Instant lockedUntil) {
    this.lockedUntil = lockedUntil;
  }

  public int getTokenEpoch() {
    return tokenEpoch;
  }

  public void setTokenEpoch(int tokenEpoch) {
    this.tokenEpoch = tokenEpoch;
  }

  public Instant getLastLoginAt() {
    return lastLoginAt;
  }

  public void setLastLoginAt(Instant lastLoginAt) {
    this.lastLoginAt = lastLoginAt;
  }

  public String getLastLoginIp() {
    return lastLoginIp;
  }

  public void setLastLoginIp(String lastLoginIp) {
    this.lastLoginIp = lastLoginIp;
  }

  public Long getCreatedBy() {
    return createdBy;
  }

  public void setCreatedBy(Long createdBy) {
    this.createdBy = createdBy;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }

  public void setUpdatedAt(Instant updatedAt) {
    this.updatedAt = updatedAt;
  }

  /** 当前是否可用（status=active 且未被 lockedUntil 锁住）。 */
  public boolean isUsable(Instant now) {
    return STATUS_ACTIVE.equals(status) && (lockedUntil == null || !lockedUntil.isAfter(now));
  }
}
