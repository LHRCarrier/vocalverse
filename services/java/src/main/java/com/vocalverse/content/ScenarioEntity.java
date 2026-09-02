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

/**
 * 对话场景模板（**Java 写**；schema 由 Alembic 唯一真源，本类仅纯映射 ddl-auto=none，docs/10 §3）。
 *
 * <p>status 仅 draft/published/archived（不物理删除）；interest_tags JSON 数组（推荐匹配用）。
 */
@Entity
@Table(name = "scenarios")
public class ScenarioEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(nullable = false, length = 128)
  private String title;

  @Column(name = "scene_type", nullable = false, length = 32)
  private String sceneType;

  @Column(nullable = false)
  private Integer difficulty;

  @Column(length = 512)
  private String description;

  @Column(name = "system_prompt", nullable = false)
  private String systemPrompt;

  @Column(name = "opening_line", nullable = false)
  private String openingLine;

  @Column(name = "target_corpus")
  private String targetCorpus;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(name = "interest_tags", nullable = false)
  private String interestTags;

  @Column(name = "prompt_version", nullable = false)
  private Integer promptVersion;

  @Column(name = "estimated_turns")
  private Integer estimatedTurns;

  @Column(name = "estimated_minutes")
  private Integer estimatedMinutes;

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

  public String getSceneType() {
    return sceneType;
  }

  public void setSceneType(String sceneType) {
    this.sceneType = sceneType;
  }

  public Integer getDifficulty() {
    return difficulty;
  }

  public void setDifficulty(Integer difficulty) {
    this.difficulty = difficulty;
  }

  public String getDescription() {
    return description;
  }

  public void setDescription(String description) {
    this.description = description;
  }

  public String getSystemPrompt() {
    return systemPrompt;
  }

  public void setSystemPrompt(String systemPrompt) {
    this.systemPrompt = systemPrompt;
  }

  public String getOpeningLine() {
    return openingLine;
  }

  public void setOpeningLine(String openingLine) {
    this.openingLine = openingLine;
  }

  public String getTargetCorpus() {
    return targetCorpus;
  }

  public void setTargetCorpus(String targetCorpus) {
    this.targetCorpus = targetCorpus;
  }

  public String getInterestTags() {
    return interestTags;
  }

  public void setInterestTags(String interestTags) {
    this.interestTags = interestTags;
  }

  public Integer getPromptVersion() {
    return promptVersion;
  }

  public void setPromptVersion(Integer promptVersion) {
    this.promptVersion = promptVersion;
  }

  public Integer getEstimatedTurns() {
    return estimatedTurns;
  }

  public void setEstimatedTurns(Integer estimatedTurns) {
    this.estimatedTurns = estimatedTurns;
  }

  public Integer getEstimatedMinutes() {
    return estimatedMinutes;
  }

  public void setEstimatedMinutes(Integer estimatedMinutes) {
    this.estimatedMinutes = estimatedMinutes;
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
