package com.vocalverse.content;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * 歌曲库（**Java 写**；demo 只用公有领域/自创曲，商用音乐不入库 docs/06 §9.7）。
 *
 * <p>pitch_ref_status：LRC 重写后由 Java 置回 missing，Python 离线任务提取完翻转 ready/INVALID （docs/10
 * §3.2-2）；跟唱请求见 status != ready 返回「生成中」，不静默算分。
 */
@Entity
@Table(name = "songs")
public class SongEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(nullable = false, length = 128)
  private String title;

  @Column(length = 128)
  private String artist;

  @Column(nullable = false)
  private Integer level;

  @Column(name = "duration_s")
  private Long durationS;

  @Column(precision = 6, scale = 2)
  private BigDecimal bpm;

  @Column(name = "musical_key", length = 8)
  private String musicalKey;

  @Column(name = "audio_url", nullable = false, length = 512)
  private String audioUrl;

  @Column(name = "lrc_url", length = 512)
  private String lrcUrl;

  @Column(name = "cover_url", length = 512)
  private String coverUrl;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "interest_tags", nullable = false)
  private String interestTags;

  @Column(nullable = false, length = 32)
  private String source;

  @Column(nullable = false, length = 16)
  private String status;

  @Column(name = "pitch_ref_status", nullable = false, length = 24)
  private String pitchRefStatus;

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

  public String getArtist() {
    return artist;
  }

  public void setArtist(String artist) {
    this.artist = artist;
  }

  public Integer getLevel() {
    return level;
  }

  public void setLevel(Integer level) {
    this.level = level;
  }

  public Long getDurationS() {
    return durationS;
  }

  public void setDurationS(Long durationS) {
    this.durationS = durationS;
  }

  public BigDecimal getBpm() {
    return bpm;
  }

  public void setBpm(BigDecimal bpm) {
    this.bpm = bpm;
  }

  public String getMusicalKey() {
    return musicalKey;
  }

  public void setMusicalKey(String musicalKey) {
    this.musicalKey = musicalKey;
  }

  public String getAudioUrl() {
    return audioUrl;
  }

  public void setAudioUrl(String audioUrl) {
    this.audioUrl = audioUrl;
  }

  public String getLrcUrl() {
    return lrcUrl;
  }

  public void setLrcUrl(String lrcUrl) {
    this.lrcUrl = lrcUrl;
  }

  public String getCoverUrl() {
    return coverUrl;
  }

  public void setCoverUrl(String coverUrl) {
    this.coverUrl = coverUrl;
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

  public String getStatus() {
    return status;
  }

  public void setStatus(String status) {
    this.status = status;
  }

  public String getPitchRefStatus() {
    return pitchRefStatus;
  }

  public void setPitchRefStatus(String pitchRefStatus) {
    this.pitchRefStatus = pitchRefStatus;
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
