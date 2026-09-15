package com.vocalverse.console.rbac;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 管理端会话 / 刷新令牌（docs/50 §5.3.5；Java 写方）。
 *
 * <p>只存 refresh token 的 <b>sha256 hex</b>（{@code char(64)}，唯一键），明文永不落库、永不进日志（docs/50 §9.3）。 {@code
 * revokedAt} 非空即失效；{@code revokeReason} ∈ logout/rotated/admin_revoked/role_changed（Alembic 侧 CHECK
 * 用 32 长度，另加 token_reuse_detected 用于轮换重放的全族吊销）。
 */
@Entity
@Table(name = "admin_sessions")
public class AdminSessionEntity {

  public static final String REASON_LOGOUT = "logout";
  public static final String REASON_ROTATED = "rotated";
  public static final String REASON_ADMIN_REVOKED = "admin_revoked";
  public static final String REASON_ROLE_CHANGED = "role_changed";

  /** 刷新令牌被重放（一次性轮换被绕过）→ 吊销同一账号全部会话（docs/50 §4.1「一次性轮换」的强化）。 */
  public static final String REASON_TOKEN_REUSE = "token_reuse_detected";

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "admin_user_id", nullable = false)
  private Long adminUserId;

  /** sha256 hex（64 字符）；Hibernate 侧钉死 char(64) 与 Alembic DDL 字符型一致。 */
  @Column(name = "refresh_token_hash", nullable = false, columnDefinition = "char(64)")
  private String refreshTokenHash;

  @Column(name = "issued_at", nullable = false)
  private Instant issuedAt;

  @Column(name = "expires_at", nullable = false)
  private Instant expiresAt;

  @Column(name = "revoked_at")
  private Instant revokedAt;

  @Column(name = "revoke_reason", length = 32)
  private String revokeReason;

  @Column(name = "user_agent", length = 255)
  private String userAgent;

  @Column(name = "ip", length = 45)
  private String ip;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  /**
   * 明文 refresh token 的**内存暂存**（不映射列，绝不落库、绝不进日志 —— docs/50 §9.3 红线）。
   *
   * <p>为什么放在实体上：{@link com.vocalverse.console.auth.ConsoleAuthService} 建会话时先算出明文算 sha256，
   * 之后需要把明文回传给调用方一次。用单独的 record 返回会更干净，但实体已经是最小改动面—— 关键是它必须 {@code @Transient}，否则 Hibernate 会去找
   * {@code refresh_token_plain} 列（生产 ddl-auto=none， 直接报 Unknown column）。
   */
  @jakarta.persistence.Transient private String refreshTokenPlain;

  public String getRefreshTokenPlain() {
    return refreshTokenPlain;
  }

  public void setRefreshTokenPlain(String refreshTokenPlain) {
    this.refreshTokenPlain = refreshTokenPlain;
  }

  public Long getId() {
    return id;
  }

  public Long getAdminUserId() {
    return adminUserId;
  }

  public void setAdminUserId(Long adminUserId) {
    this.adminUserId = adminUserId;
  }

  public String getRefreshTokenHash() {
    return refreshTokenHash;
  }

  public void setRefreshTokenHash(String refreshTokenHash) {
    this.refreshTokenHash = refreshTokenHash;
  }

  public Instant getIssuedAt() {
    return issuedAt;
  }

  public void setIssuedAt(Instant issuedAt) {
    this.issuedAt = issuedAt;
  }

  public Instant getExpiresAt() {
    return expiresAt;
  }

  public void setExpiresAt(Instant expiresAt) {
    this.expiresAt = expiresAt;
  }

  public Instant getRevokedAt() {
    return revokedAt;
  }

  public void setRevokedAt(Instant revokedAt) {
    this.revokedAt = revokedAt;
  }

  public String getRevokeReason() {
    return revokeReason;
  }

  public void setRevokeReason(String revokeReason) {
    this.revokeReason = revokeReason;
  }

  public String getUserAgent() {
    return userAgent;
  }

  public void setUserAgent(String userAgent) {
    this.userAgent = userAgent;
  }

  public String getIp() {
    return ip;
  }

  public void setIp(String ip) {
    this.ip = ip;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }

  public boolean isRevoked() {
    return revokedAt != null;
  }
}
