package com.vocalverse.console.audit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * 管理员操作审计（docs/50 §5.3.7；Java 写方）。<b>append-only：无 {@code updated_at}。</b>
 *
 * <h2>「append-only」在本仓是**纪律**，不是 DB 强制</h2>
 *
 * <p>不要读成「数据库保证不可修改」——核实的实际情况是：
 *
 * <ul>
 *   <li>{@code infra/} 下只有 {@code README.md} 与 {@code dev/.wslconfig}，**没有** {@code
 *       pg/init-roles.sh} 之类的角色分离脚本（docs/50 提到的方案未落地）；
 *   <li>全库只有一个 owner 角色，没有任何 {@code BEFORE UPDATE/DELETE} 触发器保护本表。
 * </ul>
 *
 * <p>因此 append-only 目前成立的**真实理由**只有两条，二者都在应用层：
 *
 * <ol>
 *   <li>本模块没有任何 UPDATE/DELETE 路径 —— {@link AdminAuditLogRepository} 刻意不声明这些方法， {@code
 *       ConsoleAuditController} 只有 GET；
 *   <li>管理员账号**只停用、从不删除**（docs/50 §5.3.1：{@code status} 表达启用/停用，无删除端点）， 所以 {@code admin_user_id} 的
 *       FK {@code ON DELETE SET NULL} 实际上永远不会触发， 快照列 {@code admin_username}
 *       也不是「为了兜住删号」而存在，而是为了**快照语义** （改名后旧记录仍显示当时的用户名）。
 * </ol>
 *
 * <p>要把它变成 DB 强制，需要一次独立的 DDL 变更（角色分离或触发器）—— 不在本模块范围， 已作为已知缺口上报。在那之前，任何新增的写方法都必须先在这里说明理由。
 *
 * <p>{@code detail} 走字段白名单（{@link AuditFieldAllowlist}），口令/令牌等永不落库（docs/50 §9.3 红线）。
 */
@Entity
@Table(name = "admin_audit_logs")
public class AdminAuditLogEntity {

  public static final String RESULT_OK = "ok";
  public static final String RESULT_DENIED = "denied";
  public static final String RESULT_FAILED = "failed";

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "admin_user_id")
  private Long adminUserId;

  @Column(name = "admin_username", nullable = false, length = 32)
  private String adminUsername;

  @Column(name = "action", nullable = false, length = 64)
  private String action;

  @Column(name = "target_type", length = 32)
  private String targetType;

  @Column(name = "target_id", length = 64)
  private String targetId;

  @Column(name = "result", nullable = false, length = 16)
  private String result;

  @Column(name = "error_code")
  private Integer errorCode;

  @Column(name = "summary", nullable = false, length = 255)
  private String summary;

  /** jsonb；应用层经 ObjectMapper 序列化（同 PostEntity.tags 惯例），写入前过白名单。 */
  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "detail")
  private String detail;

  @Column(name = "request_id", length = 64)
  private String requestId;

  @Column(name = "ip", length = 45)
  private String ip;

  @Column(name = "duration_ms")
  private Integer durationMs;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public Long getId() {
    return id;
  }

  public Long getAdminUserId() {
    return adminUserId;
  }

  public void setAdminUserId(Long adminUserId) {
    this.adminUserId = adminUserId;
  }

  public String getAdminUsername() {
    return adminUsername;
  }

  public void setAdminUsername(String adminUsername) {
    this.adminUsername = adminUsername;
  }

  public String getAction() {
    return action;
  }

  public void setAction(String action) {
    this.action = action;
  }

  public String getTargetType() {
    return targetType;
  }

  public void setTargetType(String targetType) {
    this.targetType = targetType;
  }

  public String getTargetId() {
    return targetId;
  }

  public void setTargetId(String targetId) {
    this.targetId = targetId;
  }

  public String getResult() {
    return result;
  }

  public void setResult(String result) {
    this.result = result;
  }

  public Integer getErrorCode() {
    return errorCode;
  }

  public void setErrorCode(Integer errorCode) {
    this.errorCode = errorCode;
  }

  public String getSummary() {
    return summary;
  }

  public void setSummary(String summary) {
    this.summary = summary;
  }

  public String getDetail() {
    return detail;
  }

  public void setDetail(String detail) {
    this.detail = detail;
  }

  public String getRequestId() {
    return requestId;
  }

  public void setRequestId(String requestId) {
    this.requestId = requestId;
  }

  public String getIp() {
    return ip;
  }

  public void setIp(String ip) {
    this.ip = ip;
  }

  public Integer getDurationMs() {
    return durationMs;
  }

  public void setDurationMs(Integer durationMs) {
    this.durationMs = durationMs;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
