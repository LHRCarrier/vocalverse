package com.vocalverse.console.moderation;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.common.dto.PageView;
import com.vocalverse.console.audit.AdminAuditLogEntity;
import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.auth.CurrentAdmin;
import com.vocalverse.console.rbac.PermissionCatalog;
import com.vocalverse.console.rbac.RequireConsolePermission;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 审核端点（docs/50 §10.2 + 状态机 §6.2）。
 *
 * <p>权限码：读走 {@code moderation:queue:read} / {@code moderation:report:read}， 写走 {@code
 * moderation:decide} / {@code moderation:report:handle}。
 */
@RestController
@RequestMapping("/api/v1/console/moderation")
public class ModerationController {

  public record CaseView(
      Long id,
      String targetType,
      Long targetId,
      String source,
      String reasonCode,
      Short priority,
      String status,
      String snippet,
      Object snapshot,
      Long reporterUserId,
      Long assigneeId,
      Long decidedBy,
      Instant decidedAt,
      String decisionNote,
      Instant createdAt,
      Instant updatedAt) {}

  public record CaseCreate(
      @NotNull @Pattern(regexp = "post|comment|media|direct_message") String targetType,
      @NotNull Long targetId,
      @Pattern(regexp = "auto|report|manual") String source,
      @NotNull String reasonCode,
      @Min(1) @Max(3) Short priority,
      Long assigneeId) {}

  /**
   * 指派 / 取消指派请求体。
   *
   * <p>{@code assigneeId} **可空**：控制台有「取消认领」，其请求体是 {@code {"assigneeId": null}}。 早期版本写
   * {@code @NotNull} 会让「取消认领」直接 400 —— 那是把一个正常操作做成了不可达。 {@code null} 的语义 = 清空 {@code
   * assignee_id}（回到未认领），并且**同样落一行审计** （「谁取消了谁的认领」与「谁认领了」同等重要，召回器需要能追）。
   */
  public record CaseAssign(Long assigneeId, @Size(max = 500) String note) {}

  public record CaseDecision(
      @NotNull @Pattern(regexp = "approve|hide|delete|reject|escalate") String decision,
      String reasonCode,
      @Size(max = 500) String note) {}

  public record ReportView(
      Long id,
      Long reporterUserId,
      String targetType,
      Long targetId,
      String reasonCode,
      String detail,
      String status,
      Long caseId,
      Long handledBy,
      Instant handledAt,
      Instant createdAt) {}

  /**
   * 处理举报请求体。
   *
   * <p><b>线格式以 docs/50 §10.2 为准：{@code {decision, note?}}</b>（{@code decision ∈
   * accept|reject|duplicate}）。控制台前端按这个形状发请求。
   *
   * <p>{@code action} 作为**兼容别名**保留：早期实现用 {@code action} 作字段名，Python 侧同一语义的 端点（docs/50 §10.3 同样是
   * handle）也用 {@code action}。两者同时提供时以 {@code decision} 优先， 避免出现「两个字段都传且不一致」时的歧义（此时按 {@code
   * decision} 执行并**不报错** —— 报错会把一个前端迁移期的无害请求变成故障）。
   *
   * <p>{@code caseId} 可选：只对 {@code duplicate} 有意义（指向被视为「原始」的举报所属审单）； {@code accept}
   * 一律由服务端创建/复用审单并回填，不接受调用方指定（防止把举报挂到不相干的单上）。
   */
  public record ReportHandle(
      @Pattern(regexp = "accept|reject|duplicate") String decision,
      @Pattern(regexp = "accept|reject|duplicate") String action,
      Long caseId,
      @Size(max = 500) String note) {

    /** 实际生效的动作（{@code decision} 优先，回退 {@code action}）。 */
    public String effective() {
      return decision != null && !decision.isBlank() ? decision : action;
    }
  }

  private final ModerationService service;
  private final com.fasterxml.jackson.databind.ObjectMapper mapper;

  public ModerationController(
      ModerationService service, com.fasterxml.jackson.databind.ObjectMapper mapper) {
    this.service = service;
    this.mapper = mapper;
  }

  // ------------------------------------------------------------------ 工单

  @GetMapping("/cases")
  @RequireConsolePermission(PermissionCatalog.MODERATION_QUEUE_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<CaseView>> listCases(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false)
          @Pattern(regexp = "pending|approved|rejected|escalated|withdrawn")
          String status,
      @RequestParam(required = false) @Pattern(regexp = "post|comment|media|direct_message")
          String targetType,
      @RequestParam(required = false) @Min(1) @Max(3) Short priority,
      @RequestParam(required = false) Long assigneeId) {
    Page<ModerationCaseEntity> rows =
        service.list(status, targetType, priority, assigneeId, page, pageSize);
    return Envelope.ok(PageView.of(rows.map(this::toView)));
  }

  @PostMapping("/cases")
  @RequireConsolePermission(PermissionCatalog.MODERATION_DECIDE)
  public Envelope<CaseView> createCase(
      @CurrentAdmin ConsolePrincipal me, @Valid @RequestBody CaseCreate body) {
    ModerationCaseEntity e =
        service.create(
            me,
            new ModerationService.CreateRequest(
                body.targetType(),
                body.targetId(),
                body.source(),
                body.reasonCode(),
                body.priority(),
                body.assigneeId()));
    return Envelope.ok(toView(e));
  }

  /** 详情：含快照（target 现状）+ 历史审计（docs/50 §10.2「含快照 + 历史审计」）。 */
  @GetMapping("/cases/{id}")
  @RequireConsolePermission(PermissionCatalog.MODERATION_QUEUE_READ)
  @Transactional(readOnly = true)
  public Envelope<Map<String, Object>> getCase(@PathVariable Long id) {
    ModerationCaseEntity c = service.require(id);
    Map<String, Object> out = new LinkedHashMap<>();
    out.put("case", toView(c));
    out.putAll(service.describe(c));
    List<Map<String, Object>> history = new ArrayList<>();
    for (AdminAuditLogEntity a : service.history(id)) {
      Map<String, Object> h = new LinkedHashMap<>();
      h.put("id", a.getId());
      h.put("action", a.getAction());
      h.put("adminUserId", a.getAdminUserId());
      h.put("adminUsername", a.getAdminUsername());
      h.put("result", a.getResult());
      h.put("summary", a.getSummary());
      h.put("detail", a.getDetail() == null ? null : readJson(a.getDetail()));
      h.put("createdAt", a.getCreatedAt());
      history.add(h);
    }
    out.put("history", history);
    return Envelope.ok(out);
  }

  @PostMapping("/cases/{id}/assign")
  @RequireConsolePermission(PermissionCatalog.MODERATION_DECIDE)
  public Envelope<CaseView> assign(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody CaseAssign body) {
    return Envelope.ok(toView(service.assign(me, id, body.assigneeId(), body.note())));
  }

  /** 决定（docs/50 §6.2）：竞态由条件 UPDATE 兜住，第二个并发请求得 46010。 */
  @PostMapping("/cases/{id}/decision")
  @RequireConsolePermission(PermissionCatalog.MODERATION_DECIDE)
  public Envelope<CaseView> decide(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody CaseDecision body) {
    return Envelope.ok(
        toView(service.decide(me, id, body.decision(), body.reasonCode(), body.note())));
  }

  // ------------------------------------------------------------------ 举报

  @GetMapping("/reports")
  @RequireConsolePermission(PermissionCatalog.MODERATION_REPORT_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<ReportView>> listReports(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "pending|accepted|rejected|duplicate")
          String status,
      @RequestParam(required = false) @Pattern(regexp = "post|comment|media|direct_message")
          String targetType) {
    return Envelope.ok(
        PageView.of(service.listReports(status, targetType, page, pageSize).map(this::toView)));
  }

  @PostMapping("/reports/{id}/handle")
  @RequireConsolePermission(PermissionCatalog.MODERATION_REPORT_HANDLE)
  public Envelope<ReportView> handleReport(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody ReportHandle body) {
    return Envelope.ok(
        toView(
            service.handleReport(
                me,
                id,
                new ModerationService.HandleRequest(
                    body.effective(), body.caseId(), body.note()))));
  }

  /**
   * 契约自证端点（docs/50 §5.3.7/§5.3.8）：回传后端**实际会写**的审计动作名与原因码。
   *
   * <p>为什么值得开一个只读端点：控制台前端把这些字面量写死在过滤条件与下拉框里， 一旦后端改字面量，前端会静默筛不到（页面空白但不报错）。有了它，
   * 前端可以（也应该）用一个断言测试对比自己的常量表；对不齐时是**测试红**而不是**线上空白**。
   *
   * <p>权限用 {@code moderation:queue:read}（审核域的读权限，不需要新增权限码）。
   */
  @GetMapping("/contract")
  @RequireConsolePermission(PermissionCatalog.MODERATION_QUEUE_READ)
  public Envelope<Map<String, Object>> contract() {
    Map<String, Object> out = new java.util.LinkedHashMap<>();
    out.put("auditActions", ModerationService.AUDIT_ACTIONS);
    out.put("reasonCodes", ModerationService.REASON_CODES);
    out.put(
        "decisions",
        java.util.Arrays.stream(ModerationService.Decision.values())
            .map(ModerationService.Decision::wire)
            .toList());
    out.put("reportActions", java.util.List.of("accept", "reject", "duplicate"));
    out.put(
        "caseStatuses",
        java.util.List.of("pending", "approved", "rejected", "escalated", "withdrawn"));
    out.put("reportStatuses", java.util.List.of("pending", "accepted", "rejected", "duplicate"));
    out.put("targetTypes", java.util.List.of("post", "comment", "media", "direct_message"));
    out.put("javaWritableTargetTypes", java.util.List.of("post", "comment"));
    return Envelope.ok(out);
  }

  @GetMapping("/stats")
  @RequireConsolePermission(PermissionCatalog.MODERATION_QUEUE_READ)
  @Transactional(readOnly = true)
  public Envelope<Map<String, Object>> stats(
      @RequestParam(defaultValue = "30") @Min(1) @Max(90) int days) {
    return Envelope.ok(service.stats(days));
  }

  // ------------------------------------------------------------------ 转换

  private CaseView toView(ModerationCaseEntity c) {
    return new CaseView(
        c.getId(),
        c.getTargetType(),
        c.getTargetId(),
        c.getSource(),
        c.getReasonCode(),
        c.getPriority(),
        c.getStatus(),
        c.getSnippet(),
        c.getSnapshot() == null ? null : readJson(c.getSnapshot()),
        c.getReporterUserId(),
        c.getAssigneeId(),
        c.getDecidedBy(),
        c.getDecidedAt(),
        c.getDecisionNote(),
        c.getCreatedAt(),
        c.getUpdatedAt());
  }

  private ReportView toView(ModerationReportEntity r) {
    return new ReportView(
        r.getId(),
        r.getReporterUserId(),
        r.getTargetType(),
        r.getTargetId(),
        r.getReasonCode(),
        r.getDetail(),
        r.getStatus(),
        r.getCaseId(),
        r.getHandledBy(),
        r.getHandledAt(),
        r.getCreatedAt());
  }

  private Object readJson(String raw) {
    try {
      return mapper.readTree(raw);
    } catch (Exception e) {
      return raw;
    }
  }
}
