package com.vocalverse.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** 学习档案（Java 写；1:1 用户；cefr_level 为最近一次入学测试/人工校正快照）。 */
@Entity
@Table(name = "user_profiles")
public class UserProfileEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "user_id", nullable = false, unique = true)
  private Long userId;

  @Column(name = "age_group", nullable = false, length = 16)
  private String ageGroup;

  @Column(name = "cefr_level", nullable = false, length = 8)
  private String cefrLevel;

  @Column(name = "learning_goal", length = 255)
  private String learningGoal;

  /** 兴趣标签 JSON 数组文本；应用层负责 JsonNode 转换（docs/10 §5.2 纯映射+校验）。 */
  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "interest_tags", nullable = false)
  private String interestTags;

  @Column(name = "voice_rate", nullable = false, length = 16)
  private String voiceRate;

  @Column(name = "voice_type", length = 32)
  private String voiceType;

  @Column(name = "preferred_difficulty")
  private Integer preferredDifficulty;

  @Column(name = "avatar_url", length = 512)
  private String avatarUrl;

  @Column(name = "cefr_level_source", nullable = false, length = 16)
  private String cefrLevelSource;

  @Column(name = "cefr_level_at")
  private Instant cefrLevelAt;

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

  public String getAgeGroup() {
    return ageGroup;
  }

  public void setAgeGroup(String ageGroup) {
    this.ageGroup = ageGroup;
  }

  public String getCefrLevel() {
    return cefrLevel;
  }

  public void setCefrLevel(String cefrLevel) {
    this.cefrLevel = cefrLevel;
  }

  public String getLearningGoal() {
    return learningGoal;
  }

  public void setLearningGoal(String learningGoal) {
    this.learningGoal = learningGoal;
  }

  public String getInterestTags() {
    return interestTags;
  }

  public void setInterestTags(String interestTags) {
    this.interestTags = interestTags;
  }

  public String getVoiceRate() {
    return voiceRate;
  }

  public void setVoiceRate(String voiceRate) {
    this.voiceRate = voiceRate;
  }

  public String getVoiceType() {
    return voiceType;
  }

  public void setVoiceType(String voiceType) {
    this.voiceType = voiceType;
  }

  public Integer getPreferredDifficulty() {
    return preferredDifficulty;
  }

  public void setPreferredDifficulty(Integer preferredDifficulty) {
    this.preferredDifficulty = preferredDifficulty;
  }

  public String getAvatarUrl() {
    return avatarUrl;
  }

  public void setAvatarUrl(String avatarUrl) {
    this.avatarUrl = avatarUrl;
  }

  public String getCefrLevelSource() {
    return cefrLevelSource;
  }

  public void setCefrLevelSource(String cefrLevelSource) {
    this.cefrLevelSource = cefrLevelSource;
  }

  public Instant getCefrLevelAt() {
    return cefrLevelAt;
  }

  public void setCefrLevelAt(Instant cefrLevelAt) {
    this.cefrLevelAt = cefrLevelAt;
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
