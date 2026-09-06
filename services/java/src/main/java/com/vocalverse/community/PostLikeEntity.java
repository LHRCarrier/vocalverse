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
 * 帖子点赞（Java 写 · docs/37 §3.1）：(post_id, liker_id) 唯一，幂等由唯一键兜底； unlike = 物理删行（不软删，避免撞唯一索引）。PG 由
 * Alembic CHECK/唯一约束守护。
 */
@Entity
@Table(
    name = "post_likes",
    uniqueConstraints = {
      @UniqueConstraint(
          columnNames = {"post_id", "liker_id"},
          name = "uq_post_likes_post_liker")
    },
    indexes = {@Index(name = "ix_post_likes_post", columnList = "post_id")})
public class PostLikeEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "post_id", nullable = false)
  private Long postId;

  @Column(name = "liker_id", nullable = false)
  private Long likerId;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public Long getId() {
    return id;
  }

  public Long getPostId() {
    return postId;
  }

  public void setPostId(Long postId) {
    this.postId = postId;
  }

  public Long getLikerId() {
    return likerId;
  }

  public void setLikerId(Long likerId) {
    this.likerId = likerId;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
