package com.vocalverse.console.content;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.common.dto.PageView;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.console.audit.AdminAuditLogEntity;
import com.vocalverse.console.audit.AdminAuditLogRepository;
import com.vocalverse.console.audit.AuditService;
import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.auth.CurrentAdmin;
import com.vocalverse.console.rbac.PermissionCatalog;
import com.vocalverse.console.rbac.RequireConsolePermission;
import com.vocalverse.content.ListeningMaterialEntity;
import com.vocalverse.content.ListeningMaterialRepository;
import com.vocalverse.content.PlacementQuestionEntity;
import com.vocalverse.content.PlacementQuestionRepository;
import com.vocalverse.content.ScenarioEntity;
import com.vocalverse.content.ScenarioRepository;
import com.vocalverse.content.SongEntity;
import com.vocalverse.content.SongRepository;
import com.vocalverse.ticket.TicketEntity;
import com.vocalverse.ticket.TicketRepository;
import com.vocalverse.ticket.TicketWorkflowService;
import com.vocalverse.ticket.dto.TicketView;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 运营域端点（docs/50 §10.2「/content/*」段）。
 *
 * <h2>与既有 {@code /api/v1/admin/**} 的关系</h2>
 *
 * <p>本控制器**只读取**既有仓库、**只新增**上架/下架这一条写路径（docs/50 §6.1 的 status 迁移）。 歌曲/听力/场景的 CRUD 仍走既有 {@code
 * ContentAdminController}（ADMIN 角色守门），一行未改 —— 控制台不复制 CRUD，避免「两处都能改内容元数据、规则不同」的分叉。
 *
 * <p><b>工单</b>：既有 {@code AdminTicketController} 覆盖了状态流转，所以这里**不重写状态机**， 而是调用抽出来的 {@link
 * TicketWorkflowService}（两处共用同一张转义表与同一段认领逻辑）。 唯一差别是 {@code admin_id} 的取值来源：既有端点是 App 的 {@code
 * users.id}，控制台是 {@code admin_users.id} —— 两套身份本就是两张表（docs/50 §4.1），工单已认领时不再覆盖该列，
 * 所以不会互相污染。这一点已登记为上报的偏差项。
 *
 * <p><b>书籍/媒体</b>：docs/50 §3.2 明确归 Python，Java 侧不提供端点（只登记权限码目录）。 {@code GET
 * /content/publish-events} 从 {@code admin_audit_logs} 派生（docs/50 §10.2 明确要求）。
 */
@RestController
@RequestMapping("/api/v1/console/content")
public class ConsoleContentController {

  public record PublishRequest(@Pattern(regexp = "draft|published|archived") String status) {}

  public record PublishView(
      String domain, Long id, String prevStatus, String nextStatus, Instant publishedAt) {}

  public record SongRow(
      Long id,
      String title,
      String artist,
      Integer level,
      String audioUrl,
      String status,
      String pitchRefStatus,
      Instant updatedAt) {}

  public record MaterialRow(
      Long id,
      String title,
      Integer level,
      String audioUrl,
      Boolean hasTranscript,
      String status,
      Instant updatedAt) {}

  public record ScenarioRow(
      Long id,
      String title,
      String sceneType,
      Integer difficulty,
      String status,
      int corpusItemCount,
      Instant updatedAt) {}

  public record QuestionRow(
      Long id,
      Integer examRevision,
      Integer itemIndex,
      String kind,
      String prompt,
      String status,
      Instant updatedAt) {}

  private final SongRepository songs;
  private final ListeningMaterialRepository materials;
  private final ScenarioRepository scenarios;
  private final PlacementQuestionRepository questions;
  private final TicketRepository tickets;
  private final TicketWorkflowService ticketWorkflow;
  private final PublishService publishService;
  private final AdminAuditLogRepository auditLogs;
  private final AuditService audit;

  public ConsoleContentController(
      SongRepository songs,
      ListeningMaterialRepository materials,
      ScenarioRepository scenarios,
      PlacementQuestionRepository questions,
      TicketRepository tickets,
      TicketWorkflowService ticketWorkflow,
      PublishService publishService,
      AdminAuditLogRepository auditLogs,
      AuditService audit) {
    this.songs = songs;
    this.materials = materials;
    this.scenarios = scenarios;
    this.questions = questions;
    this.tickets = tickets;
    this.ticketWorkflow = ticketWorkflow;
    this.publishService = publishService;
    this.auditLogs = auditLogs;
    this.audit = audit;
  }

  // ------------------------------------------------------------------ 歌曲

  @GetMapping("/songs")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<SongRow>> listSongs(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "draft|published|archived") String status) {
    Page<SongEntity> rows = songs.search(status, PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(ConsoleContentController::toRow)));
  }

  @PostMapping("/songs/{id}/publish")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_PUBLISH)
  @Transactional
  public Envelope<PublishView> publishSong(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody PublishRequest body) {
    return Envelope.ok(applyPublish(me, PublishService.DOMAIN_SONG, id, body.status()));
  }

  // ------------------------------------------------------------------ 听力素材

  @GetMapping("/listening-materials")
  @RequireConsolePermission(PermissionCatalog.CONTENT_LISTENING_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<MaterialRow>> listMaterials(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "draft|published|archived") String status) {
    Page<ListeningMaterialEntity> rows =
        materials.search(status, PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(ConsoleContentController::toRow)));
  }

  @PostMapping("/listening-materials/{id}/publish")
  @RequireConsolePermission(PermissionCatalog.CONTENT_LISTENING_PUBLISH)
  @Transactional
  public Envelope<PublishView> publishMaterial(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody PublishRequest body) {
    return Envelope.ok(applyPublish(me, PublishService.DOMAIN_LISTENING, id, body.status()));
  }

  // ------------------------------------------------------------------ 场景

  @GetMapping("/scenarios")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SCENARIO_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<ScenarioRow>> listScenarios(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "draft|published|archived") String status,
      @RequestParam(required = false) String sceneType) {
    Page<ScenarioEntity> rows =
        scenarios.search(status, sceneType, PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(ConsoleContentController::toRow)));
  }

  @PostMapping("/scenarios/{id}/publish")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SCENARIO_PUBLISH)
  @Transactional
  public Envelope<PublishView> publishScenario(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody PublishRequest body) {
    return Envelope.ok(applyPublish(me, PublishService.DOMAIN_SCENARIO, id, body.status()));
  }

  // ------------------------------------------------------------------ 题库（只读：题库无 draft，故无
  // publish，docs/50 §4.2）

  @GetMapping("/questions")
  @RequireConsolePermission(PermissionCatalog.CONTENT_QUESTION_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<QuestionRow>> listQuestions(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) Integer examRevision,
      @RequestParam(required = false) @Pattern(regexp = "published|archived") String status) {
    // 题库按 examRevision 版本化（docs/10 §3.2：改题=新版本），默认取最新版本
    Integer revision = examRevision != null ? examRevision : questions.maxExamRevision();
    List<PlacementQuestionEntity> all =
        questions.findByExamRevisionOrderByItemIndexAsc(revision == null ? 0 : revision);
    List<QuestionRow> filtered =
        all.stream()
            .filter(q -> status == null || status.equals(q.getStatus()))
            .map(ConsoleContentController::toRow)
            .toList();
    int size = Math.min(Math.max(pageSize, 1), 100);
    int from = Math.min(Math.max(page - 1, 0) * size, filtered.size());
    int to = Math.min(from + size, filtered.size());
    return Envelope.ok(
        new PageView<>(filtered.subList(from, to), filtered.size(), Math.max(page, 1), size));
  }

  // ------------------------------------------------------------------ 工单（控制台是**唯一**工单面）

  /**
   * 工单列表（docs/50 §10.2）。
   *
   * <p>支持 {@code kind} 过滤：用户点名的三类工单是 反馈 / 报错 / **内容纠误** （{@code feedback|bug|content_correction}，见
   * {@code TicketEntity} 注释）， 运营处理内容纠误时按 {@code kind} 筛是最主要的用法 —— 旧管理端的列表只支持 {@code status}， 控制台补上
   * {@code kind} 属于「退役旧面后不能丢能力」的补齐（旧面本来也没有这个过滤，不是回退）。
   */
  @GetMapping("/tickets")
  @RequireConsolePermission(PermissionCatalog.CONTENT_TICKET_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<TicketView>> listTickets(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "open|processing|resolved|closed")
          String status,
      @RequestParam(required = false) @Pattern(regexp = "feedback|bug|content_correction")
          String kind) {
    Page<TicketEntity> rows = tickets.search(status, kind, PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(TicketView::of)));
  }

  /** 工单详情。 */
  @GetMapping("/tickets/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_TICKET_READ)
  @Transactional(readOnly = true)
  public Envelope<TicketView> getTicket(@PathVariable Long id) {
    return Envelope.ok(
        TicketView.of(
            tickets
                .findById(id)
                .orElseThrow(
                    () -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "工单不存在"))));
  }

  /**
   * 工单更新请求体（与已退役的 {@code AdminTicketController.TicketPatch} **逐字同形**： {@code {status?,
   * adminReply?}}）。
   *
   * <p>刻意保持同形：控制台前端按这个形状发请求，且「状态流转 + 回复用户」必须是一次请求 —— 拆成两个端点会让「改了状态但没回复」成为可能，而那正是工单处理最常见的半成品状态。
   */
  public record TicketPatch(
      @Pattern(regexp = "open|processing|resolved|closed") String status,
      @Size(max = 2000) String adminReply) {}

  /**
   * 工单状态流转 + 回复（**PATCH**，controls/admin tickets 的替代面）。
   *
   * <p>状态机权威仍是 {@link TicketWorkflowService}（前向流转、禁回退、closed 终态）， 本方法只负责「换身份来源 + 落审计」，不复制任何转换规则 ——
   * 删除旧管理端后本端点是**全仓唯一**的工单写路径。
   *
   * <h2>admin_id 的身份语义（必须写清楚，否则后来者会做错 join）</h2>
   *
   * <p>{@code tickets.admin_id} **没有外键约束**，历史上存的是 App 侧 {@code users.id} （旧 {@code
   * AdminTicketController} 用 {@code @RequestAttribute("userId")}，即登录 App 的管理员用户）。 控制台是独立身份（{@code
   * admin_users}，与 {@code users} 无外键、无字段共享，docs/50 §4.1）， 所以本端点写入的是 **{@code
   * admin_users.id}**。因此该列现在是**混合语义**：
   *
   * <ul>
   *   <li>旧的、由已退役端点写过的行 → {@code users.id}；
   *   <li>新写入的行（本端点，即退役后的唯一写路径）→ {@code admin_users.id}；
   *   <li>「是谁处理的」的**权威记录**始终是 {@code admin_audit_logs} （{@code admin_user_id} + {@code
   *       admin_username} 快照 + {@code request_id}）， {@code admin_id} 只作展示用。
   * </ul>
   *
   * <p><b>为什么不改列语义/加列</b>：那是一次用户域+#{@code tickets} 的 DDL 变更（新增判别列或改注释），
   * 属迁移范围、不在本模块；且退役后旧写入方已不存在，继续往同一列写是**单调**的 （混合只发生在历史数据里，不会再产生新的旧语义行）。已作为已知缺口上报。
   */
  @PatchMapping("/tickets/{id}")
  @RequireConsolePermission(PermissionCatalog.CONTENT_TICKET_WRITE)
  @Transactional
  public Envelope<TicketView> patchTicket(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody TicketPatch body) {
    TicketEntity before =
        tickets
            .findById(id)
            .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "工单不存在"));
    String prevStatus = before.getStatus();
    Long prevAdminId = before.getAdminId();

    TicketEntity updated =
        ticketWorkflow.update(id, me.adminUserId(), body.status(), body.adminReply());

    audit.record(
        me,
        "content.ticket.update",
        "ticket",
        String.valueOf(id),
        "处理工单：" + prevStatus + " → " + updated.getStatus(),
        detail(
            "prevStatus", prevStatus,
            "nextStatus", updated.getStatus(),
            // 只记「是否写了回复」，**不记回复正文**（可能含用户隐私内容，且 detail 是长期留存）
            "note", body.adminReply() == null ? null : "(已填写处理回复)",
            "before", prevAdminId == null ? null : String.valueOf(prevAdminId),
            "after", updated.getAdminId() == null ? null : String.valueOf(updated.getAdminId())));
    return Envelope.ok(TicketView.of(updated));
  }

  // ------------------------------------------------------------------ 上架流水（审计派生）

  @GetMapping("/publish-events")
  @RequireConsolePermission(PermissionCatalog.CONTENT_SONG_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<Map<String, Object>>> publishEvents(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false)
          @Pattern(regexp = "song|listening_material|scenario|book|chapter")
          String targetType) {
    Page<AdminAuditLogEntity> rows =
        auditLogs.publishEvents(
            targetType == null || targetType.isBlank() ? null : targetType,
            null,
            null,
            PageRequest.of(page - 1, pageSize));
    List<Map<String, Object>> items = new java.util.ArrayList<>();
    for (AdminAuditLogEntity e : rows.getContent()) {
      Map<String, Object> m = new LinkedHashMap<>();
      m.put("id", e.getId());
      m.put("action", e.getAction());
      m.put("targetType", e.getTargetType());
      m.put("targetId", e.getTargetId());
      m.put("operator", e.getAdminUsername());
      m.put("adminUserId", e.getAdminUserId());
      m.put("summary", e.getSummary());
      m.put("detail", e.getDetail());
      m.put("createdAt", e.getCreatedAt());
      items.add(m);
    }
    return Envelope.ok(new PageView<>(items, rows.getTotalElements(), page, pageSize));
  }

  // ------------------------------------------------------------------ 内部

  private PublishView applyPublish(ConsolePrincipal me, String domain, Long id, String status) {
    PublishService.PublishResult r = publishService.publish(domain, id, status);
    Instant now = Instant.now();
    audit.record(
        me,
        "content." + domain + ".publish",
        targetTypeOf(domain),
        String.valueOf(id),
        "内容上下架：" + domain + "#" + id + " " + r.prevStatus() + " → " + r.nextStatus(),
        detail(
            "prevStatus", r.prevStatus(),
            "nextStatus", r.nextStatus(),
            "status", r.nextStatus(),
            "publishedAt", now.toString()));
    return new PublishView(domain, id, r.prevStatus(), r.nextStatus(), now);
  }

  private static String targetTypeOf(String domain) {
    return switch (domain) {
      case PublishService.DOMAIN_SONG -> "song";
      case PublishService.DOMAIN_LISTENING -> "listening_material";
      case PublishService.DOMAIN_SCENARIO -> "scenario";
      default -> domain;
    };
  }

  private static SongRow toRow(SongEntity e) {
    return new SongRow(
        e.getId(),
        e.getTitle(),
        e.getArtist(),
        e.getLevel(),
        e.getAudioUrl(),
        e.getStatus(),
        e.getPitchRefStatus(),
        e.getUpdatedAt());
  }

  private static MaterialRow toRow(ListeningMaterialEntity e) {
    return new MaterialRow(
        e.getId(),
        e.getTitle(),
        e.getLevel(),
        e.getAudioUrl(),
        e.getTranscript() != null && !e.getTranscript().isBlank(),
        e.getStatus(),
        e.getUpdatedAt());
  }

  private static ScenarioRow toRow(ScenarioEntity e) {
    return new ScenarioRow(
        e.getId(),
        e.getTitle(),
        e.getSceneType(),
        e.getDifficulty(),
        e.getStatus(),
        PublishService.countCorpusItems(e.getTargetCorpus()),
        e.getUpdatedAt());
  }

  private static QuestionRow toRow(PlacementQuestionEntity e) {
    return new QuestionRow(
        e.getId(),
        e.getExamRevision(),
        e.getItemIndex(),
        e.getKind(),
        e.getPrompt(),
        e.getStatus(),
        e.getUpdatedAt());
  }

  private static Map<String, Object> detail(Object... kv) {
    Map<String, Object> m = new LinkedHashMap<>();
    for (int i = 0; i + 1 < kv.length; i += 2) {
      m.put(String.valueOf(kv[i]), kv[i + 1]);
    }
    return m.isEmpty() ? null : m;
  }
}
