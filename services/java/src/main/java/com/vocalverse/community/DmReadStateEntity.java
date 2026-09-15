package com.vocalverse.community;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.Instant;

/**
 * 私信已读水位（Java 写 · docs/49 §1.2，迁移 0012）。
 *
 * <p><b>水位是 {@code last_read_id} 而非时间戳</b>：时间戳水位在并发提交下会跨过尚未渲染的消息， 造成永久漏未读；消息 id 单调，取 {@code max(现有,
 * upTo)} 无此问题（docs/49 §4.3 B2）。 未读 = 对端 visible 消息中 {@code id > last_read_id} 的条数（缺行视作 0）。
 *
 * <p>主键形态：代理主键 {@code id} + 业务唯一键 {@code (user_id, peer_id)}（本仓 Java/JPA 侧统一 {@code @Id Long id}）。
 */
@Entity
@Table(
    name = "dm_read_state",
    uniqueConstraints = {
      @UniqueConstraint(
          columnNames = {"user_id", "peer_id"},
          name = "uq_dm_read_state_user_peer")
    },
    indexes = {@Index(name = "ix_dm_read_state_user", columnList = "user_id")})
public class DmReadStateEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "user_id", nullable = false)
  private Long userId;

  @Column(name = "peer_id", nullable = false)
  private Long peerId;

  @Column(name = "last_read_id", nullable = false)
  private Long lastReadId = 0L;

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

  public Long getPeerId() {
    return peerId;
  }

  public void setPeerId(Long peerId) {
    this.peerId = peerId;
  }

  public Long getLastReadId() {
    return lastReadId;
  }

  public void setLastReadId(Long lastReadId) {
    this.lastReadId = lastReadId;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }

  public void setUpdatedAt(Instant updatedAt) {
    this.updatedAt = updatedAt;
  }
}
