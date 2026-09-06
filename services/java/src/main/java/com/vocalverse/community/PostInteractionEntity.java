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
 * 互动时序单（Java 写 · docs/37 §3.1）：like/coin/share 唯一 (actor_id, post_id, action) 幂等；
 * 无软删列——取消表态=物理删行。画像/通知（S2）数据源。
 */
@Entity
@Table(
    name = "post_interactions",
    uniqueConstraints = {
      @UniqueConstraint(
          columnNames = {"actor_id", "post_id", "action"},
          name = "uq_post_interactions_actor_post_action")
    },
    indexes = {
      @Index(name = "ix_post_interactions_post_action", columnList = "post_id, action, created_at")
    })
public class PostInteractionEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "actor_id", nullable = false)
  private Long actorId;

  @Column(name = "post_id", nullable = false)
  private Long postId;

  /** like / coin / share（PG 由 Alembic CHECK 守护） */
  @Column(name = "action", nullable = false, length = 16)
  private String action;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public Long getId() {
    return id;
  }

  public Long getActorId() {
    return actorId;
  }

  public void setActorId(Long actorId) {
    this.actorId = actorId;
  }

  public Long getPostId() {
    return postId;
  }

  public void setPostId(Long postId) {
    this.postId = postId;
  }

  public String getAction() {
    return action;
  }

  public void setAction(String action) {
    this.action = action;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
