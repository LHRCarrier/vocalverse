package com.vocalverse.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.common.dto.Envelope;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserRepository;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * JWT 请求过滤器：解析 Bearer 令牌 → 查 users.status（J-02）→ 写入 SecurityContext
 * （principal=userId，authority=ROLE_&lt;role&gt;）与 request attr。role 来自 JWT claim（2026-09 起签发）， 无
 * role claim 的旧令牌按 ROLE_USER 处理。
 *
 * <p>J-02（2026-09-08）：status != 'active' 或用户已不存在 → 立即 401（Envelope 40101），不再等 access token
 * 过期——修复「禁用不即时生效」：JwtAuthFilter 此前只验签不查库，disabled 用户在 access-ttl=3600 内仍可访问全部受保护端点。代价 = 每请求一次 PK
 * 查库（本服务为薄管理端， QPS 低，可承受；规模增长再上短 TTL 缓存 + 变更失效，登记 docs/18 J-02 后续项）。
 *
 * <h2>2026-09-10 · 跨端令牌闸门（App 侧）</h2>
 *
 * <p>新增：**任何携带 {@code aud} claim 且不等于本服务受众的令牌一律拒绝**（{@link #APP_AUDIENCES}）。 这是堵住「控制台令牌冒充 App
 * 用户」的闸门 —— 控制台令牌带 {@code aud=vocalverse-console}， 且其 {@code sub} 是 {@code
 * admin_users.id}；若落到本过滤器，{@code users.findById(sub)} 可能命中一个 <b>真实的 App 用户 id</b>，于是审核员就成了那个用户。
 *
 * <p><b>为什么只拒绝「外来 aud」而不给 App 令牌加 aud</b>（这是刻意的兼容性取舍，不是遗漏）：
 *
 * <ol>
 *   <li>既有 App 令牌**没有** {@code aud} claim（{@code JwtService.generateAccessToken} 只签
 *       sub/role/iat/exp）， 线下也已有大量在途令牌，所以判定必须是「有 aud 且不匹配才拒」；
 *   <li>更硬的理由：{@code AuthController.issue()} 把**同一个 access token 字符串**拼成 refresh token （{@code
 *       buildRefreshToken(jwt.generateAccessToken(...))}）并以 30 天 TTL 存进 {@code
 *       refresh_tokens.token_hash}。若给新签发的 App 令牌加 {@code aud}，那么所有**既有** refresh token 所嵌入的内层 JWT
 *       仍然没有 aud 而外层字符串已固定 —— 一旦 {@code /auth/refresh} 改为要求 aud， 全部在线用户会在 refresh 时被登出。加 aud
 *       的收益（App 侧自证身份）远小于踢掉所有在线用户的代价；
 *   <li>控制台侧另有独立闸门：{@code ConsoleJwtService.parse} 强制校验 {@code aud=vocalverse-console} 且 {@code
 *       typ=console-access}。两侧合起来才能双向隔离。
 * </ol>
 *
 * <p>{@code typ=console-access} 也被显式检查：万一将来有人把控制台受众名改成本服务的，typ 仍能兜住。
 */
public class JwtAuthFilter extends OncePerRequestFilter {

  private static final int CODE_UNAUTH = 40101;

  /**
   * 本服务认可的 {@code aud} 取值。
   *
   * <p>既有 App 令牌无 aud（放行）；显式声明 {@code vocalverse-app} 的令牌也放行（为将来 App 令牌加 aud 留出兼容位，届时只需在 {@code
   * JwtService} 里加 claim，本过滤器不用改）。
   */
  private static final java.util.Set<String> APP_AUDIENCES =
      java.util.Set.of("vocalverse-app", "vocalverse-java");

  private final JwtService jwt;
  private final UserRepository users;
  private final ObjectMapper mapper;

  public JwtAuthFilter(JwtService jwt, UserRepository users, ObjectMapper mapper) {
    this.jwt = jwt;
    this.users = users;
    this.mapper = mapper;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
      throws ServletException, IOException {
    // 内部域（/internal/**）由 ServiceTokenFilter 处理：这里的 Authorization 是服务令牌，
    // 不是 JWT——解析失败不得 clearContext（会抹掉 ServiceTokenFilter 刚设置的 ROLE_SERVICE，
    // 导致内部端点 403；2026-09-06 修复，见 InternalCheckinApiTest 回归）。
    if (request.getRequestURI().startsWith("/internal/")) {
      filterChain.doFilter(request, response);
      return;
    }
    String header = request.getHeader("Authorization");
    if (header != null && header.startsWith("Bearer ")) {
      try {
        Claims claims = jwt.parse(header.substring(7));
        if (isForeignToken(claims)) {
          // 控制台令牌（或任何带外来 aud 的令牌）→ 匿名，由 SecurityFilterChain 拒绝（40101/40301）
          SecurityContextHolder.clearContext();
          filterChain.doFilter(request, response);
          return;
        }
        Long userId = Long.parseLong(claims.getSubject());
        // J-02：禁用即时生效——已签发未过期 token 在 status != active 时立即失效
        // （findById 为 PK 命中；已删除用户同样 401，防「注销后 token 诈尸」）。
        UserEntity user = users.findById(userId).orElse(null);
        if (user == null || !"active".equals(user.getStatus())) {
          SecurityContextHolder.clearContext();
          reject(response, "账号已停用或不存在");
          return;
        }
        String role = claims.get("role", String.class);
        String authority = "ROLE_" + (role == null ? "USER" : role.toUpperCase());
        var auth =
            new UsernamePasswordAuthenticationToken(
                userId, null, List.of(new SimpleGrantedAuthority(authority)));
        SecurityContextHolder.getContext().setAuthentication(auth);
        request.setAttribute("userId", userId);
      } catch (JwtException | IllegalArgumentException e) {
        SecurityContextHolder.clearContext(); // 无令牌/非法令牌 → 匿名，由 SecurityFilterChain 拒绝
      }
    }
    filterChain.doFilter(request, response);
  }

  /**
   * 是否属于**其他受众**的令牌（跨端隔离闸门）。
   *
   * <p>判定：{@code typ=console-access} → 是；或存在 {@code aud} 且与 {@link #APP_AUDIENCES} 无交集 → 是。 无 aud
   * 且无 typ 的既有 App 令牌 → 不是（向后兼容）。
   */
  static boolean isForeignToken(Claims claims) {
    if ("console-access".equals(claims.get("typ", String.class))) {
      return true;
    }
    Object raw = claims.get("aud");
    if (raw == null) {
      return false;
    }
    java.util.Set<String> auds = new java.util.HashSet<>();
    if (raw instanceof String s) {
      auds.add(s);
    } else if (raw instanceof java.util.Collection<?> c) {
      for (Object o : c) {
        if (o != null) {
          auds.add(String.valueOf(o));
        }
      }
    } else {
      auds.add(String.valueOf(raw));
    }
    for (String a : auds) {
      if (APP_AUDIENCES.contains(a)) {
        return false;
      }
    }
    return true;
  }

  /** 401 + Envelope{40101}（过滤器层无法走 @RestControllerAdvice，显式写 JSON 响应）。 */
  private void reject(HttpServletResponse response, String message) throws IOException {
    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write(mapper.writeValueAsString(Envelope.error(CODE_UNAUTH, message)));
  }
}
