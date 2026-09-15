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
 * 关注关系（Java 写 · docs/37 §3.1 S2 启用）：(follower_id, followee_id) 唯一幂等； 无软删列（取消关注=物理删行）；PG 由 Alembic
 * CHECK 守护（follower <> followee）。
 */
@Entity
@Table(
    name = "follows",
    uniqueConstraints = {
      @UniqueConstraint(
          columnNames = {"follower_id", "followee_id"},
          name = "uq_follows_follower_followee")
    },
    indexes = {@Index(name = "ix_follows_followee", columnList = "followee_id")})
public class FollowEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "follower_id", nullable = false)
  private Long followerId;

  @Column(name = "followee_id", nullable = false)
  private Long followeeId;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public Long getId() {
    return id;
  }

  public Long getFollowerId() {
    return followerId;
  }

  public void setFollowerId(Long followerId) {
    this.followerId = followerId;
  }

  public Long getFolloweeId() {
    return followeeId;
  }

  public void setFolloweeId(Long followeeId) {
    this.followeeId = followeeId;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
