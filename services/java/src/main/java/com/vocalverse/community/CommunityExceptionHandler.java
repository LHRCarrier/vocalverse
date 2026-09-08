package com.vocalverse.community;

import com.vocalverse.common.dto.Envelope;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 社区域异常 → Envelope（限定 basePackages=community，与全局 GlobalExceptionHandler 并存：
 * 本类 @Order(HIGHEST_PRECEDENCE) 保证先被咨询——同类型异常（CommunityException / 校验失败）由本类
 * 按社区语义处理（42203），其余类型回落到全局 Advice 统一 Envelope）。校验失败统一 42203（docs/37
 * 错误码），业务错误按 CommunityException 的 code/httpStatus。
 */
@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(basePackages = "com.vocalverse.community")
public class CommunityExceptionHandler {

  @ExceptionHandler(CommunityException.class)
  public ResponseEntity<Envelope<Void>> handleCommunity(CommunityException ex) {
    return ResponseEntity.status(ex.getHttpStatus())
        .body(Envelope.error(ex.getCode(), ex.getMessage()));
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<Envelope<Void>> handleValidation(MethodArgumentNotValidException ex) {
    String message =
        ex.getBindingResult().getFieldErrors().stream()
            .limit(1)
            .map(
                f ->
                    f.getField()
                        + " "
                        + (f.getDefaultMessage() == null ? "非法" : f.getDefaultMessage()))
            .findFirst()
            .orElse("参数非法");
    return ResponseEntity.badRequest().body(Envelope.error(42203, "社区入参非法：" + message));
  }
}
