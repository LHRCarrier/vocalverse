package com.vocalverse.console;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.console.audit.IndependentAuditWriter;
import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.auth.CurrentAdminArgumentResolver;
import com.vocalverse.console.rbac.ConsolePermissionInterceptor;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 管理端异常 → Envelope（docs/50 §10.4 的 46xxx 段）。
 *
 * <p><b>为什么必须单独一个 Advice</b>：{@code common.GlobalExceptionHandler} 的兜底
 * {@code @ExceptionHandler(Exception.class)} 会把未匹配异常转成 50002；{@code ConsoleException} 若不加
 * 显式处理，46xxx 语义会全部丢失。本 Advice 用 {@code @Order(HIGHEST_PRECEDENCE)} 抢在全局兜底之前。
 *
 * <p><b>{@code basePackages} 是**必需**的，不是优化</b>（2026-09-10 实测事故）：
 * 本类原先是不限包的 {@code @RestControllerAdvice} + {@code @Order(HIGHEST_PRECEDENCE)} + 兜底
 * {@code @ExceptionHandler(Exception.class)}。这三条合起来会把**整个应用**的异常处理劫持过来——
 * 任何非控制台接口抛异常都落到这里的 500，于是
 * {@code ErrorEnvelopeTest} 6/6 由 400/401/404/405 变成 500、
 * {@code AuthFlowTest}/{@code UserMeApiTest}/{@code TicketApiTest}/{@code CommunityApiTest} 一路 500，
 * **30 个测试红**。既有 {@code CommunityExceptionHandler} 正是用
 * {@code @Order(HIGHEST_PRECEDENCE) + @RestControllerAdvice(basePackages=...)} 这个组合的，
 * 这里照抄同一个模式：**抢顺序，但只抢自己包的**。
 *
 * <p>与既有约定一致：不声明 {@code MethodArgumentNotValidException}（那是 community 包专属 42203 特例， 控制台控制器不加 Bean
 * Validation 注解，入参校验一律走 {@code ConsoleException 46007}，规则集中在服务层）。
 *
 * <p>「被拒也留痕」：权限拦截器把缺失的权限码挂在 request 属性上抛 46002，本类在转 Envelope 的同时用 {@link IndependentAuditWriter} 以
 * <b>独立事务</b>落一行 {@code result=denied} 审计。 为什么用独立事务：拒绝路径没有业务事务可依附（拦截器在事务之前就抛了），而且这行审计**不应**被 业务回滚带走
 * —— 「有人试图越权」是安全事件，与业务是否成功无关。
 */
@RestControllerAdvice(basePackages = "com.vocalverse.console")
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ConsoleExceptionHandler {

  private static final Logger log = LoggerFactory.getLogger(ConsoleExceptionHandler.class);

  private final IndependentAuditWriter audit;

  public ConsoleExceptionHandler(IndependentAuditWriter audit) {
    this.audit = audit;
  }

  @ExceptionHandler(ConsoleException.class)
  public ResponseEntity<Envelope<Object>> handle(ConsoleException ex, HttpServletRequest request) {
    // 46xxx 是**预期内**的业务结果（未登录/无权限/校验失败…），按 WARN 留一行便于排障；
    // 不回显入参，避免把口令/令牌经日志外泄（docs/50 §9.3 红线）。
    log.warn("console error code={} status={} message={}", ex.code(), ex.status(), ex.getMessage());
    if (ex.code() == ConsoleErrorCodes.PERMISSION_DENIED) {
      recordDeniedAudit(request, ex);
    }
    return ResponseEntity.status(ex.status())
        .body(Envelope.error(ex.code(), ex.getMessage(), ex.data()));
  }

  /**
   * 未预期的运行时异常 → 50002 + **完整堆栈入日志**。
   *
   * <p>不加这个分支的话，{@code ConsoleException} 之外的异常会落到
   * {@code GlobalExceptionHandler.handleFallback}，客户端只看到 50002、服务端也没有堆栈
   * （本轮实测就因此在若干个 50002 上只能靠猜）。这是纵深防御：即使 Console 的 advice 排在前面，
   * 也要保证「控制台路径上的 500 一定有堆栈」。
   */
  @ExceptionHandler(Exception.class)
  public ResponseEntity<Envelope<Object>> handleUnexpected(Exception ex) {
    log.error("console 未处理异常 → 50002（{}）：{}", ex.getClass().getName(), ex.getMessage(), ex);
    return ResponseEntity.status(org.springframework.http.HttpStatus.INTERNAL_SERVER_ERROR)
        .body(Envelope.error(50002, "服务内部错误"));
  }

  /** 越权尝试落审计（{@code result=denied} + 46002 错误码）。审计失败**不得**改变响应。 */
  private void recordDeniedAudit(HttpServletRequest request, ConsoleException ex) {
    Object attr = request.getAttribute(ConsolePermissionInterceptor.DENIED_ACTION_ATTRIBUTE);
    String required =
        String.valueOf(
            request.getAttribute(ConsolePermissionInterceptor.DENIED_REQUIRED_ATTRIBUTE));
    ConsolePrincipal principal = CurrentAdminArgumentResolver.from(request);
    audit.bestEffort(
        () ->
            audit.recordDeniedIndependent(
                principal == null ? null : principal.adminUserId(),
                principal == null ? null : principal.username(),
                attr == null ? "console.permission.denied" : String.valueOf(attr),
                ex.code(),
                "管理端越权被拒：" + ex.getMessage(),
                Map.of("reasonCode", required)),
        "permission-denied");
  }
}
