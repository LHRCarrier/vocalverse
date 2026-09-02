package com.vocalverse.content.controller;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.common.dto.PageView;
import com.vocalverse.content.ListeningMaterialEntity;
import com.vocalverse.content.ListeningMaterialRepository;
import com.vocalverse.content.LrcEntity;
import com.vocalverse.content.LrcRepository;
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
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
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
 * 内容库管理端（docs/06 §9.6：场景/歌曲库 CRUD 含上下架；docs/10 §3 表写方=Java）。
 *
 * <p>约定：DELETE = 归档（status→archived，禁物理删除）；LRC 为「整首重写」（seq 按请求顺序 重排，songs.pitch_ref_status→missing
 * 触发 Python 离线重提取，docs/10 §3.2-2）。网关路径 /manage/api/v1/admin/**（SecurityConfig hasRole ADMIN 守门）。
 */
@RestController
@RequestMapping("/api/v1/admin")
public class ContentAdminController {

  // ---------------------------------------------------------------------------
  // DTO
  // ---------------------------------------------------------------------------

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

  public record ScenarioView(
      Long id,
      String title,
      String sceneType,
      Integer difficulty,
      String description,
      String systemPrompt,
      String openingLine,
      String targetCorpus,
      String interestTags,
      Integer promptVersion,
      Integer estimatedTurns,
      Integer estimatedMinutes,
      String status,
      Instant createdAt,
      Instant updatedAt) {}

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

  public record SongView(
      Long id,
      String title,
      String artist,
      Integer level,
      Long durationS,
      BigDecimal bpm,
      String musicalKey,
      String audioUrl,
      String lrcUrl,
      String coverUrl,
      String interestTags,
      String source,
      String status,
      String pitchRefStatus,
      Instant createdAt,
      Instant updatedAt) {}

  /** 单句歌词行（PUT lrc 用；seq 由服务端按数组顺序重排）。 */
  public record LrcLine(
      @NotNull @Min(0) Long offsetMs, @Min(0) Long endOffsetMs, @NotBlank String lineText) {}

  public record LrcUpsert(@NotNull List<LrcLine> lines) {}

  public record LrcView(
      Integer seq, Long offsetMs, Long endOffsetMs, String lineText, String source) {}

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

  public record MaterialView(
      Long id,
      String title,
      Integer level,
      String audioUrl,
      Long durationS,
      String transcript,
      String interestTags,
      String source,
      String license,
      String status,
      Instant createdAt,
      Instant updatedAt) {}

  private final ScenarioRepository scenarios;
  private final SongRepository songs;
  private final LrcRepository lrcs;
  private final ListeningMaterialRepository materials;

  public ContentAdminController(
      ScenarioRepository scenarios,
      SongRepository songs,
      LrcRepository lrcs,
      ListeningMaterialRepository materials) {
    this.scenarios = scenarios;
    this.songs = songs;
    this.lrcs = lrcs;
    this.materials = materials;
  }

  // ---------------------------------------------------------------------------
  // 场景
  // ---------------------------------------------------------------------------

  @GetMapping("/scenarios")
  public Envelope<PageView<ScenarioView>> listScenarios(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "draft|published|archived") String status,
      @RequestParam(required = false) String sceneType) {
    Pageable pageable = PageRequest.of(page - 1, pageSize);
    Page<ScenarioEntity> rows = scenarios.search(status, sceneType, pageable);
    return Envelope.ok(PageView.of(rows.map(ContentAdminController::toView)));
  }

  @PostMapping("/scenarios")
  public Envelope<ScenarioView> createScenario(@Valid @RequestBody ScenarioUpsert body) {
    Instant now = Instant.now();
    ScenarioEntity e = new ScenarioEntity();
    e.setTitle(body.title());
    e.setSceneType(body.sceneType());
    e.setDifficulty(body.difficulty());
    e.setDescription(body.description());
    e.setSystemPrompt(body.systemPrompt());
    e.setOpeningLine(body.openingLine());
    e.setTargetCorpus(body.targetCorpus());
    e.setInterestTags(body.interestTags() == null ? "[]" : body.interestTags());
    e.setPromptVersion(body.promptVersion() == null ? 1 : body.promptVersion());
    e.setEstimatedTurns(body.estimatedTurns());
    e.setEstimatedMinutes(body.estimatedMinutes());
    e.setStatus(body.status() == null ? "draft" : body.status());
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return Envelope.ok(toView(scenarios.save(e)));
  }

  @GetMapping("/scenarios/{id}")
  public Envelope<ScenarioView> getScenario(@PathVariable Long id) {
    return Envelope.ok(toView(requireScenario(id)));
  }

  @PutMapping("/scenarios/{id}")
  public Envelope<ScenarioView> updateScenario(
      @PathVariable Long id, @Valid @RequestBody ScenarioUpsert body) {
    ScenarioEntity e = requireScenario(id);
    e.setTitle(body.title());
    e.setSceneType(body.sceneType());
    e.setDifficulty(body.difficulty());
    e.setDescription(body.description());
    e.setSystemPrompt(body.systemPrompt());
    e.setOpeningLine(body.openingLine());
    e.setTargetCorpus(body.targetCorpus());
    if (body.interestTags() != null) {
      e.setInterestTags(body.interestTags());
    }
    if (body.promptVersion() != null) {
      e.setPromptVersion(body.promptVersion());
    }
    e.setEstimatedTurns(body.estimatedTurns());
    e.setEstimatedMinutes(body.estimatedMinutes());
    if (body.status() != null) {
      e.setStatus(body.status());
    }
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(toView(scenarios.save(e)));
  }

  /** 归档（禁物理删除；Python 读侧按 status=published 过滤，自动不可见）。 */
  @DeleteMapping("/scenarios/{id}")
  public Envelope<ScenarioView> archiveScenario(@PathVariable Long id) {
    ScenarioEntity e = requireScenario(id);
    e.setStatus("archived");
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(toView(scenarios.save(e)));
  }

  // ---------------------------------------------------------------------------
  // 歌曲 + LRC
  // ---------------------------------------------------------------------------

  @GetMapping("/songs")
  public Envelope<PageView<SongView>> listSongs(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "draft|published|archived") String status) {
    Page<SongEntity> rows = songs.search(status, PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(ContentAdminController::toView)));
  }

  @PostMapping("/songs")
  public Envelope<SongView> createSong(@Valid @RequestBody SongUpsert body) {
    Instant now = Instant.now();
    SongEntity e = new SongEntity();
    e.setTitle(body.title());
    e.setArtist(body.artist());
    e.setLevel(body.level());
    e.setDurationS(body.durationS());
    e.setBpm(body.bpm());
    e.setMusicalKey(body.musicalKey());
    e.setAudioUrl(body.audioUrl());
    e.setLrcUrl(body.lrcUrl());
    e.setCoverUrl(body.coverUrl());
    e.setInterestTags(body.interestTags() == null ? "[]" : body.interestTags());
    e.setSource(body.source() == null ? "public_domain" : body.source());
    e.setStatus(body.status() == null ? "draft" : body.status());
    e.setPitchRefStatus(body.pitchRefStatus() == null ? "missing" : body.pitchRefStatus());
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return Envelope.ok(toView(songs.save(e)));
  }

  @GetMapping("/songs/{id}")
  public Envelope<SongView> getSong(@PathVariable Long id) {
    return Envelope.ok(toView(requireSong(id)));
  }

  @PutMapping("/songs/{id}")
  public Envelope<SongView> updateSong(@PathVariable Long id, @Valid @RequestBody SongUpsert body) {
    SongEntity e = requireSong(id);
    e.setTitle(body.title());
    e.setArtist(body.artist());
    e.setLevel(body.level());
    e.setDurationS(body.durationS());
    e.setBpm(body.bpm());
    e.setMusicalKey(body.musicalKey());
    e.setAudioUrl(body.audioUrl());
    e.setLrcUrl(body.lrcUrl());
    e.setCoverUrl(body.coverUrl());
    if (body.interestTags() != null) {
      e.setInterestTags(body.interestTags());
    }
    if (body.source() != null) {
      e.setSource(body.source());
    }
    if (body.status() != null) {
      e.setStatus(body.status());
    }
    if (body.pitchRefStatus() != null) {
      e.setPitchRefStatus(body.pitchRefStatus());
    }
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(toView(songs.save(e)));
  }

  @DeleteMapping("/songs/{id}")
  public Envelope<SongView> archiveSong(@PathVariable Long id) {
    SongEntity e = requireSong(id);
    e.setStatus("archived");
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(toView(songs.save(e)));
  }

  @GetMapping("/songs/{id}/lrc")
  public Envelope<List<LrcView>> getLrc(@PathVariable Long id) {
    requireSong(id);
    return Envelope.ok(
        lrcs.findBySongIdOrderBySeqAsc(id).stream().map(ContentAdminController::toView).toList());
  }

  /** 整首重写（docs/10 §4.3）：删旧插新 + seq 重排；song_pitch_refs 级联清，pitch_ref_status→missing。 */
  @PutMapping("/songs/{id}/lrc")
  @Transactional
  public Envelope<List<LrcView>> replaceLrc(
      @PathVariable Long id, @Valid @RequestBody LrcUpsert body) {
    SongEntity song = requireSong(id);
    lrcs.deleteBySongId(id);
    Instant now = Instant.now();
    List<LrcEntity> saved = new ArrayList<>();
    int seq = 1;
    for (LrcLine line : body.lines()) {
      LrcEntity e = new LrcEntity();
      e.setSongId(id);
      e.setSeq(seq++);
      e.setOffsetMs(line.offsetMs());
      e.setEndOffsetMs(line.endOffsetMs());
      e.setLineText(line.lineText());
      e.setSource(song.getSource()); // 与 songs.source 一致（docs/11 Q-B19）
      e.setCreatedAt(now);
      saved.add(lrcs.save(e));
    }
    // 触发 Python 离线重提取（docs/10 §3.2-2：ready → missing）
    if ("ready".equals(song.getPitchRefStatus())) {
      song.setPitchRefStatus("missing");
      song.setUpdatedAt(now);
      songs.save(song);
    }
    return Envelope.ok(saved.stream().map(ContentAdminController::toView).toList());
  }

  // ---------------------------------------------------------------------------
  // 听力素材
  // ---------------------------------------------------------------------------

  @GetMapping("/listening-materials")
  public Envelope<PageView<MaterialView>> listMaterials(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "draft|published|archived") String status) {
    Page<ListeningMaterialEntity> rows =
        materials.search(status, PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(ContentAdminController::toView)));
  }

  @PostMapping("/listening-materials")
  public Envelope<MaterialView> createMaterial(@Valid @RequestBody MaterialUpsert body) {
    Instant now = Instant.now();
    ListeningMaterialEntity e = new ListeningMaterialEntity();
    e.setTitle(body.title());
    e.setLevel(body.level());
    e.setAudioUrl(body.audioUrl());
    e.setDurationS(body.durationS());
    e.setTranscript(body.transcript());
    e.setInterestTags(body.interestTags() == null ? "[]" : body.interestTags());
    e.setSource(body.source());
    e.setLicense(body.license());
    e.setStatus(body.status() == null ? "draft" : body.status());
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return Envelope.ok(toView(materials.save(e)));
  }

  @GetMapping("/listening-materials/{id}")
  public Envelope<MaterialView> getMaterial(@PathVariable Long id) {
    return Envelope.ok(toView(requireMaterial(id)));
  }

  @PutMapping("/listening-materials/{id}")
  public Envelope<MaterialView> updateMaterial(
      @PathVariable Long id, @Valid @RequestBody MaterialUpsert body) {
    ListeningMaterialEntity e = requireMaterial(id);
    e.setTitle(body.title());
    e.setLevel(body.level());
    e.setAudioUrl(body.audioUrl());
    e.setDurationS(body.durationS());
    e.setTranscript(body.transcript());
    if (body.interestTags() != null) {
      e.setInterestTags(body.interestTags());
    }
    e.setSource(body.source());
    e.setLicense(body.license());
    if (body.status() != null) {
      e.setStatus(body.status());
    }
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(toView(materials.save(e)));
  }

  @DeleteMapping("/listening-materials/{id}")
  public Envelope<MaterialView> archiveMaterial(@PathVariable Long id) {
    ListeningMaterialEntity e = requireMaterial(id);
    e.setStatus("archived");
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(toView(materials.save(e)));
  }

  // ---------------------------------------------------------------------------
  // 工具
  // ---------------------------------------------------------------------------

  private ScenarioEntity requireScenario(Long id) {
    return scenarios
        .findById(id)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "scenario not found"));
  }

  private SongEntity requireSong(Long id) {
    return songs
        .findById(id)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "song not found"));
  }

  private ListeningMaterialEntity requireMaterial(Long id) {
    return materials
        .findById(id)
        .orElseThrow(
            () ->
                new ResponseStatusException(HttpStatus.NOT_FOUND, "listening material not found"));
  }

  private static ScenarioView toView(ScenarioEntity e) {
    return new ScenarioView(
        e.getId(),
        e.getTitle(),
        e.getSceneType(),
        e.getDifficulty(),
        e.getDescription(),
        e.getSystemPrompt(),
        e.getOpeningLine(),
        e.getTargetCorpus(),
        e.getInterestTags(),
        e.getPromptVersion(),
        e.getEstimatedTurns(),
        e.getEstimatedMinutes(),
        e.getStatus(),
        e.getCreatedAt(),
        e.getUpdatedAt());
  }

  private static SongView toView(SongEntity e) {
    return new SongView(
        e.getId(),
        e.getTitle(),
        e.getArtist(),
        e.getLevel(),
        e.getDurationS(),
        e.getBpm(),
        e.getMusicalKey(),
        e.getAudioUrl(),
        e.getLrcUrl(),
        e.getCoverUrl(),
        e.getInterestTags(),
        e.getSource(),
        e.getStatus(),
        e.getPitchRefStatus(),
        e.getCreatedAt(),
        e.getUpdatedAt());
  }

  private static LrcView toView(LrcEntity e) {
    return new LrcView(
        e.getSeq(), e.getOffsetMs(), e.getEndOffsetMs(), e.getLineText(), e.getSource());
  }

  private static MaterialView toView(ListeningMaterialEntity e) {
    return new MaterialView(
        e.getId(),
        e.getTitle(),
        e.getLevel(),
        e.getAudioUrl(),
        e.getDurationS(),
        e.getTranscript(),
        e.getInterestTags(),
        e.getSource(),
        e.getLicense(),
        e.getStatus(),
        e.getCreatedAt(),
        e.getUpdatedAt());
  }
}
