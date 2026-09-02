package com.vocalverse.content;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 入学测试题库（**Java 写**；docs/06 §9.2「admin 题库预置，保证可复现」；docs/11 Q-B06）。
 *
 * <p>exam_revision 版本化（改题=新版本，不改历史）；status 仅 published/archived； kind 仅 read/qa。注意：入库默认 published（与
 * draft 类内容不同，题库必须可复现）。
 */
@Entity
@Table(name = "placement_questions")
public class PlacementQuestionEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "exam_revision", nullable = false)
  private Integer examRevision;

  @Column(name = "item_index", nullable = false)
  private Integer itemIndex;

  @Column(nullable = false, length = 16)
  private String kind;

  @Column(nullable = false)
  private String prompt;

  @Column(name = "reference_answer")
  private String referenceAnswer;

  @Column(nullable = false, length = 16)
  private String status;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
  }

  public Integer getExamRevision() {
    return examRevision;
  }

  public void setExamRevision(Integer examRevision) {
    this.examRevision = examRevision;
  }

  public Integer getItemIndex() {
    return itemIndex;
  }

  public void setItemIndex(Integer itemIndex) {
    this.itemIndex = itemIndex;
  }

  public String getKind() {
    return kind;
  }

  public void setKind(String kind) {
    this.kind = kind;
  }

  public String getPrompt() {
    return prompt;
  }

  public void setPrompt(String prompt) {
    this.prompt = prompt;
  }

  public String getReferenceAnswer() {
    return referenceAnswer;
  }

  public void setReferenceAnswer(String referenceAnswer) {
    this.referenceAnswer = referenceAnswer;
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
