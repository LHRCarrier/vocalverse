package com.vocalverse.console.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.common.dto.Envelope;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.rbac.AdminUserEntity;
import com.vocalverse.console.rbac.AdminUserRepository;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 控制台令牌过滤器（docs/50 §4.1）。<b>只挂在控制台安全链上</b>（{@code ConsoleSecurityConfig}）， 不注册为 Servlet Filter ——
 * 既有 {@code JwtAuthFilter} 也不在 App 链之外运行（它由 {@code SecurityConfig} 显式 new 出来加链，无
 * {@code @Component}，因此没有 Boot 的 servlet 自动注册）。
 *
 * <p>三件事，顺序不可换：
 *
 * <ol>
 *   <li><b>验签 + aud + typ</b>（{@link ConsoleJwtService#parse}）：App token（aud/typ 不符）在此被拒；
 *   <li><b>token_epoch 强制校验</b>（本设计的即时生效机制，docs/50 §4.1 补偿项③）：每次都按主键回读 {@code admin_users.status +
 *       token_epoch}（单次 PK 查询，微秒级，不读权限表、不读角色表）， {@code epo} 与库中不符 → 令牌立即作废。停用/降权/改密时 bump epoch +
 *       吊销会话 → 下一请求即生效， 无需等 900s TTL，也无需黑名单；
 *   <li>通过后把 {@link ConsolePrincipal} 写入 SecurityContext（authority = {@code ROLE_CONSOLE}，
 *       仅用于「是否已登录」判定；**权限码不在这里判**，见下）。
 * </ol>
 *
 * <p><b>为什么权限码不在过滤器里判</b>：过滤器只能拿到路径，做不出「这个方法需要哪个码」的判断； 用路径前缀猜会在端点增删时悄悄放行。权限判定的唯一位置是 {@code
 * ConsolePermissionInterceptor} 读 controller 方法上的 {@code @RequireConsolePermission} —— 只读方法签名，不猜路径。
 */
public class ConsoleSecurityFilter extends OncePerRequestFilter {

  /** 免鉴权路径（docs/50 §10.2：login / refresh）。其余一律需要有效控制台令牌。 */
  private static final List<String> PUBLIC_PATHS =
      List.of("/api/v1/console/auth/login", "/api/v1/console/auth/refresh");

  private final ConsoleJwtService jwt;
  private final AdminUserRepository adminUsers;
  private final ObjectMapper mapper;

  public ConsoleSecurityFilter(
      ConsoleJwtService jwt, AdminUserRepository adminUsers, ObjectMapper mapper) {
    this.jwt = jwt;
    this.adminUsers = adminUsers;
    this.mapper = mapper;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
      throws ServletException, IOException {
    String header = request.getHeader("Authorization");
    if (header == null || !header.startsWith("Bearer ")) {
      // 无令牌：放行交给安全链 —— permitAll 的 login/refresh 正常处理，
      // 其余路径由 EntryPoint 统一回 46001 Envelope（而不是 Spring 默认错误页）。
      filterChain.doFilter(request, response);
      return;
    }

    Claims claims;
    try {
      claims = jwt.parse(header.substring(7));
    } catch (JwtException | IllegalArgumentException e) {
      // 令牌无效/aud 不符/typ 不符：免鉴权路径（登录本身）直接放行，其余 46001。
      // 免鉴权路径**不抛错**是有意的：这样手机 App 复用同一 client 打登录接口时，
      // 残留的 App token 不会把「登录」这一步本身打挂。
      if (isPublic(request)) {
        filterChain.doFilter(request, response);
        return;
      }
      reject(response, ConsoleErrorCodes.UNAUTHENTICATED, "控制台令牌无效或已过期：请重新登录", null);
      return;
    }

    long adminUserId;
    try {
      adminUserId = Long.parseLong(claims.getSubject());
    } catch (NumberFormatException e) {
      reject(response, ConsoleErrorCodes.UNAUTHENTICATED, "控制台令牌 subject 非法", null);
      return;
    }

    // token_epoch 强制校验：主键命中查询，读 status + token_epoch（不读权限/角色表）
    AdminUserEntity user = adminUsers.findById(adminUserId).orElse(null);
    if (user == null) {
      reject(response, ConsoleErrorCodes.UNAUTHENTICATED, "管理端账号不存在或令牌已失效", null);
      return;
    }
    if (!AdminUserEntity.STATUS_ACTIVE.equals(user.getStatus())) {
      reject(
          response,
          ConsoleErrorCodes.ACCOUNT_UNAVAILABLE,
          "管理端账号已停用",
          Map.of("status", user.getStatus()));
      return;
    }
    if (ConsoleJwtService.epochOf(claims) != user.getTokenEpoch()) {
      // 已改权/改密/被强制下线：epoch 不符 → 令牌立即作废（docs/50 §4.1 补偿项②③）
      reject(response, ConsoleErrorCodes.UNAUTHENTICATED, "控制台令牌已失效（账号权限或口令已变更）：请重新登录", null);
      return;
    }
    Instant lockedUntil = user.getLockedUntil();
    if (lockedUntil != null && lockedUntil.isAfter(Instant.now())) {
      reject(
          response,
          ConsoleErrorCodes.ACCOUNT_UNAVAILABLE,
          "管理端账号已锁定",
          Map.of("lockedUntil", lockedUntil.toString()));
      return;
    }

    Set<String> perms = new LinkedHashSet<>();
    Object rawPerms = claims.get("perms");
    if (rawPerms instanceof List<?> list) {
      for (Object o : list) {
        if (o != null) {
          perms.add(String.valueOf(o));
        }
      }
    }
    Number sid = claims.get("sid", Number.class);
    ConsolePrincipal principal =
        new ConsolePrincipal(
            adminUserId,
            claims.get("uname", String.class) == null
                ? user.getUsername()
                : claims.get("uname", String.class),
            claims.get("role", String.class),
            perms,
            sid == null ? null : sid.longValue());

    SecurityContextHolder.getContext()
        .setAuthentication(
            new UsernamePasswordAuthenticationToken(
                principal, null, List.of(new SimpleGrantedAuthority("ROLE_CONSOLE"))));
    request.setAttribute(CurrentAdminArgumentResolver.REQUEST_ATTRIBUTE, principal);
    // docs/50 §9.1「access log 增加 adminUserId」：写 **request attribute**（access log 用 %{adminUserId}r
    // 读）。
    // 注意：MDC 在这里也设一份供 logback pattern 用，但 access log **读不到 MDC**（见 application.yml 注释）。
    request.setAttribute(ADMIN_USER_ID_ATTRIBUTE, adminUserId);
    org.slf4j.MDC.put(ADMIN_USER_ID_MDC_KEY, String.valueOf(adminUserId));
    try {
      filterChain.doFilter(request, response);
    } finally {
      // 必须清：Tomcat 复用工作线程，不清会把上一个管理员的身份带进下一个请求的日志行
      org.slf4j.MDC.remove(ADMIN_USER_ID_MDC_KEY);
    }
  }

  /** access log 用 {@code %{adminUserId}r} 读取的 request attribute 名。 */
  public static final String ADMIN_USER_ID_ATTRIBUTE = "adminUserId";

  /** logback pattern 用的 MDC key（与 request attribute 同名，便于对照）。 */
  public static final String ADMIN_USER_ID_MDC_KEY = "adminUserId";

  private boolean isPublic(HttpServletRequest request) {
    return PUBLIC_PATHS.contains(request.getRequestURI());
  }

  /** 401/403 + Envelope（过滤器层无法走 @RestControllerAdvice，显式写 JSON —— 同 JwtAuthFilter 惯例）。 */
  private void reject(HttpServletResponse response, int code, String message, Object data)
      throws IOException {
    response.setStatus(com.vocalverse.console.ConsoleErrorCodes.status(code).value());
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write(mapper.writeValueAsString(Envelope.error(code, message, data)));
  }
}
