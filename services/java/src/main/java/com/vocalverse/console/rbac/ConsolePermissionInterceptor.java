package com.vocalverse.console.rbac;

import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.console.audit.AuditService;
import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.auth.CurrentAdminArgumentResolver;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * 控制台权限拦截器（docs/50 §4.3 硬规则：每个端点在后端独立校验权限码）。
 *
 * <p>判定顺序：① 取主体（无 = 未登录，46001）→ ② 展开角色权限码（JWT 内快照，已含 {@code *} 通配）→ ③ 比对注解上的码（缺 = 46002 + {@code
 * data.required}）。
 *
 * <p>用 JWT 内的 {@code perms} 快照而非每请求查库：docs/50 §4.1 的取舍 —— 控制台 QPS 低但角色变更要即时生效， 折中是「快照 + {@code
 * token_epoch} 立即失效」。改角色的那一刻，成员令牌的 {@code epo} 就不匹配了， 所以快照最长只可能陈旧到「改权前的最后一次请求」，这正是设计要的语义。
 */
@Component
public class ConsolePermissionInterceptor implements HandlerInterceptor {

  private final RbacService rbac;
  private final AuditService audit;

  public ConsolePermissionInterceptor(RbacService rbac, AuditService audit) {
    this.rbac = rbac;
    this.audit = audit;
  }

  @Override
  public boolean preHandle(
      HttpServletRequest request, HttpServletResponse response, Object handler) {
    if (!(handler instanceof HandlerMethod method)) {
      return true; // 静态资源 / 404 等：交给后续处理
    }
    RequireConsolePermission required = method.getMethodAnnotation(RequireConsolePermission.class);
    if (required == null) {
      required = method.getBeanType().getAnnotation(RequireConsolePermission.class);
    }
    if (required == null) {
      // 未标注 = 无需权限码（如 /auth/me 只要登录）。这不是漏洞：/auth/me 的语义就是「我是谁」。
      // 覆盖面由 ConsolePermissionCoverageTest 兜住（除白名单外每个端点必须标注）。
      return true;
    }

    ConsolePrincipal principal = CurrentAdminArgumentResolver.from(request);
    if (principal == null) {
      throw ConsoleException.of(ConsoleErrorCodes.UNAUTHENTICATED);
    }
    String code = required.value();
    if (principal.has(code)) {
      return true;
    }
    // 纵深防御：JWT 快照与库不一致时（例如运维手改了 admin_role_permissions 而没 bump epoch），以库为准。
    if (rbac.hasPermission(principal.adminUserId(), code)) {
      return true;
    }

    // 「被拒」也要留痕（docs/50 §5.3.7 result 枚举含 denied）。
    // 拦截器**不能**直接写审计：preHandle 还没有业务事务，而 AuditService.record 是 MANDATORY
    // （见 AuditAspect 的事务不变量）。所以把「被哪个码拒了」挂到 request 属性上，
    // 由 ConsoleExceptionHandler 在拿到 46002 后用 REQUIRES_NEW 独立落库 —— 覆盖所有 console 端点，
    // 不需要每个 controller 手写 try/catch。
    request.setAttribute(DENIED_ACTION_ATTRIBUTE, "console.permission.denied");
    request.setAttribute(DENIED_REQUIRED_ATTRIBUTE, code);
    throw ConsoleException.of(
        ConsoleErrorCodes.PERMISSION_DENIED, "管理端权限不足：需要 " + code, Map.of("required", code));
  }

  /** 被拒动作名（ConsoleExceptionHandler 读取；{@code code} 类动作名会以 {@code console.endpoint.denied} 记录）。 */
  public static final String DENIED_ACTION_ATTRIBUTE = "consoleDeniedAction";

  /** 被拒时缺失的权限码。 */
  public static final String DENIED_REQUIRED_ATTRIBUTE = "consoleDeniedRequired";
}
