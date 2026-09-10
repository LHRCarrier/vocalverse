package com.vocalverse.console.audit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.console.auth.ConsolePrincipal;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 审计写入（docs/50 §5.3.7 / §9.3）。{@code admin_audit_logs} 是**唯一审计流**，append-only。
 *
 * <p>三条纪律：
 *
 * <ol>
 *   <li><b>与业务写同事务</b>：所有入口都是 {@code Propagation.MANDATORY} —— 调用方必须已在事务中。 这是刻意的：若用 {@code
 *       REQUIRES_NEW}，业务回滚后审计行还在（「改了但没留痕」的反面：「没改成却有痕」， 审计会变成一本编造的历史）。{@code MANDATORY}
 *       让「忘了开事务就写审计」当场炸掉，而不是悄悄写一条 自动提交的孤儿行。<b>本类不存在任何 REQUIRES_NEW 路径</b>；
 *   <li><b>{@code detail} 过字段白名单</b>（{@link AuditFieldAllowlist}）：白名单外的键静默丢弃并累加 {@link
 *       #droppedDetailKeys()}（对应 docs/50 §9.4 的 {@code audit_detail_dropped_total} 计数器）。
 *       口令/令牌类键另有单独计数，便于发现「有人试图把机密写进审计」；
 *   <li><b>不吞异常</b>：插入失败必须让整个业务事务回滚（docs/50 §9.3：宁可写不成功，不可无痕写成功）。
 * </ol>
 *
 * <h2>没有业务事务的审计去哪了</h2>
 *
 * <p>「登录成功」「越权被拒」这类事件没有可依附的业务事务，且**不应**被任何业务回滚带走。 它们走 {@link IndependentAuditWriter} ——
 * 一个独立的、自开事务的写入器，刻意与本类分开： 混在一起就只能用 {@code REQUIRES_NEW} 分支，而那会重新打开「审计落在业务事务之外」的口子 （见 {@link
 * AuditAspect} 关于 order 的说明）。
 */
@Service
public class AuditService {

  private static final Logger log = LoggerFactory.getLogger(AuditService.class);

  private final AdminAuditLogRepository logs;
  private final ObjectMapper mapper;

  /** {@code audit_detail_dropped_total}：白名单外被丢弃的键数。 */
  private final AtomicLong droppedDetailKeys = new AtomicLong();

  /** 其中「看起来像机密」的键数（password/token/secret/…）。 */
  private final AtomicLong droppedSecretKeys = new AtomicLong();

  public AuditService(AdminAuditLogRepository logs, ObjectMapper mapper) {
    this.logs = logs;
    this.mapper = mapper;
  }

  public long droppedDetailKeys() {
    return droppedDetailKeys.get();
  }

  public long droppedSecretKeys() {
    return droppedSecretKeys.get();
  }

  // ------------------------------------------------------------------ 对外入口

  /** 记录一次成功的管理端写操作（**必须在调用方事务内**）。 */
  @Transactional(propagation = Propagation.MANDATORY)
  public void record(
      ConsolePrincipal principal,
      String action,
      String targetType,
      String targetId,
      String summary,
      Map<String, Object> detail) {
    write(
        principal == null ? null : principal.adminUserId(),
        principal == null ? null : principal.username(),
        action,
        targetType,
        targetId,
        AdminAuditLogEntity.RESULT_OK,
        null,
        summary,
        detail,
        ConsoleRequestContext.clientIp());
  }

  /** 记录一次被拒/失败的操作（同事务；{@code errorCode} 为 46xxx）。 */
  @Transactional(propagation = Propagation.MANDATORY)
  public void recordFailed(
      ConsolePrincipal principal,
      String action,
      String targetType,
      String targetId,
      String result,
      Integer errorCode,
      String summary,
      Map<String, Object> detail) {
    write(
        principal == null ? null : principal.adminUserId(),
        principal == null ? null : principal.username(),
        action,
        targetType,
        targetId,
        result,
        errorCode,
        summary,
        detail,
        ConsoleRequestContext.clientIp());
  }

  /** 记录「无权限被拒」（{@code result=denied}，docs/50 §5.3.7 的 result 枚举之一）。 */
  @Transactional(propagation = Propagation.MANDATORY)
  public void recordDenied(
      ConsolePrincipal principal,
      String action,
      String targetType,
      String targetId,
      int errorCode,
      String summary) {
    write(
        principal == null ? null : principal.adminUserId(),
        principal == null ? null : principal.username(),
        action,
        targetType,
        targetId,
        AdminAuditLogEntity.RESULT_DENIED,
        errorCode,
        summary,
        null,
        ConsoleRequestContext.clientIp());
  }

  /**
   * 供 {@link IndependentAuditWriter}（无业务事务的审计）复用的底层写入。
   *
   * <p>包内可见而非 public：外部只应通过 {@link #record} / {@link #recordFailed} / {@link #recordDenied} 三个
   * MANDATORY 入口写审计，或在确实没有事务时用 {@code IndependentAuditWriter}。 直接暴露无事务保护的 write() 会让人绕过整套不变量。
   *
   * <p><b>{@code MANDATORY} 在这条路径上也是必须的</b>：{@link IndependentAuditWriter} 的 {@code REQUIRES_NEW}
   * 提供了事务，这里的 MANDATORY 会**加入**它；而如果有人绕过 writer 直接调用， MANDATORY
   * 会当场报错而不是静默写入。两条入口用同一个约束，就没有「某一条路径忘了事务」的口子。
   */
  @Transactional(propagation = Propagation.MANDATORY)
  void write(
      Long adminUserId,
      String adminUsername,
      String action,
      String targetType,
      String targetId,
      String result,
      Integer errorCode,
      String summary,
      Map<String, Object> detail,
      String ip) {
    AdminAuditLogEntity e = new AdminAuditLogEntity();
    e.setAdminUserId(adminUserId);
    // admin_username 是快照（NOT NULL）：系统路径（登录失败等）拿不到用户名时用 "-" 占位，
    // 不写空串 —— 空串在报表里与「用户名未知」无法区分。
    e.setAdminUsername(
        adminUsername == null || adminUsername.isBlank() ? "-" : truncate(adminUsername, 32));
    e.setAction(truncate(action, 64));
    e.setTargetType(targetType == null ? null : truncate(targetType, 32));
    e.setTargetId(targetId == null ? null : truncate(targetId, 64));
    e.setResult(result);
    e.setErrorCode(errorCode);
    e.setSummary(truncate(summary == null ? action : summary, 255));
    e.setDetail(serialize(filtered(detail)));
    e.setRequestId(truncateOrNull(ConsoleRequestContext.requestId(), 64));
    e.setIp(truncateOrNull(ip, 45));
    e.setCreatedAt(Instant.now());
    logs.save(e);
  }

  /** 白名单过滤；返回 null 表示「过滤后为空 → 不写 detail」（避免写一堆空对象噪音行）。 */
  Map<String, Object> filtered(Map<String, Object> detail) {
    if (detail == null || detail.isEmpty()) {
      return null;
    }
    Map<String, Object> out = new LinkedHashMap<>();
    long dropped = 0;
    long droppedSecret = 0;
    for (Map.Entry<String, Object> e : detail.entrySet()) {
      if (AuditFieldAllowlist.isAllowed(e.getKey())) {
        out.put(e.getKey(), e.getValue());
      } else {
        dropped++;
        if (AuditFieldAllowlist.looksSecret(e.getKey())) {
          droppedSecret++;
        }
      }
    }
    if (dropped > 0) {
      droppedDetailKeys.addAndGet(dropped);
      if (droppedSecret > 0) {
        droppedSecretKeys.addAndGet(droppedSecret);
        log.debug("审计 detail 丢弃 {} 个白名单外键（其中 {} 个疑似机密）", dropped, droppedSecret);
      }
    }
    return out.isEmpty() ? null : out;
  }

  private String serialize(Map<String, Object> detail) {
    if (detail == null || detail.isEmpty()) {
      return null;
    }
    try {
      return mapper.writeValueAsString(detail);
    } catch (Exception ex) {
      // detail 序列化失败不能让业务事务失败：审计主体（action/target/result/summary）已够用，
      // 丢的只是附加上下文。这里显式记录而不是静默。
      log.warn("审计 detail 序列化失败，已置空：{}", ex.getMessage());
      return null;
    }
  }

  private static String truncate(String s, int max) {
    if (s == null) {
      return null;
    }
    return s.length() <= max ? s : s.substring(0, max);
  }

  private static String truncateOrNull(String s, int max) {
    if (s == null || s.isBlank()) {
      return null;
    }
    return truncate(s, max);
  }
}
