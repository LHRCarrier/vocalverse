package com.vocalverse.ticket;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 工单（**Java 写**；用户提交反馈/报错/纠误 → open → processing → resolved → closed，docs/06 §9.6）。
 *
 * <p>- kind：feedback(反馈)/bug(报错)/content_correction(内容纠误)； - target_type 仅在 content_correction
 * 时挂具体对象（scene/song/attempt/none）； - admin_id 可空（未认领）；resolved_at 在流转到 resolved 时由服务端落。
 */
@Entity
@Table(name = "tickets")
public class TicketEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "user_id", nullable = false)
  private Long userId;

  @Column(nullable = false, length = 32)
  private String kind;

  @Column(name = "target_type", length = 16)
  private String targetType;

  @Column(name = "target_id")
  private Long targetId;

  @Column(length = 128)
  private String title;

  @Column(nullable = false)
  private String content;

  @Column(nullable = false, length = 16)
  private String status;

  @Column(name = "admin_id")
  private Long adminId;

  @Column(name = "admin_reply")
  private String adminReply;

  @Column(name = "resolved_at")
  private Instant resolvedAt;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
  }

  public Long getUserId() {
    return userId;
  }

  public void setUserId(Long userId) {
    this.userId = userId;
  }

  public String getKind() {
    return kind;
  }

  public void setKind(String kind) {
    this.kind = kind;
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

  public String getTitle() {
    return title;
  }

  public void setTitle(String title) {
    this.title = title;
  }

  public String getContent() {
    return content;
  }

  public void setContent(String content) {
    this.content = content;
  }

  public String getStatus() {
    return status;
  }

  public void setStatus(String status) {
    this.status = status;
  }

  public Long getAdminId() {
    return adminId;
  }

  public void setAdminId(Long adminId) {
    this.adminId = adminId;
  }

  public String getAdminReply() {
    return adminReply;
  }

  public void setAdminReply(String adminReply) {
    this.adminReply = adminReply;
  }

  public Instant getResolvedAt() {
    return resolvedAt;
  }

  public void setResolvedAt(Instant resolvedAt) {
    this.resolvedAt = resolvedAt;
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
