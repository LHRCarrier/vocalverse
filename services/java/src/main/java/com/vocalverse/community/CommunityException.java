package com.vocalverse.community;

import org.springframework.http.HttpStatus;

/**
 * 社区业务错误（错误码见 docs/api/error-codes.md 社区段：40402/40302/40904/42203）。
 *
 * <p>HTTP 状态码负责传输层，code 负责业务语义（docs/06 §7）；由 CommunityExceptionHandler 统一包为 Envelope{code, message,
 * data:null}。
 */
public class CommunityException extends RuntimeException {

  private final int code;
  private final HttpStatus httpStatus;

  public CommunityException(int code, String message, HttpStatus httpStatus) {
    super(message);
    this.code = code;
    this.httpStatus = httpStatus;
  }

  public int getCode() {
    return code;
  }

  public HttpStatus getHttpStatus() {
    return httpStatus;
  }
}
