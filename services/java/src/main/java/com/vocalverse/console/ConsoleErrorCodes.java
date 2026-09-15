package com.vocalverse.console;

import java.util.Map;
import org.springframework.http.HttpStatus;

/**
 * 46xxx 错误码 registry（数值与 HTTP 状态**严格取自 docs/50 §10.4**，不自行增删）。
 *
 * <p>本类只做「码 → 状态 / 默认文案」的映射；登记动作由父 Agent 统一写 {@code docs/api/error-codes.md} （本模块**不修改**该文件）。
 */
public final class ConsoleErrorCodes {

  private ConsoleErrorCodes() {}

  // ------------------------------------------------------------------ 码

  /** 401 · 管理端未登录 / 控制台令牌失效（前端跳控制台登录页，不走 App 登录）。 */
  public static final int UNAUTHENTICATED = 46001;

  /** 403 · 管理端权限不足（缺具体权限码，{@code data.required} 回传所需码）。 */
  public static final int PERMISSION_DENIED = 46002;

  /** 403 · 管理端账号已停用 / 已锁定（{@code data.lockedUntil}）。 */
  public static final int ACCOUNT_UNAVAILABLE = 46003;

  /** 404 · 凭据不匹配（账号不存在或口令错误 —— 对外合并，见 ConsoleAuthService 的反枚举说明）。 */
  public static final int ADMIN_NOT_FOUND = 46004;

  /** 409 · 管理端用户名已存在。 */
  public static final int USERNAME_TAKEN = 46005;

  /** 409 · 角色不可删除（内置角色 / 仍有成员 / 仍被引用）。 */
  public static final int ROLE_NOT_DELETABLE = 46006;

  /** 422 · 管理端入参非法（枚举 / 长度 / 时间窗过大 {@code data.suggestedStep}）。 */
  public static final int INVALID_PARAM = 46007;

  /** 429 · 管理端登录失败次数过多 / 同 IP 限流（{@code data.retryAfter}）。 */
  public static final int LOGIN_THROTTLED = 46008;

  /** 404 · 审核对象不存在（内容已物理消失）。 */
  public static final int TARGET_NOT_FOUND = 46009;

  /** 409 · 审核单状态不允许该动作（已终态 / 并发已被处理）。 */
  public static final int CASE_STATE_CONFLICT = 46010;

  /** 422 · 上架校验失败（{@code data.violations[]} 字段级原因）。 */
  public static final int PUBLISH_VALIDATION_FAILED = 46011;

  /** 404 · LLM trace 不存在或已过保留期（Python 侧）。 */
  public static final int TRACE_NOT_FOUND = 46012;

  /** 503 · 遥测存储不可用（Python 侧）。 */
  public static final int TELEMETRY_UNAVAILABLE = 46013;

  /** 403 · 运维采集通道未开启（Python 侧）。 */
  public static final int TELEMETRY_DISABLED = 46014;

  /** 409 · 举报已存在待处理记录（幂等返回既有 {@code caseId}）。 */
  public static final int REPORT_DUPLICATE = 46015;

  private static final Map<Integer, HttpStatus> STATUS =
      Map.ofEntries(
          Map.entry(UNAUTHENTICATED, HttpStatus.UNAUTHORIZED),
          Map.entry(PERMISSION_DENIED, HttpStatus.FORBIDDEN),
          Map.entry(ACCOUNT_UNAVAILABLE, HttpStatus.FORBIDDEN),
          Map.entry(ADMIN_NOT_FOUND, HttpStatus.NOT_FOUND),
          Map.entry(USERNAME_TAKEN, HttpStatus.CONFLICT),
          Map.entry(ROLE_NOT_DELETABLE, HttpStatus.CONFLICT),
          Map.entry(INVALID_PARAM, HttpStatus.UNPROCESSABLE_ENTITY),
          Map.entry(LOGIN_THROTTLED, HttpStatus.TOO_MANY_REQUESTS),
          Map.entry(TARGET_NOT_FOUND, HttpStatus.NOT_FOUND),
          Map.entry(CASE_STATE_CONFLICT, HttpStatus.CONFLICT),
          Map.entry(PUBLISH_VALIDATION_FAILED, HttpStatus.UNPROCESSABLE_ENTITY),
          Map.entry(TRACE_NOT_FOUND, HttpStatus.NOT_FOUND),
          Map.entry(TELEMETRY_UNAVAILABLE, HttpStatus.SERVICE_UNAVAILABLE),
          Map.entry(TELEMETRY_DISABLED, HttpStatus.FORBIDDEN),
          Map.entry(REPORT_DUPLICATE, HttpStatus.CONFLICT));

  private static final Map<Integer, String> MESSAGES =
      Map.ofEntries(
          Map.entry(UNAUTHENTICATED, "管理端未登录或控制台令牌已失效"),
          Map.entry(PERMISSION_DENIED, "管理端权限不足"),
          Map.entry(ACCOUNT_UNAVAILABLE, "管理端账号已停用或已锁定"),
          Map.entry(ADMIN_NOT_FOUND, "用户名或口令不正确"),
          Map.entry(USERNAME_TAKEN, "管理端用户名已存在"),
          Map.entry(ROLE_NOT_DELETABLE, "角色不可删除（内置角色 / 仍有成员 / 仍被引用）"),
          Map.entry(INVALID_PARAM, "管理端入参非法"),
          Map.entry(LOGIN_THROTTLED, "登录尝试过于频繁，请稍后再试"),
          Map.entry(TARGET_NOT_FOUND, "审核对象不存在"),
          Map.entry(CASE_STATE_CONFLICT, "审核单状态不允许该动作"),
          Map.entry(PUBLISH_VALIDATION_FAILED, "上架校验失败"),
          Map.entry(TRACE_NOT_FOUND, "LLM trace 不存在或已过保留期"),
          Map.entry(TELEMETRY_UNAVAILABLE, "遥测存储不可用"),
          Map.entry(TELEMETRY_DISABLED, "运维采集通道未开启"),
          Map.entry(REPORT_DUPLICATE, "举报已存在待处理记录"));

  public static HttpStatus status(int code) {
    return STATUS.getOrDefault(code, HttpStatus.INTERNAL_SERVER_ERROR);
  }

  public static String message(int code) {
    return MESSAGES.getOrDefault(code, "管理端请求失败");
  }
}
