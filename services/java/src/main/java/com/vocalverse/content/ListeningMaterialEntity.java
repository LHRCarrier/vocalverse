package com.vocalverse.content;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** 听力素材（**Java 写**；推荐候选池第三类，docs/06 §9.5/§9.6；版权字段 docs/11 Q-B19）。 */
@Entity
@Table(name = "listening_materials")
public class ListeningMaterialEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(nullable = false, length = 128)
  private String title;

  @Column(nullable = false)
  private Integer level;

  @Column(name = "audio_url", nullable = false, length = 512)
  private String audioUrl;

  @Column(name = "duration_s")
  private Long durationS;

  @Column private String transcript;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "interest_tags", nullable = false)
  private String interestTags;

  @Column(length = 32)
  private String source;

  @Column(length = 64)
  private String license;

  @Column(nullable = false, length = 16)
  private String status;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
  }

  public String getTitle() {
    return title;
  }

  public void setTitle(String title) {
    this.title = title;
  }

  public Integer getLevel() {
    return level;
  }

  public void setLevel(Integer level) {
    this.level = level;
  }

  public String getAudioUrl() {
    return audioUrl;
  }

  public void setAudioUrl(String audioUrl) {
    this.audioUrl = audioUrl;
  }

  public Long getDurationS() {
    return durationS;
  }

  public void setDurationS(Long durationS) {
    this.durationS = durationS;
  }

  public String getTranscript() {
    return transcript;
  }

  public void setTranscript(String transcript) {
    this.transcript = transcript;
  }

  public String getInterestTags() {
    return interestTags;
  }

  public void setInterestTags(String interestTags) {
    this.interestTags = interestTags;
  }

  public String getSource() {
    return source;
  }

  public void setSource(String source) {
    this.source = source;
  }

  public String getLicense() {
    return license;
  }

  public void setLicense(String license) {
    this.license = license;
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
