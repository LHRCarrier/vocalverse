package com.vocalverse.console.audit;

import java.util.Set;

/**
 * {@code admin_audit_logs.detail} 的**字段白名单**（docs/50 §9.3 红线）。
 *
 * <p>白名单外的键**静默丢弃并计数**（{@code audit_detail_dropped_total}）—— 不抛异常、不写警告刷屏，
 * 但计数器必须递增，否则「审计字段被拦」这件事本身会变得不可观测（docs/50 §9.4 要求控制台自身可被观测）。
 *
 * <p>白名单口径（docs/50 §9.3）：{@code status/code/name/title/priority/severity/enabled/prevStatus/
 * nextStatus/reasonCode/assigneeId/permissionCodes/…}。本常量类把「…」展开为控制台实际会写的全部键，
 * 并按「业务状态字段」与「归因字段」分组说明，便于评审时逐条核对。
 *
 * <p><b>永不入白名单</b>：{@code password} / {@code passwordHash} / {@code refreshToken} / {@code
 * accessToken} / {@code token} / {@code secret} / {@code authorization} / {@code *token*} ——
 * 即使调用方传了也会被丢弃。 这里用「显式拒绝列表 + 白名单双重把关」：拒绝列表只为**留痕**（被拒时记 {@code dropped_secret} 计数）， 真正的安全边界是白名单本身。
 */
public final class AuditFieldAllowlist {

  private AuditFieldAllowlist() {}

  /**
   * 允许写入 {@code detail} 的键。
   *
   * <p><b>必须保持无重复</b>：{@code Set.of(...)} 有重复元素时会在类初始化阶段抛 {@code IllegalArgumentException} → {@code
   * ExceptionInInitializerError}， 结果是**每一次审计写入都失败**（{@code bestEffort} 把它降级成一行 warn，看起来只是「审计没数据」）。
   * 曾经 {@code revoked} 出现两次、{@code totp}/{@code otp} 与 {@code totpSecret} 同时命中词根， 两处都炸。{@code
   * AuditTransactionInvariantTest} 有专门的用例盯这一类回归。
   */
  public static final Set<String> KEYS =
      Set.of(
          // ── 内容域状态
          "status",
          "prevStatus",
          "nextStatus",
          "code",
          "name",
          "title",
          "priority",
          "severity",
          "enabled",
          "reasonCode",
          "note",
          // ── 审核域
          "decision",
          "caseId",
          "reportId",
          "targetType",
          "reportCount",
          "duplicate",
          // ── RBAC 域
          "roleCode",
          "roleId",
          "permissionCodes",
          "granted",
          "revoked",
          "memberCount",
          "before",
          "after",
          // ── 会话/登录域（只放 id 与计数，不放任何令牌材料）
          "sessionId",
          "revokedSessions",
          "lockedUntil",
          "retryAfter",
          "failedAttempts",
          "ip",
          "userAgentHash",
          // ── 发布/校验域
          "violations",
          "violationCount",
          "publishedAt",
          "fields");

  /**
   * 明确禁止的键（命中即丢弃并单独计数，便于发现「有人试图把口令写进审计」）。
   *
   * <p>必须**保持无重复**：{@code Set.of(...)} 遇到重复元素会在类初始化时抛 {@code IllegalArgumentException}，包成 {@code
   * ExceptionInInitializerError} —— 那意味着**每一次审计写入都失败**（而 {@code bestEffort} 会把它降级成一行 warn，
   * 表现为「审计静默不落库」）。曾经 {@code totp} 与 {@code totpSecret} 同时命中， 写死两个词就等于埋了一颗必炸的雷，所以这里只留词根，靠 substring
   * 匹配覆盖变体。
   */
  public static final Set<String> FORBIDDEN_MARKERS =
      Set.of(
          "password",
          "passwd",
          "pwd",
          "token",
          "secret",
          "authorization",
          "credential",
          "hash",
          "totp");

  public static boolean isAllowed(String key) {
    if (key == null || key.isBlank()) {
      return false;
    }
    if (KEYS.contains(key)) {
      return true;
    }
    String lower = key.toLowerCase(java.util.Locale.ROOT);
    for (String marker : FORBIDDEN_MARKERS) {
      if (lower.contains(marker)) {
        return false;
      }
    }
    return false;
  }

  /** 键是否属于「看起来像机密」（用于把丢弃原因分成两类计数）。 */
  public static boolean looksSecret(String key) {
    if (key == null) {
      return false;
    }
    String lower = key.toLowerCase(java.util.Locale.ROOT);
    for (String marker : FORBIDDEN_MARKERS) {
      if (lower.contains(marker)) {
        return true;
      }
    }
    return false;
  }
}
