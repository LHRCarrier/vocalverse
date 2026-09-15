package com.vocalverse.console.moderation;

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
 * 审核工单（docs/50 §5.3.8；Java 写方）。状态机见 docs/50 §6.2。
 *
 * <p>部分唯一索引 {@code uq_moderation_cases_target_pending (target_type,target_id) WHERE status IN
 * ('pending','escalated')} 保证「同一目标不重复建待审单」（幂等）——H2 无法建 PG 部分唯一索引，所以 <b>服务层用条件查询兜底</b>（同 docs/37 对
 * uq_posts_checkin 的既有处置）。
 *
 * <p>本表只存**当前状态**：决定的前后状态在 {@code admin_audit_logs.detail}（单一审计流，docs/50 §5.3.7）。 {@code snippet}
 * 是送审内容截断快照（≤500），不存全文以免二次留存。
 */
@Entity
@Table(name = "moderation_cases")
public class ModerationCaseEntity {

  public static final String STATUS_PENDING = "pending";
  public static final String STATUS_APPROVED = "approved";
  public static final String STATUS_REJECTED = "rejected";
  public static final String STATUS_ESCALATED = "escalated";
  public static final String STATUS_WITHDRAWN = "withdrawn";

  public static final String TARGET_POST = "post";
  public static final String TARGET_COMMENT = "comment";
  public static final String TARGET_MEDIA = "media";
  public static final String TARGET_DIRECT_MESSAGE = "direct_message";

  public static final String SOURCE_AUTO = "auto";
  public static final String SOURCE_REPORT = "report";
  public static final String SOURCE_MANUAL = "manual";

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "target_type", nullable = false, length = 16)
  private String targetType;

  @Column(name = "target_id", nullable = false)
  private Long targetId;

  @Column(name = "source", nullable = false, length = 16)
  private String source;

  @Column(name = "reason_code", nullable = false, length = 32)
  private String reasonCode;

  @Column(name = "priority", nullable = false)
  private short priority;

  @Column(name = "status", nullable = false, length = 16)
  private String status;

  @Column(name = "snippet", length = 500)
  private String snippet;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "snapshot")
  private String snapshot;

  @Column(name = "reporter_user_id")
  private Long reporterUserId;

  @Column(name = "assignee_id")
  private Long assigneeId;

  @Column(name = "decided_by")
  private Long decidedBy;

  @Column(name = "decided_at")
  private Instant decidedAt;

  @Column(name = "decision_note", length = 500)
  private String decisionNote;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
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

  public String getSource() {
    return source;
  }

  public void setSource(String source) {
    this.source = source;
  }

  public String getReasonCode() {
    return reasonCode;
  }

  public void setReasonCode(String reasonCode) {
    this.reasonCode = reasonCode;
  }

  public short getPriority() {
    return priority;
  }

  public void setPriority(short priority) {
    this.priority = priority;
  }

  public String getStatus() {
    return status;
  }

  public void setStatus(String status) {
    this.status = status;
  }

  public String getSnippet() {
    return snippet;
  }

  public void setSnippet(String snippet) {
    this.snippet = snippet;
  }

  public String getSnapshot() {
    return snapshot;
  }

  public void setSnapshot(String snapshot) {
    this.snapshot = snapshot;
  }

  public Long getReporterUserId() {
    return reporterUserId;
  }

  public void setReporterUserId(Long reporterUserId) {
    this.reporterUserId = reporterUserId;
  }

  public Long getAssigneeId() {
    return assigneeId;
  }

  public void setAssigneeId(Long assigneeId) {
    this.assigneeId = assigneeId;
  }

  public Long getDecidedBy() {
    return decidedBy;
  }

  public void setDecidedBy(Long decidedBy) {
    this.decidedBy = decidedBy;
  }

  public Instant getDecidedAt() {
    return decidedAt;
  }

  public void setDecidedAt(Instant decidedAt) {
    this.decidedAt = decidedAt;
  }

  public String getDecisionNote() {
    return decisionNote;
  }

  public void setDecisionNote(String decisionNote) {
    this.decisionNote = decisionNote;
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
