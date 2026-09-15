package com.vocalverse.console;

import org.springframework.http.HttpStatus;

/**
 * 管理端业务异常（docs/50 §10.4 的 46xxx 错误码registry）。
 *
 * <p>与既有 Common 侧的 {@code ResponseStatusException} 约定一致：异常自带 HTTP 状态，由 {@link
 * ConsoleExceptionHandler} 转成 {@code Envelope}。{@code data} 只在少数码需要（46002 的 {@code
 * data.required}、46003 的 {@code data.lockedUntil}、46008 的 {@code data.retryAfter}、46011 的 {@code
 * data.violations[]}、46015 的 {@code data.caseId}）。
 */
public class ConsoleException extends RuntimeException {

  private final int code;
  private final HttpStatus status;
  private final transient Object data;

  public ConsoleException(int code, String message, HttpStatus status) {
    this(code, message, status, null);
  }

  public ConsoleException(int code, String message, HttpStatus status, Object data) {
    super(message);
    this.code = code;
    this.status = status;
    this.data = data;
  }

  public int code() {
    return code;
  }

  public HttpStatus status() {
    return status;
  }

  public Object data() {
    return data;
  }

  // ------------------------------------------------------------------ 便捷构造

  public static ConsoleException of(int code) {
    return new ConsoleException(
        code, ConsoleErrorCodes.message(code), ConsoleErrorCodes.status(code));
  }

  public static ConsoleException of(int code, String message) {
    return new ConsoleException(code, message, ConsoleErrorCodes.status(code));
  }

  public static ConsoleException of(int code, String message, Object data) {
    return new ConsoleException(code, message, ConsoleErrorCodes.status(code), data);
  }
}
