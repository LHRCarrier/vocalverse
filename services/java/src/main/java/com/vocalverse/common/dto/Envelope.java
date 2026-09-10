package com.vocalverse.common.dto;

/**
 * 统一响应 envelope（docs/06 §7）：{code, message, data}，成功 code=0。
 *
 * <p>前端类型由契约生成（apps/web/src/api/generated/java-api.d.ts）——Java 侧任何接口 返回必须经本类包装，不得裸返回对象（2026-09-01 修
 * M1 遗留：ping 裸返回导致前端误判）。
 */
public record Envelope<T>(int code, String message, T data) {

  public static <T> Envelope<T> ok(T data) {
    return new Envelope<>(0, "ok", data);
  }

  public static <T> Envelope<T> error(int code, String message) {
    return new Envelope<>(code, message, null);
  }

  /**
   * 错误 envelope 允许携带结构化 data（2026-09-10 管理端新增）。
   *
   * <p>背景：docs/api/envelope.md 原文是「错误 data 恒 null」，但 docs/50 §10.4 对若干码**明确要求结构化 data**——46002 的
   * {@code data.required}、46003 的 {@code data.lockedUntil}、46008 的 {@code data.retryAfter}、46011 的
   * {@code data.violations[]}、46015 的 {@code data.caseId}。 无此重载则只能把所需权限码拼进 message
   * 字符串，前端无法可靠解析（前端是安全边界的体验层， 不该靠正则读中文提示）。本重载为**纯新增**：{@link #error(int, String)} 行为不变。
   */
  public static <T> Envelope<T> error(int code, String message, T data) {
    return new Envelope<>(code, message, data);
  }
}
