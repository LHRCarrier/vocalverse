package com.vocalverse.console.moderation;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 用户举报（docs/50 §5.3.9；Java 写方）。
 *
 * <p>部分唯一索引 {@code uq_moderation_reports_reporter_target (reporter_user_id,target_type,target_id)
 * WHERE status='pending'} 保证「同一用户对同一目标只留一条待处理举报」——重复举报返回 46015 并回传既有 {@code caseId}（幂等，docs/50
 * §10.4）。H2 不支持部分唯一索引，服务层同样以条件查询兜底。
 */
@Entity
@Table(name = "moderation_reports")
public class ModerationReportEntity {

  public static final String STATUS_PENDING = "pending";
  public static final String STATUS_ACCEPTED = "accepted";
  public static final String STATUS_REJECTED = "rejected";
  public static final String STATUS_DUPLICATE = "duplicate";

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "reporter_user_id", nullable = false)
  private Long reporterUserId;

  @Column(name = "target_type", nullable = false, length = 16)
  private String targetType;

  @Column(name = "target_id", nullable = false)
  private Long targetId;

  @Column(name = "reason_code", nullable = false, length = 32)
  private String reasonCode;

  @Column(name = "detail", length = 500)
  private String detail;

  @Column(name = "status", nullable = false, length = 16)
  private String status;

  @Column(name = "case_id")
  private Long caseId;

  @Column(name = "handled_by")
  private Long handledBy;

  @Column(name = "handled_at")
  private Instant handledAt;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
  }

  public Long getReporterUserId() {
    return reporterUserId;
  }

  public void setReporterUserId(Long reporterUserId) {
    this.reporterUserId = reporterUserId;
  }

  public String getTargetType() {
    return targetType;
  }

  public void setTargetType(String targetType) {
    this.targetType = targetType;
  }

  public Long getTargetId() {
    return targetId;
  }

  public void setTargetId(Long targetId) {
    this.targetId = targetId;
  }

  public String getReasonCode() {
    return reasonCode;
  }

  public void setReasonCode(String reasonCode) {
    this.reasonCode = reasonCode;
  }

  public String getDetail() {
    return detail;
  }

  public void setDetail(String detail) {
    this.detail = detail;
  }

  public String getStatus() {
    return status;
  }

  public void setStatus(String status) {
    this.status = status;
  }

  public Long getCaseId() {
    return caseId;
  }

  public void setCaseId(Long caseId) {
    this.caseId = caseId;
  }

  public Long getHandledBy() {
    return handledBy;
  }

  public void setHandledBy(Long handledBy) {
    this.handledBy = handledBy;
  }

  public Instant getHandledAt() {
    return handledAt;
  }

  public void setHandledAt(Instant handledAt) {
    this.handledAt = handledAt;
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
}
