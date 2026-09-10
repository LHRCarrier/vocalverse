package com.vocalverse.console.content;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.console.audit.AuditService;
import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.auth.CurrentAdmin;
import com.vocalverse.console.rbac.PermissionCatalog;
import com.vocalverse.console.rbac.RequireConsolePermission;
import com.vocalverse.content.ListeningMaterialEntity;
import com.vocalverse.content.ListeningMaterialRepository;
import com.vocalverse.content.LrcEntity;
import com.vocalverse.content.LrcRepository;
import com.vocalverse.content.PlacementQuestionEntity;
import com.vocalverse.content.PlacementQuestionRepository;
import com.vocalverse.content.ScenarioEntity;
import com.vocalverse.content.ScenarioRepository;
import com.vocalverse.content.SongEntity;
import com.vocalverse.content.SongRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 运营域**内容写入**端点（场景 / 歌曲 + LRC / 听力素材 / 题库）。
 *
 * <h2>为什么这个文件存在（而不是什么都不做）</h2>
 *
 * <p>旧管理端（{@code /api/v1/admin/**} 的 {@code ContentAdminController} / {@code
 * QuestionAdminController}）被整体退役。但退役前逐条核对能力矩阵发现： 控制台的内容面**只有读 + 上下架**，没有任何 create/update/delete。
 * 若直接删掉旧控制器，全仓将**不存在**任何能新建/编辑歌曲、场景、听力素材、题库的 HTTP 端点 —— 运营的职责（docs/50 §0「音乐、书籍、音频/媒体管理」，其中音乐/音频/题库归
 * Java） 就没有写路径了，而且 {@link PublishService} 也失去意义（没有内容可上架）。
 *
 * <p>这与工单域是同一类问题（前端查到的「删了以后没人能处理」），所以采用同一处置： **把能力搬到控制台**，然后删掉旧路径。净效果仍是「{@code /api/v1/admin/**}
 * 彻底消失」， 但没有能力回退，且每一次写都进审计。
 *
 * <h2>与旧实现的关系</h2>
 *
 * <p>校验注解、字段映射、归档语义（DELETE = {@code status → archived}，禁物理删除） 与旧控制器**逐字一致** ——
 * 那些是既有契约，不是本次要改的东西。本文件只做三件事不同：
 *
 * <ol>
 *   <li>权限码（{@code @RequireConsolePermission}）替代 {@code hasRole("ADMIN")}；
 *   <li>每次写落一行审计（旧面完全没有留痕）；
 *   <li>入参非法走 {@code 46007}（控制台错误码段）而不是 40001。 <b>例外</b>：LRC 整首重写仍沿用「删旧插新 + seq 重排 +
 *       pitch_ref_status→missing」的既有语义。
 * </ol>
 */
@RestController
@RequestMapping("/api/v1/console/content")
public class ConsoleContentWriteController {

  // ------------------------------------------------------------------ DTO（与旧面同形）

  public record ScenarioUpsert(
      @NotBlank @Size(max = 128) String title,
      @NotBlank @Pattern(regexp = "cafe|airport|interview|library|other") String sceneType,
      @NotNull @Min(1) @Max(4) Integer difficulty,
      @Size(max = 512) String description,
      @NotBlank String systemPrompt,
      @NotBlank String openingLine,
      String targetCorpus,
      String interestTags,
      @Min(1) Integer promptVersion,
      @Min(1) Integer estimatedTurns,
      @Min(1) Integer estimatedMinutes,
      @Pattern(regexp = "draft|published|archived") String status) {}

  public record SongUpsert(
      @NotBlank @Size(max = 128) String title,
      @Size(max = 128) String artist,
      @NotNull @Min(1) @Max(4) Integer level,
      @Min(0) Long durationS,
      BigDecimal bpm,
      @Size(max = 8) String musicalKey,
      @NotBlank @Size(max = 512) String audioUrl,
      @Size(max = 512) String lrcUrl,
      @Size(max = 512) String coverUrl,
      String interestTags,
      @Pattern(regexp = "public_domain|original|demo_only") String source,
      @Pattern(regexp = "draft|published|archived") String status,
      @Pattern(regexp = "missing|building|ready|invalid") String pitchRefStatus) {}

  /** 单句歌词行（PUT lrc 用；seq 由服务端按数组顺序重排）。 */
  public record LrcLine(
      @NotNull @Min(0) Long offsetMs, @Min(0) Long endOffsetMs, @NotBlank String lineText) {}

  public record LrcUpsert(@NotNull List<LrcLine> lines) {}

  public record MaterialUpsert(
      @NotBlank @Size(max = 128) String title,
      @NotNull @Min(1) @Max(4) Integer level,
      @NotBlank @Size(max = 512) String audioUrl,
      @Min(0) Long durationS,
      String transcript,
      String interestTags,
      @Pattern(regexp = "public_domain|original|demo_only") String source,
      @Size(max = 64) String license,
      @Pattern(regexp = "draft|published|archived") String status) {}

  public record QuestionUpsert(
      @NotNull @Min(1) Integer examRevision,
      @NotNull @Min(1) Integer itemIndex,
      @NotBlank @Pattern(regexp = "read|qa") String kind,
      @NotBlank String prompt,
      String referenceAnswer,
      @Pattern(regexp = "published|archived") String status) {}

  public record QuestionPatch(
      @NotBlank String prompt,
      String referenceAnswer,
      @Pattern(regexp = "published|archived") String status) {}

  // ------------------------------------------------------------------ 字段

  private final SongRepository songs;
  private final ScenarioRepository scenarios;
  private final ListeningMaterialRepository materials;
  private final PlacementQuestionRepository questions;
  private final LrcRepository lrcs;
  private final AuditService audit;

  public ConsoleContentWriteController(
      SongRepository songs,
      ScenarioRepository scenarios,
      ListeningMaterialRepository materials,
      PlacementQuestionRepository questions,
      LrcRepository lrcs,
      AuditService audit) {
    this.songs = songs;
    this.scenarios = scenarios;
    this.materials = materials;
    this.questions = questions;
    this.lrcs = lrcs;
    this.audit = audit;
  }

  // ------------------------------------------------------------------ 单条读取
  //
  // 旧面的 GET /{resource}/{id} 在控制台**没有对应物**：控制台的 GET /content/songs 是分页列表，
  // 点进详情页只能靠「在列表里找」或「记住整页数据」—— 翻页/筛选后详情就取不到了。
  // 所以这里补齐单条读取，权限复用各自的 :read 码（读不新增码）。

  @GetMapping("/songs/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_READ)
  @Transactional(readOnly = true)
  public Envelope<Map<String, Object>> getSong(@PathVariable Long id) {
    return Envelope.ok(songView(requireSong(id)));
  }

  @GetMapping("/scenarios/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SCENARIO_READ)
  @Transactional(readOnly = true)
  public Envelope<Map<String, Object>> getScenario(@PathVariable Long id) {
    return Envelope.ok(scenarioView(requireScenario(id)));
  }

  @GetMapping("/listening-materials/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_LISTENING_READ)
  @Transactional(readOnly = true)
  public Envelope<Map<String, Object>> getMaterial(@PathVariable Long id) {
    return Envelope.ok(materialView(requireMaterial(id)));
  }

  @GetMapping("/questions/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_QUESTION_READ)
  @Transactional(readOnly = true)
  public Envelope<Map<String, Object>> getQuestion(@PathVariable Long id) {
    PlacementQuestionEntity e =
        questions
            .findById(id)
            .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "题目不存在"));
    return Envelope.ok(questionView(e));
  }

  // ------------------------------------------------------------------ 场景

  @PostMapping("/scenarios")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SCENARIO_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> createScenario(
      @CurrentAdmin ConsolePrincipal me, @Valid @RequestBody ScenarioUpsert body) {
    Instant now = Instant.now();
    ScenarioEntity e = new ScenarioEntity();
    applyScenario(e, body);
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    ScenarioEntity saved = scenarios.save(e);
    auditRecord(
        me, "content.scenario.create", "scenario", saved.getId(), "新建场景：" + saved.getTitle());
    return Envelope.ok(scenarioView(saved));
  }

  @PutMapping("/scenarios/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SCENARIO_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> updateScenario(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody ScenarioUpsert body) {
    ScenarioEntity e = requireScenario(id);
    String prev = e.getStatus();
    applyScenario(e, body);
    e.setUpdatedAt(Instant.now());
    ScenarioEntity saved = scenarios.save(e);
    auditRecord(
        me,
        "content.scenario.update",
        "scenario",
        id,
        "更新场景：" + saved.getTitle(),
        Map.of("prevStatus", prev, "nextStatus", saved.getStatus()));
    return Envelope.ok(scenarioView(saved));
  }

  /**
   * 归档（**禁物理删除**，与旧面同语义）：{@code status → archived}。
   *
   * <p>旧面注释已经说明「归档即软删」，控制台沿用 —— 物理删除会让已发出的题目/战绩引用悬空， 而 {@code docs/50 §6.1} 也明确「控制台不再提供物理删除」。
   */
  @DeleteMapping("/scenarios/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SCENARIO_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> archiveScenario(
      @CurrentAdmin ConsolePrincipal me, @PathVariable Long id) {
    ScenarioEntity e = requireScenario(id);
    String prev = e.getStatus();
    e.setStatus(PublishService.STATUS_ARCHIVED);
    e.setUpdatedAt(Instant.now());
    ScenarioEntity saved = scenarios.save(e);
    auditRecord(
        me,
        "content.scenario.archive",
        "scenario",
        id,
        "归档场景：" + saved.getTitle(),
        Map.of("prevStatus", prev, "nextStatus", saved.getStatus()));
    return Envelope.ok(scenarioView(saved));
  }

  // ------------------------------------------------------------------ 歌曲 + LRC

  @PostMapping("/songs")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> createSong(
      @CurrentAdmin ConsolePrincipal me, @Valid @RequestBody SongUpsert body) {
    Instant now = Instant.now();
    SongEntity e = new SongEntity();
    applySong(e, body);
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    SongEntity saved = songs.save(e);
    auditRecord(me, "content.song.create", "song", saved.getId(), "新建歌曲：" + saved.getTitle());
    return Envelope.ok(songView(saved));
  }

  @PutMapping("/songs/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> updateSong(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody SongUpsert body) {
    SongEntity e = requireSong(id);
    String prev = e.getStatus();
    applySong(e, body);
    e.setUpdatedAt(Instant.now());
    SongEntity saved = songs.save(e);
    auditRecord(
        me,
        "content.song.update",
        "song",
        id,
        "更新歌曲：" + saved.getTitle(),
        Map.of("prevStatus", prev, "nextStatus", saved.getStatus()));
    return Envelope.ok(songView(saved));
  }

  @DeleteMapping("/songs/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> archiveSong(
      @CurrentAdmin ConsolePrincipal me, @PathVariable Long id) {
    SongEntity e = requireSong(id);
    String prev = e.getStatus();
    e.setStatus(PublishService.STATUS_ARCHIVED);
    e.setUpdatedAt(Instant.now());
    SongEntity saved = songs.save(e);
    auditRecord(
        me,
        "content.song.archive",
        "song",
        id,
        "归档歌曲：" + saved.getTitle(),
        Map.of("prevStatus", prev, "nextStatus", saved.getStatus()));
    return Envelope.ok(songView(saved));
  }

  @GetMapping("/songs/{id}/lrc")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_READ)
  @Transactional(readOnly = true)
  public Envelope<List<Map<String, Object>>> getLrc(@PathVariable Long id) {
    requireSong(id);
    List<Map<String, Object>> out = new ArrayList<>();
    for (LrcEntity l : lrcs.findBySongIdOrderBySeqAsc(id)) {
      Map<String, Object> m = new LinkedHashMap<>();
      m.put("seq", l.getSeq());
      m.put("offsetMs", l.getOffsetMs());
      m.put("endOffsetMs", l.getEndOffsetMs());
      m.put("lineText", l.getLineText());
      m.put("source", l.getSource());
      out.add(m);
    }
    return Envelope.ok(out);
  }

  /**
   * LRC 整首重写（与旧面同语义）：删旧插新 + {@code seq} 按请求顺序重排； {@code source} 继承 {@code songs.source}（docs/11
   * Q-B19 冗余一致性）； 若 {@code pitch_ref_status} 原为 {@code ready} 则置回 {@code missing}，触发 Python 离线重提取。
   *
   * <p>这条「置回 missing」是**必须保留**的既有语义：LRC 改了而参考旋律还是旧的，跟唱打分会用错误的 参考音高 —— 比没有参考更糟（会给出看似有据的错分）。
   */
  @PutMapping("/songs/{id}/lrc")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_WRITE)
  @Transactional
  public Envelope<List<Map<String, Object>>> replaceLrc(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody LrcUpsert body) {
    SongEntity song = requireSong(id);
    String prevPitch = song.getPitchRefStatus();
    lrcs.deleteBySongId(id);
    Instant now = Instant.now();
    List<LrcEntity> saved = new ArrayList<>();
    int seq = 1;
    for (LrcLine line : body.lines()) {
      LrcEntity l = new LrcEntity();
      l.setSongId(id);
      l.setSeq(seq++);
      l.setOffsetMs(line.offsetMs());
      l.setEndOffsetMs(line.endOffsetMs());
      l.setLineText(line.lineText());
      l.setSource(song.getSource());
      l.setCreatedAt(now);
      saved.add(lrcs.save(l));
    }
    if ("ready".equals(song.getPitchRefStatus())) {
      song.setPitchRefStatus("missing");
      song.setUpdatedAt(now);
      songs.save(song);
    }
    List<Map<String, Object>> out = new ArrayList<>();
    for (LrcEntity l : saved) {
      Map<String, Object> m = new LinkedHashMap<>();
      m.put("seq", l.getSeq());
      m.put("offsetMs", l.getOffsetMs());
      m.put("endOffsetMs", l.getEndOffsetMs());
      m.put("lineText", l.getLineText());
      m.put("source", l.getSource());
      out.add(m);
    }
    auditRecord(
        me,
        "content.song.lrc_replace",
        "song",
        id,
        "重写歌曲 LRC：" + saved.size() + " 行",
        Map.of(
            "violationCount",
            saved.size(),
            "before",
            prevPitch,
            "after",
            song.getPitchRefStatus()));
    return Envelope.ok(out);
  }

  // ------------------------------------------------------------------ 听力素材

  @PostMapping("/listening-materials")
  @RequireConsolePermission(PermissionCatalog.CONTENT_LISTENING_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> createMaterial(
      @CurrentAdmin ConsolePrincipal me, @Valid @RequestBody MaterialUpsert body) {
    Instant now = Instant.now();
    ListeningMaterialEntity e = new ListeningMaterialEntity();
    applyMaterial(e, body);
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    ListeningMaterialEntity saved = materials.save(e);
    auditRecord(
        me,
        "content.listening.create",
        "listening_material",
        saved.getId(),
        "新建听力素材：" + saved.getTitle());
    return Envelope.ok(materialView(saved));
  }

  @PutMapping("/listening-materials/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_LISTENING_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> updateMaterial(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody MaterialUpsert body) {
    ListeningMaterialEntity e = requireMaterial(id);
    String prev = e.getStatus();
    applyMaterial(e, body);
    e.setUpdatedAt(Instant.now());
    ListeningMaterialEntity saved = materials.save(e);
    auditRecord(
        me,
        "content.listening.update",
        "listening_material",
        id,
        "更新听力素材：" + saved.getTitle(),
        Map.of("prevStatus", prev, "nextStatus", saved.getStatus()));
    return Envelope.ok(materialView(saved));
  }

  @DeleteMapping("/listening-materials/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_LISTENING_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> archiveMaterial(
      @CurrentAdmin ConsolePrincipal me, @PathVariable Long id) {
    ListeningMaterialEntity e = requireMaterial(id);
    String prev = e.getStatus();
    e.setStatus(PublishService.STATUS_ARCHIVED);
    e.setUpdatedAt(Instant.now());
    ListeningMaterialEntity saved = materials.save(e);
    auditRecord(
        me,
        "content.listening.archive",
        "listening_material",
        id,
        "归档听力素材：" + saved.getTitle(),
        Map.of("prevStatus", prev, "nextStatus", saved.getStatus()));
    return Envelope.ok(materialView(saved));
  }

  // ------------------------------------------------------------------ 题库

  /**
   * 新增题目（docs/10 §3.2：{@code exam_revision} 版本化，改题=新版本，不改历史）。
   *
   * <p>题库**默认 published**（与 draft 类内容不同）：入学测试必须可复现， 没有「半成品题目」这种状态（{@code PlacementQuestionEntity}
   * 类注释）。
   */
  @PostMapping("/questions")
  @RequireConsolePermission(PermissionCatalog.CONTENT_QUESTION_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> createQuestion(
      @CurrentAdmin ConsolePrincipal me, @Valid @RequestBody QuestionUpsert body) {
    if (questions.existsByExamRevisionAndItemIndex(body.examRevision(), body.itemIndex())) {
      throw ConsoleException.of(
          ConsoleErrorCodes.INVALID_PARAM,
          "同一版本内 itemIndex 已存在：" + body.examRevision() + "/" + body.itemIndex());
    }
    Instant now = Instant.now();
    PlacementQuestionEntity e = new PlacementQuestionEntity();
    e.setExamRevision(body.examRevision());
    e.setItemIndex(body.itemIndex());
    e.setKind(body.kind());
    e.setPrompt(body.prompt());
    e.setReferenceAnswer(body.referenceAnswer());
    e.setStatus(body.status() == null ? "published" : body.status());
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    PlacementQuestionEntity saved = questions.save(e);
    auditRecord(
        me,
        "content.question.create",
        "placement_question",
        saved.getId(),
        "新建题目：v" + saved.getExamRevision() + "#" + saved.getItemIndex());
    return Envelope.ok(questionView(saved));
  }

  @PutMapping("/questions/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_QUESTION_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> updateQuestion(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody QuestionPatch body) {
    PlacementQuestionEntity e =
        questions
            .findById(id)
            .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "题目不存在"));
    String prev = e.getStatus();
    e.setPrompt(body.prompt());
    e.setReferenceAnswer(body.referenceAnswer());
    if (body.status() != null) {
      e.setStatus(body.status());
    }
    e.setUpdatedAt(Instant.now());
    PlacementQuestionEntity saved = questions.save(e);
    auditRecord(
        me,
        "content.question.update",
        "placement_question",
        id,
        "更新题目：v" + saved.getExamRevision() + "#" + saved.getItemIndex(),
        Map.of("prevStatus", prev, "nextStatus", saved.getStatus()));
    return Envelope.ok(questionView(saved));
  }

  /** 归档题目（禁物理删除：历史战绩引用要能解出题干）。 */
  @DeleteMapping("/questions/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_QUESTION_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> archiveQuestion(
      @CurrentAdmin ConsolePrincipal me, @PathVariable Long id) {
    PlacementQuestionEntity e =
        questions
            .findById(id)
            .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "题目不存在"));
    String prev = e.getStatus();
    e.setStatus(PublishService.STATUS_ARCHIVED);
    e.setUpdatedAt(Instant.now());
    PlacementQuestionEntity saved = questions.save(e);
    auditRecord(
        me,
        "content.question.archive",
        "placement_question",
        id,
        "归档题目：v" + saved.getExamRevision() + "#" + saved.getItemIndex(),
        Map.of("prevStatus", prev, "nextStatus", saved.getStatus()));
    return Envelope.ok(questionView(saved));
  }

  // ------------------------------------------------------------------ 内部

  private void auditRecord(
      ConsolePrincipal me, String action, String targetType, Long id, String summary) {
    auditRecord(me, action, targetType, id, summary, null);
  }

  private void auditRecord(
      ConsolePrincipal me,
      String action,
      String targetType,
      Long id,
      String summary,
      Map<String, Object> extra) {
    Map<String, Object> detail = extra == null ? new LinkedHashMap<>() : new LinkedHashMap<>(extra);
    detail.putIfAbsent("targetType", targetType);
    audit.record(me, action, targetType, String.valueOf(id), summary, detail);
  }

  private void applyScenario(ScenarioEntity e, ScenarioUpsert b) {
    e.setTitle(b.title());
    e.setSceneType(b.sceneType());
    e.setDifficulty(b.difficulty());
    e.setDescription(b.description());
    e.setSystemPrompt(b.systemPrompt());
    e.setOpeningLine(b.openingLine());
    e.setTargetCorpus(b.targetCorpus());
    e.setInterestTags(b.interestTags() == null ? "[]" : b.interestTags());
    e.setPromptVersion(b.promptVersion() == null ? 1 : b.promptVersion());
    e.setEstimatedTurns(b.estimatedTurns());
    e.setEstimatedMinutes(b.estimatedMinutes());
    e.setStatus(b.status() == null ? PublishService.STATUS_DRAFT : b.status());
  }

  private void applySong(SongEntity e, SongUpsert b) {
    e.setTitle(b.title());
    e.setArtist(b.artist());
    e.setLevel(b.level());
    e.setDurationS(b.durationS());
    e.setBpm(b.bpm());
    e.setMusicalKey(b.musicalKey());
    e.setAudioUrl(b.audioUrl());
    e.setLrcUrl(b.lrcUrl());
    e.setCoverUrl(b.coverUrl());
    e.setInterestTags(b.interestTags() == null ? "[]" : b.interestTags());
    e.setSource(b.source() == null ? "public_domain" : b.source());
    e.setStatus(b.status() == null ? PublishService.STATUS_DRAFT : b.status());
    e.setPitchRefStatus(b.pitchRefStatus() == null ? "missing" : b.pitchRefStatus());
  }

  private void applyMaterial(ListeningMaterialEntity e, MaterialUpsert b) {
    e.setTitle(b.title());
    e.setLevel(b.level());
    e.setAudioUrl(b.audioUrl());
    e.setDurationS(b.durationS());
    e.setTranscript(b.transcript());
    e.setInterestTags(b.interestTags() == null ? "[]" : b.interestTags());
    e.setSource(b.source());
    e.setLicense(b.license());
    e.setStatus(b.status() == null ? PublishService.STATUS_DRAFT : b.status());
  }

  private ScenarioEntity requireScenario(Long id) {
    return scenarios
        .findById(id)
        .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "场景不存在"));
  }

  private SongEntity requireSong(Long id) {
    return songs
        .findById(id)
        .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "歌曲不存在"));
  }

  private ListeningMaterialEntity requireMaterial(Long id) {
    return materials
        .findById(id)
        .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "听力素材不存在"));
  }

  private static Map<String, Object> songView(SongEntity e) {
    Map<String, Object> m = new LinkedHashMap<>();
    m.put("id", e.getId());
    m.put("title", e.getTitle());
    m.put("artist", e.getArtist());
    m.put("level", e.getLevel());
    m.put("durationS", e.getDurationS());
    m.put("bpm", e.getBpm());
    m.put("musicalKey", e.getMusicalKey());
    m.put("audioUrl", e.getAudioUrl());
    m.put("lrcUrl", e.getLrcUrl());
    m.put("coverUrl", e.getCoverUrl());
    m.put("interestTags", e.getInterestTags());
    m.put("source", e.getSource());
    m.put("status", e.getStatus());
    m.put("pitchRefStatus", e.getPitchRefStatus());
    m.put("createdAt", e.getCreatedAt());
    m.put("updatedAt", e.getUpdatedAt());
    return m;
  }

  private static Map<String, Object> scenarioView(ScenarioEntity e) {
    Map<String, Object> m = new LinkedHashMap<>();
    m.put("id", e.getId());
    m.put("title", e.getTitle());
    m.put("sceneType", e.getSceneType());
    m.put("difficulty", e.getDifficulty());
    m.put("description", e.getDescription());
    m.put("systemPrompt", e.getSystemPrompt());
    m.put("openingLine", e.getOpeningLine());
    m.put("targetCorpus", e.getTargetCorpus());
    m.put("interestTags", e.getInterestTags());
    m.put("promptVersion", e.getPromptVersion());
    m.put("estimatedTurns", e.getEstimatedTurns());
    m.put("estimatedMinutes", e.getEstimatedMinutes());
    m.put("status", e.getStatus());
    m.put("createdAt", e.getCreatedAt());
    m.put("updatedAt", e.getUpdatedAt());
    return m;
  }

  private static Map<String, Object> materialView(ListeningMaterialEntity e) {
    Map<String, Object> m = new LinkedHashMap<>();
    m.put("id", e.getId());
    m.put("title", e.getTitle());
    m.put("level", e.getLevel());
    m.put("audioUrl", e.getAudioUrl());
    m.put("durationS", e.getDurationS());
    m.put("transcript", e.getTranscript());
    m.put("interestTags", e.getInterestTags());
    m.put("source", e.getSource());
    m.put("license", e.getLicense());
    m.put("status", e.getStatus());
    m.put("createdAt", e.getCreatedAt());
    m.put("updatedAt", e.getUpdatedAt());
    return m;
  }

  private static Map<String, Object> questionView(PlacementQuestionEntity e) {
    Map<String, Object> m = new LinkedHashMap<>();
    m.put("id", e.getId());
    m.put("examRevision", e.getExamRevision());
    m.put("itemIndex", e.getItemIndex());
    m.put("kind", e.getKind());
    m.put("prompt", e.getPrompt());
    m.put("referenceAnswer", e.getReferenceAnswer());
    m.put("status", e.getStatus());
    m.put("createdAt", e.getCreatedAt());
    m.put("updatedAt", e.getUpdatedAt());
    return m;
  }
}
