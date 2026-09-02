package com.vocalverse.content.controller;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.content.PlacementQuestionEntity;
import com.vocalverse.content.PlacementQuestionRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.time.Instant;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 入学测试题库管理（**Java 写**，docs/06 §9.2「admin 题库预置」；docs/11 Q-B06）。
 *
 * <p>exam_revision 版本化：改题=新版本（不覆写历史）；status 仅 published/archived（无 draft， 题库必须可复现）；(examRevision,
 * itemIndex) 唯一。
 */
@RestController
@RequestMapping("/api/v1/admin/placement-questions")
public class QuestionAdminController {

  public record QuestionUpsert(
      @NotNull @Min(1) Integer examRevision,
      @NotNull @Min(1) Integer itemIndex,
      @NotBlank @Pattern(regexp = "read|qa") String kind,
      @NotBlank String prompt,
      String referenceAnswer) {}

  public record QuestionPatch(
      @NotBlank @Pattern(regexp = "read|qa") String kind,
      @NotBlank String prompt,
      String referenceAnswer,
      @NotNull @Pattern(regexp = "published|archived") String status) {}

  public record QuestionView(
      Long id,
      Integer examRevision,
      Integer itemIndex,
      String kind,
      String prompt,
      String referenceAnswer,
      String status,
      Instant createdAt,
      Instant updatedAt) {}

  private final PlacementQuestionRepository questions;

  public QuestionAdminController(PlacementQuestionRepository questions) {
    this.questions = questions;
  }

  /** 缺省 examRevision = 当前最大版本。 */
  @GetMapping
  public Envelope<List<QuestionView>> list(
      @RequestParam(required = false) @Min(1) Integer examRevision) {
    int revision = examRevision == null ? questions.maxExamRevision() : examRevision;
    return Envelope.ok(
        questions.findByExamRevisionOrderByItemIndexAsc(revision).stream()
            .map(QuestionAdminController::toView)
            .toList());
  }

  @PostMapping
  public Envelope<QuestionView> create(@Valid @RequestBody QuestionUpsert body) {
    if (questions.existsByExamRevisionAndItemIndex(body.examRevision(), body.itemIndex())) {
      throw new ResponseStatusException(
          HttpStatus.CONFLICT, "item index already exists in revision " + body.examRevision());
    }
    Instant now = Instant.now();
    PlacementQuestionEntity e = new PlacementQuestionEntity();
    e.setExamRevision(body.examRevision());
    e.setItemIndex(body.itemIndex());
    e.setKind(body.kind());
    e.setPrompt(body.prompt());
    e.setReferenceAnswer(body.referenceAnswer());
    e.setStatus("published");
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return Envelope.ok(toView(questions.save(e)));
  }

  /** examRevision/itemIndex 不可改（唯一键）；改内容请走新版本（docs/10 §4.2）。 */
  @PutMapping("/{id}")
  public Envelope<QuestionView> update(
      @PathVariable Long id, @Valid @RequestBody QuestionPatch body) {
    PlacementQuestionEntity e = requireQuestion(id);
    e.setKind(body.kind());
    e.setPrompt(body.prompt());
    e.setReferenceAnswer(body.referenceAnswer());
    e.setStatus(body.status());
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(toView(questions.save(e)));
  }

  /** 归档（status→archived，保留历史版本）。 */
  @DeleteMapping("/{id}")
  public Envelope<QuestionView> archive(@PathVariable Long id) {
    PlacementQuestionEntity e = requireQuestion(id);
    e.setStatus("archived");
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(toView(questions.save(e)));
  }

  private PlacementQuestionEntity requireQuestion(Long id) {
    return questions
        .findById(id)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "question not found"));
  }

  private static QuestionView toView(PlacementQuestionEntity e) {
    return new QuestionView(
        e.getId(),
        e.getExamRevision(),
        e.getItemIndex(),
        e.getKind(),
        e.getPrompt(),
        e.getReferenceAnswer(),
        e.getStatus(),
        e.getCreatedAt(),
        e.getUpdatedAt());
  }
}
