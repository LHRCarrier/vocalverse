package com.vocalverse.community;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 一对一私信消息（Java 写 · docs/49 §1.1，迁移 0012）：只记 created_at（不可变行，无 updated_at）。
 *
 * <p>会话 = {@code (sender_id, recipient_id)} 有序对，不建会话表；{@code status} 为治理预留（本轮恒
 * 'visible'，无删除入口）。CHECK 自聊由 Alembic 守护（服务层先拦 42203）。
 */
@Entity
@Table(
    name = "direct_messages",
    indexes = {
      @Index(name = "ix_dm_pair_time", columnList = "sender_id, recipient_id, created_at, id"),
      @Index(name = "ix_dm_recipient_time", columnList = "recipient_id, created_at, id"),
      @Index(name = "ix_dm_sender_time", columnList = "sender_id, created_at, id")
    })
public class DirectMessageEntity {

  public static final String STATUS_VISIBLE = "visible";

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "sender_id", nullable = false)
  private Long senderId;

  @Column(name = "recipient_id", nullable = false)
  private Long recipientId;

  @Column(name = "body", nullable = false, length = 1000)
  private String body;

  @Column(name = "status", nullable = false, length = 16)
  private String status;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public Long getId() {
    return id;
  }

  public Long getSenderId() {
    return senderId;
  }

  public void setSenderId(Long senderId) {
    this.senderId = senderId;
  }

  public Long getRecipientId() {
    return recipientId;
  }

  public void setRecipientId(Long recipientId) {
    this.recipientId = recipientId;
  }

  public String getBody() {
    return body;
  }

  public void setBody(String body) {
    this.body = body;
  }

  public String getStatus() {
    return status;
  }

  public void setStatus(String status) {
    this.status = status;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
