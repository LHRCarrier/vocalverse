package com.vocalverse.console.audit;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.common.dto.PageView;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.console.rbac.PermissionCatalog;
import com.vocalverse.console.rbac.RequireConsolePermission;
import java.time.Instant;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 审计日志读取（docs/50 §10.2 GET /audit-logs，需 {@code console:audit:read}）。
 *
 * <p><b>只读</b>：本控制器刻意不提供任何写/删端点 —— {@code admin_audit_logs} 是 append-only 的合规资产，
 * 允许"修正"审计就等于没有审计（docs/50 §5.3.7）。清理由保留期任务（365 天）在库外做。
 *
 * <p>同一份数据还以两条派生视图暴露：{@code GET /console/content/publish-events}（上架下架流水）。 派生而不是另建表，是 docs/50 §10.2
 * 的明确要求（{@code admin_audit_logs} 为唯一真源）。
 */
@RestController
@RequestMapping("/api/v1/console")
public class ConsoleAuditController {

  /** 时间窗上限 92 天（docs/50 §10.4 46007：时间窗过大 → data.suggestedStep 提示）。 */
  private static final long MAX_WINDOW_DAYS = 92;

  public record AuditLogView(
      Long id,
      Long adminUserId,
      String adminUsername,
      String action,
      String targetType,
      String targetId,
      String result,
      Integer errorCode,
      String summary,
      Object detail,
      String requestId,
      String ip,
      Instant createdAt) {}

  private final AdminAuditLogRepository logs;
  private final com.fasterxml.jackson.databind.ObjectMapper mapper;

  public ConsoleAuditController(
      AdminAuditLogRepository logs, com.fasterxml.jackson.databind.ObjectMapper mapper) {
    this.logs = logs;
    this.mapper = mapper;
  }

  @GetMapping("/audit-logs")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_AUDIT_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<AuditLogView>> list(
      @RequestParam(defaultValue = "1") int page,
      @RequestParam(name = "page_size", defaultValue = "20") int pageSize,
      @RequestParam(required = false) String action,
      @RequestParam(required = false) String actionPrefix,
      @RequestParam(required = false) String targetType,
      @RequestParam(required = false) Long adminUserId,
      @RequestParam(required = false) String result,
      @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
          Instant from,
      @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
          Instant to) {
    validateWindow(from, to);
    int size = Math.min(Math.max(pageSize, 1), 100);
    int pageIndex = Math.max(page - 1, 0);
    // action 精确优先：两者同时给出时忽略前缀（语义歧义不猜，见 Repository 注释）
    String exact = blankToNull(action);
    String prefix = exact == null ? blankToNull(actionPrefix) : null;
    Page<AdminAuditLogEntity> rows =
        logs.search(
            exact,
            prefix,
            blankToNull(targetType),
            adminUserId,
            blankToNull(result),
            from,
            to,
            PageRequest.of(pageIndex, size));
    return Envelope.ok(PageView.of(rows.map(this::toView)));
  }

  private AuditLogView toView(AdminAuditLogEntity e) {
    return new AuditLogView(
        e.getId(),
        e.getAdminUserId(),
        e.getAdminUsername(),
        e.getAction(),
        e.getTargetType(),
        e.getTargetId(),
        e.getResult(),
        e.getErrorCode(),
        e.getSummary(),
        e.getDetail() == null ? null : readJson(e.getDetail()),
        e.getRequestId(),
        e.getIp(),
        e.getCreatedAt());
  }

  private Object readJson(String raw) {
    try {
      return mapper.readTree(raw);
    } catch (Exception ex) {
      return raw;
    }
  }

  /** 时间窗校验（docs/50 §10.4 46007 举例即「时间窗过大」）。 */
  static void validateWindow(Instant from, Instant to) {
    if (from != null && to != null && from.isAfter(to)) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "from 不能晚于 to");
    }
    if (from != null && to != null && to.minusSeconds(MAX_WINDOW_DAYS * 86400).isAfter(from)) {
      throw ConsoleException.of(
          ConsoleErrorCodes.INVALID_PARAM,
          "时间窗过大（上限 " + MAX_WINDOW_DAYS + " 天）",
          Map.of("suggestedStep", "P1D"));
    }
  }

  private static String blankToNull(String s) {
    return s == null || s.isBlank() ? null : s;
  }
}
