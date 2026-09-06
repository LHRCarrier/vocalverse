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
 * 帖子评论（Java 写 · docs/37 §3.1）：平铺列表；root_id/reply_to_* 为嵌套楼 P1 预热（S1 恒 NULL）。 展示过滤
 * status='visible'（软删位 visible/hidden/deleted，PG 由 Alembic CHECK 守护）。
 */
@Entity
@Table(
    name = "post_comments",
    indexes = {
      @Index(name = "ix_post_comments_status_post", columnList = "status, post_id, created_at, id")
    })
public class PostCommentEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "post_id", nullable = false)
  private Long postId;

  @Column(name = "author_id", nullable = false)
  private Long authorId;

  @Column(name = "root_id")
  private Long rootId;

  @Column(name = "parent_id")
  private Long parentId;

  @Column(name = "reply_to_user_id")
  private Long replyToUserId;

  @Column(name = "reply_to_nickname", length = 64)
  private String replyToNickname;

  @Column(name = "body", nullable = false, length = 500)
  private String body;

  @Column(name = "status", nullable = false, length = 16)
  private String status;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
  }

  public Long getPostId() {
    return postId;
  }

  public void setPostId(Long postId) {
    this.postId = postId;
  }

  public Long getAuthorId() {
    return authorId;
  }

  public void setAuthorId(Long authorId) {
    this.authorId = authorId;
  }

  public Long getRootId() {
    return rootId;
  }

  public void setRootId(Long rootId) {
    this.rootId = rootId;
  }

  public Long getParentId() {
    return parentId;
  }

  public void setParentId(Long parentId) {
    this.parentId = parentId;
  }

  public Long getReplyToUserId() {
    return replyToUserId;
  }

  public void setReplyToUserId(Long replyToUserId) {
    this.replyToUserId = replyToUserId;
  }

  public String getReplyToNickname() {
    return replyToNickname;
  }

  public void setReplyToNickname(String replyToNickname) {
    this.replyToNickname = replyToNickname;
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

  public Instant getUpdatedAt() {
    return updatedAt;
  }

  public void setUpdatedAt(Instant updatedAt) {
    this.updatedAt = updatedAt;
  }
}
