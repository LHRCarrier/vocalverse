package com.vocalverse.community;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * 社区帖子（Java 写 · docs/37 §3.1）：内容帖（article/video）+ 打卡卡（checkin，domain=NULL）。
 *
 * <p>JSON 列（tags/media/checkin_snapshot）为 JSON 文本，应用层经 ObjectMapper 转换（同
 * UserProfileEntity.interestTags 惯例）；checkin_snapshot 公开面 {overall, practice_count}。
 */
@Entity
@Table(
    name = "posts",
    indexes = {
      @Index(name = "ix_posts_feed_time", columnList = "status, created_at, id"),
      @Index(name = "ix_posts_domain_time", columnList = "status, domain, created_at, id"),
      @Index(name = "ix_posts_author", columnList = "author_id, created_at")
    })
public class PostEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "author_id", nullable = false)
  private Long authorId;

  @Column(name = "slug", unique = true)
  private String slug;

  /** article / video / checkin（PG 由 Alembic CHECK 守护） */
  @Column(name = "kind", nullable = false, length = 16)
  private String kind;

  /** news / teaching / overseas；checkin 为 NULL（仅「为你推荐」混排） */
  @Column(name = "domain", length = 16)
  private String domain;

  @Column(name = "title", length = 200)
  private String title;

  @Column(name = "body")
  private String body;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "tags")
  private String tags;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "media")
  private String media;

  @Column(name = "status", nullable = false, length = 16)
  private String status;

  @Column(name = "checkin_date")
  private java.time.LocalDate checkinDate;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "checkin_snapshot")
  private String checkinSnapshot;

  @Column(name = "session_id")
  private Long sessionId;

  @Column(name = "like_count", nullable = false)
  private int likeCount;

  @Column(name = "coin_count", nullable = false)
  private int coinCount;

  @Column(name = "comment_count", nullable = false)
  private int commentCount;

  @Column(name = "share_count", nullable = false)
  private int shareCount;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
  }

  public Long getAuthorId() {
    return authorId;
  }

  public void setAuthorId(Long authorId) {
    this.authorId = authorId;
  }

  public String getSlug() {
    return slug;
  }

  public void setSlug(String slug) {
    this.slug = slug;
  }

  public String getKind() {
    return kind;
  }

  public void setKind(String kind) {
    this.kind = kind;
  }

  public String getDomain() {
    return domain;
  }

  public void setDomain(String domain) {
    this.domain = domain;
  }

  public String getTitle() {
    return title;
  }

  public void setTitle(String title) {
    this.title = title;
  }

  public String getBody() {
    return body;
  }

  public void setBody(String body) {
    this.body = body;
  }

  public String getTags() {
    return tags;
  }

  public void setTags(String tags) {
    this.tags = tags;
  }

  public String getMedia() {
    return media;
  }

  public void setMedia(String media) {
    this.media = media;
  }

  public String getStatus() {
    return status;
  }

  public void setStatus(String status) {
    this.status = status;
  }

  public java.time.LocalDate getCheckinDate() {
    return checkinDate;
  }

  public void setCheckinDate(java.time.LocalDate checkinDate) {
    this.checkinDate = checkinDate;
  }

  public String getCheckinSnapshot() {
    return checkinSnapshot;
  }

  public void setCheckinSnapshot(String checkinSnapshot) {
    this.checkinSnapshot = checkinSnapshot;
  }

  public Long getSessionId() {
    return sessionId;
  }

  public void setSessionId(Long sessionId) {
    this.sessionId = sessionId;
  }

  public int getLikeCount() {
    return likeCount;
  }

  public void setLikeCount(int likeCount) {
    this.likeCount = likeCount;
  }

  public int getCoinCount() {
    return coinCount;
  }

  public void setCoinCount(int coinCount) {
    this.coinCount = coinCount;
  }

  public int getCommentCount() {
    return commentCount;
  }

  public void setCommentCount(int commentCount) {
    this.commentCount = commentCount;
  }

  public int getShareCount() {
    return shareCount;
  }

  public void setShareCount(int shareCount) {
    this.shareCount = shareCount;
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
