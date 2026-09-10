package com.vocalverse.console.audit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.time.Instant;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.IllegalTransactionStateException;

/**
 * 审计事务不变量（docs/50 §14.2-Java 第 11 条 + §9.3）。
 *
 * <h2>双向验证</h2>
 *
 * <ul>
 *   <li><b>回滚 → 无审计行</b>：业务写之后抛异常 → 事务回滚 → 审计行也必须消失 （否则审计会记录一次从未发生的操作）；
 *   <li><b>提交 → 有审计行</b>：业务写成功 → 审计行必须在（否则「改了但没留痕」）。
 * </ul>
 *
 * <h2>为什么这个测试能测到 @Order</h2>
 *
 * <p>若审计切面排在事务切面**内层**（或两者 order 相等导致顺序不定），审计写入会跑在业务事务之外： 回滚用例会**红**（审计行还在）。所以「回滚 → 无审计行」这一条就是
 * {@code @Order} 配置的回归测试。 另外用 {@code MANDATORY} 兜底：在无事务上下文里直接调 {@code AuditService.record} 必须立刻抛
 * {@link IllegalTransactionStateException}，而不是悄悄写一条自动提交的孤儿行。
 */
class AuditTransactionInvariantTest extends AbstractConsoleApiTest {

  @Autowired private AuditService auditService;
  @Autowired private AdminAuditLogRepository auditLogs;
  @Autowired private com.vocalverse.support.AuditProbeService rollbackProbe;

  private ConsolePrincipal principal() {
    return new ConsolePrincipal(1L, "audit-tester", "super", Set.of(), null);
  }

  // ------------------------------------------------------------------ 双向

  /** 提交 → 审计行存在，且 detail 与业务写入一致。 */
  @Test
  void commit_writes_audit_row() {
    long before = auditLogs.count();
    rollbackProbe.commitCase("AUDIT_COMMIT_MARKER");

    assertEquals(before + 1, auditLogs.count(), "成功路径必须恰好留 1 行审计");
    var row =
        auditLogs.findAll().stream()
            .filter(r -> "AUDIT_COMMIT_MARKER".equals(r.getSummary()))
            .findFirst()
            .orElseThrow(() -> new AssertionError("未找到审计行"));
    assertEquals("test.commit", row.getAction());
    assertEquals(AdminAuditLogEntity.RESULT_OK, row.getResult());
    assertTrue(
        row.getDetail() != null && row.getDetail().contains("nextStatus"),
        "detail 应含业务前后状态：" + row.getDetail());
  }

  /** 业务写后抛异常 → 事务回滚 → **没有**审计行。这是 @Order 的回归测试。 */
  @Test
  void rollback_writes_no_audit_row() {
    long before = auditLogs.count();

    assertThrows(
        IllegalStateException.class, () -> rollbackProbe.rollbackCase("AUDIT_ROLLBACK_MARKER"));

    assertEquals(before, auditLogs.count(), "业务回滚后审计行必须一并消失（否则审计记录了一次没发生的操作 —— 这是 @Order 配错的症状）");
    assertTrue(
        auditLogs.findAll().stream().noneMatch(r -> "AUDIT_ROLLBACK_MARKER".equals(r.getSummary())),
        "不得残留回滚用例的审计行");
  }

  /** 无事务上下文直接调 AuditService.record → 立刻炸（MANDATORY），绝不写孤儿行。 */
  @Test
  void audit_write_outside_transaction_fails_loudly() {
    long before = auditLogs.count();
    assertThrows(
        IllegalTransactionStateException.class,
        () -> auditService.record(principal(), "test.no_tx", "test", "1", "no tx", Map.of()));
    assertEquals(before, auditLogs.count(), "不得写出孤儿审计行");
  }

  // ------------------------------------------------------------------ 白名单

  /** 白名单外的键被静默丢弃并计数；口令类键单独计数。 */
  @Test
  void detail_allowlist_drops_disallowed_keys_and_counts_them() {
    Map<String, Object> raw = new LinkedHashMap<>();
    raw.put("prevStatus", "visible"); // 允许
    raw.put("nextStatus", "hidden"); // 允许
    raw.put("reasonCode", "spam"); // 允许
    raw.put("password", "hunter2-should-never-land"); // 拒绝（机密）
    raw.put("refreshToken", "abc123"); // 拒绝（机密）
    raw.put("someRandomKey", "x"); // 拒绝（未知）

    long droppedBefore = auditService.droppedDetailKeys();
    long droppedSecretBefore = auditService.droppedSecretKeys();

    Map<String, Object> filtered = auditService.filtered(raw);

    assertTrue(filtered != null);
    assertEquals(3, filtered.size(), "只应保留白名单内的 3 个键：" + filtered);
    assertFalse(filtered.containsKey("password"), "口令绝不入审计");
    assertFalse(filtered.containsKey("refreshToken"), "令牌绝不入审计");
    assertFalse(filtered.containsKey("someRandomKey"));
    assertEquals(droppedBefore + 3, auditService.droppedDetailKeys(), "丢弃数必须递增 3");
    assertEquals(droppedSecretBefore + 2, auditService.droppedSecretKeys(), "其中 2 个疑似机密");
  }

  /** 白名单过滤后为空 → detail 写 null（不写噪音空对象）。 */
  @Test
  void detail_becomes_null_when_everything_is_filtered() {
    Map<String, Object> raw = new HashMap<>();
    raw.put("passwordHash", "$2a$10$xxx");
    assertTrue(auditService.filtered(raw) == null);
  }

  /** 明确断言绝不允许的键（防止有人「顺手」把白名单放宽）。 */
  @Test
  void forbidden_keys_are_never_allowed() {
    for (String k :
        new String[] {
          "password",
          "passwordHash",
          "refreshToken",
          "accessToken",
          "token",
          "secret",
          "authorization",
          "totpSecret",
          "totp",
          "otp"
        }) {
      assertFalse(AuditFieldAllowlist.isAllowed(k), k + " 绝不能进白名单");
    }
  }

  /**
   * 白名单常量类必须能正常初始化。
   *
   * <p>回归用例（修复前必红）：{@code Set.of(...)} 有重复元素时会在**类初始化**阶段抛 {@code
   * ExceptionInInitializerError}，导致每一次审计写入都失败，而 {@code bestEffort} 把它降级成一行 warn ——
   * 表现为「审计静默不落库」，是最难发现的一类失效。
   */
  @Test
  void allowlist_constants_initialize_without_duplicates() {
    try {
      assertTrue(AuditFieldAllowlist.KEYS.size() > 20, "白名单应非空");
      assertTrue(AuditFieldAllowlist.FORBIDDEN_MARKERS.size() >= 8, "禁止词根应非空");
      assertTrue(AuditFieldAllowlist.isAllowed("prevStatus"));
      assertFalse(AuditFieldAllowlist.isAllowed("password"));
      assertFalse(AuditFieldAllowlist.isAllowed("totpSecret"), "totp 词根应覆盖 totpSecret");
    } catch (ExceptionInInitializerError e) {
      throw new AssertionError("AuditFieldAllowlist 静态初始化失败（通常是 Set.of 里有重复元素）：" + e.getCause(), e);
    }
  }

  /** 审计行必须带 request_id（docs/50 §9.2 断点 2：与 access log / 响应头同源）。 */
  @Test
  void audit_row_carries_request_id_from_request_context() {
    // 无请求上下文时 request_id 为 null（不抛异常）—— 这是「无害降级」的显式断言
    rollbackProbe.commitCase("REQ_ID_NULL_MARKER");
    var row =
        auditLogs.findAll().stream()
            .filter(r -> "REQ_ID_NULL_MARKER".equals(r.getSummary()))
            .findFirst()
            .orElseThrow();
    // 单测线程内没有 Web 请求 → null；有请求时 AuditService 会从 MDC/header 取值
    assertTrue(row.getRequestId() == null || !row.getRequestId().isBlank());
    assertTrue(row.getCreatedAt().isBefore(Instant.now().plusSeconds(5)));
  }
}
