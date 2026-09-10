package com.vocalverse.common;

import com.vocalverse.common.dto.Envelope;
import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * 全局异常 → Envelope（J-08，2026-09-08）：统一 {code, message, data}。
 *
 * <p>背景：此前全仓唯一 @RestControllerAdvice 限定 basePackages=community，Auth/Admin/Ticket/Content/ Internal
 * 等域抛 ResponseStatusException / 校验失败 → Spring 默认错误体 {timestamp,status,error,path}， 前端按 Envelope 解包时
 * data=null、message 读不到（docs/06 第 7 章「任何返回必须过 Envelope」被静默破坏）。
 *
 * <p>职责边界：
 *
 * <ul>
 *   <li>{@link CommunityException} 仍由 community 包专属 Advice 处理（社区业务码 4xxxx 语义）；
 *   <li>本 Advice **不声明** MethodArgumentNotValidException：community 控制器仍命中
 *       CommunityExceptionHandler（校验失败统一 42203 特例，docs/37）；非 community 校验异常由 下方兜底 handler 转
 *       42201（docs/api/error-codes.md）；
 *   <li>ResponseStatusException（Auth/Admin/Ticket/Content/Internal 显式抛出）按 HTTP 状态映射
 *       错误码：400→40001、401→40101、403→40301、404→40401、405→40501、409→40904（「已登记未抛出」
 *       接线：资源/唯一键冲突语义，2026-09-08）、422→42201，其余→50002；
 *   <li>兜底 Exception（含 DataIntegrityViolationException 外的未知异常）→ 500/50002， 不再吐 Spring
 *       默认错误体；过滤器层（JwtAuthFilter 401 / ServiceTokenFilter / Security 403）不经本 Advice，属已知边界（docs/18
 *       登记）。
 * </ul>
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

  private static final org.slf4j.Logger log =
      org.slf4j.LoggerFactory.getLogger(GlobalExceptionHandler.class);

  /** HTTP 状态 → 错误码映射（docs/api/error-codes.md，先登记后用）。 */
  private static final Map<Integer, Integer> STATUS_CODE =
      Map.of(
          400, 40001,
          401, 40101,
          403, 40301,
          404, 40401,
          405, 40501,
          409, 40904,
          422, 42201);

  @ExceptionHandler(ResponseStatusException.class)
  public ResponseEntity<Envelope<Void>> handleResponseStatus(ResponseStatusException ex) {
    int http = ex.getStatusCode().value();
    String message = ex.getReason() != null ? ex.getReason() : "请求处理失败";
    return ResponseEntity.status(http)
        .body(Envelope.error(STATUS_CODE.getOrDefault(http, 50002), message));
  }

  /** 唯一键/约束冲突（注册撞用户名、并发写撞唯一索引等）→ 409/40904（J-08 接线「已登记未抛出」码）。 */
  @ExceptionHandler(DataIntegrityViolationException.class)
  public ResponseEntity<Envelope<Void>> handleConstraint(DataIntegrityViolationException ex) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
        .body(Envelope.error(40904, "数据冲突：唯一键或约束（重复提交/并发写入）"));
  }

  @ExceptionHandler(NoResourceFoundException.class)
  public ResponseEntity<Envelope<Void>> handleNoResource(NoResourceFoundException ex) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
        .body(Envelope.error(40401, "资源不存在：" + ex.getResourcePath()));
  }

  @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
  public ResponseEntity<Envelope<Void>> handleMethodNotAllowed(
      HttpRequestMethodNotSupportedException ex) {
    return ResponseEntity.status(HttpStatus.METHOD_NOT_ALLOWED)
        .body(Envelope.error(40501, "方法不允许：" + ex.getMethod()));
  }

  @ExceptionHandler(HttpMessageNotReadableException.class)
  public ResponseEntity<Envelope<Void>> handleUnreadable(HttpMessageNotReadableException ex) {
    return ResponseEntity.badRequest().body(Envelope.error(40001, "请求体无法解析"));
  }

  @ExceptionHandler(HandlerMethodValidationException.class)
  public ResponseEntity<Envelope<Void>> handleMethodValidation(
      HandlerMethodValidationException ex) {
    return ResponseEntity.badRequest().body(Envelope.error(40001, "参数校验失败"));
  }

  /** 兜底：任何未单列异常 → Envelope（非 community 的 MethodArgumentNotValidException 在此转 42201）。 */
  @ExceptionHandler(Exception.class)
  public ResponseEntity<Envelope<Void>> handleFallback(Exception ex) {
    if (ex instanceof MethodArgumentNotValidException m) {
      String message =
          m.getBindingResult().getFieldErrors().stream()
              .limit(1)
              .map(
                  f ->
                      f.getField()
                          + " "
                          + (f.getDefaultMessage() == null ? "非法" : f.getDefaultMessage()))
              .findFirst()
              .orElse("参数非法");
      return ResponseEntity.badRequest().body(Envelope.error(42201, "请求体校验失败：" + message));
    }
    if (ex instanceof jakarta.validation.ConstraintViolationException) {
      return ResponseEntity.badRequest().body(Envelope.error(40001, "参数校验失败"));
    }
    // 2026-09-10 补日志：此前这里**不记任何日志**，客户端只看到 {"code":50002}，
    // 服务端也一片安静 —— 排障时只能靠猜（本轮就因此在若干个 50002 上反复试错）。
    // 500 是「不该发生」的类别，必须留下完整堆栈；4xx 兜底路径不记（那是预期内的业务拒绝）。
    log.error("未处理异常 → 50002（{}）：{}", ex.getClass().getName(), ex.getMessage(), ex);
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
        .body(Envelope.error(50002, "服务内部错误"));
  }
}
