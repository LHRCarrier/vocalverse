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
 * （principal=userId，authority=ROLE_&lt;role&gt;）与 request attr。role 来自 JWT claim（2026-09 起签发），
 * 无 role claim 的旧令牌按 ROLE_USER 处理。
 *
 * <p>J-02（2026-09-08）：status != 'active' 或用户已不存在 → 立即 401（Envelope 40101），不再等
 * access token 过期——修复「禁用不即时生效」：JwtAuthFilter 此前只验签不查库，disabled 用户在
 * access-ttl=3600 内仍可访问全部受保护端点。代价 = 每请求一次 PK 查库（本服务为薄管理端，
 * QPS 低，可承受；规模增长再上短 TTL 缓存 + 变更失效，登记 docs/18 J-02 后续项）。
 */
public class JwtAuthFilter extends OncePerRequestFilter {

  private static final int CODE_UNAUTH = 40101;

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

  /** 401 + Envelope{40101}（过滤器层无法走 @RestControllerAdvice，显式写 JSON 响应）。 */
  private void reject(HttpServletResponse response, String message) throws IOException {
    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write(mapper.writeValueAsString(Envelope.error(CODE_UNAUTH, message)));
  }
}
