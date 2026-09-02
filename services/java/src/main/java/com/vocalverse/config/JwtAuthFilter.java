package com.vocalverse.config;

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
 * JWT 请求过滤器：解析 Bearer 令牌 → 写入 SecurityContext（principal=userId，authority=ROLE_&lt;role&gt;）与
 * request attr。role 来自 JWT claim（2026-09 起签发），无 role claim 的旧令牌按 ROLE_USER 处理。
 */
public class JwtAuthFilter extends OncePerRequestFilter {

  private final JwtService jwt;

  public JwtAuthFilter(JwtService jwt) {
    this.jwt = jwt;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
      throws ServletException, IOException {
    String header = request.getHeader("Authorization");
    if (header != null && header.startsWith("Bearer ")) {
      try {
        Claims claims = jwt.parse(header.substring(7));
        Long userId = Long.parseLong(claims.getSubject());
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
}
