package com.vocalverse.config;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * 安全策略（docs/18 §3-J1）：公开白名单仅 login/register/refresh/forgot（原 /auth/** 全开放， 2026-09-07
 * 收窄：/auth/logout、/auth/me 需 JWT —— logout 依 userId 吊销全部 refresh token）； 其余需 JWT；/internal/** 需
 * service-token（Python 侧回写委托，docs/06 §2.2 内部 REST）。 全部按**网关剥离 /manage 后**的路径匹配。
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

  private final JwtService jwt;
  private final String serviceToken;

  public SecurityConfig(JwtService jwt, @Value("${vocalverse.service-token}") String serviceToken) {
    // docs/19 P0-9：service-token 缺失 → 启动即失败（fail-fast）：内部委托端点双端契约依赖同值，
    // 空串会导致 /internal/** 全部 403 且难以定位（改由启动时显式报错）。
    if (serviceToken == null || serviceToken.isBlank()) {
      throw new IllegalStateException(
          "vocalverse.service-token 未配置：检查 SERVICE_TOKEN 环境变量（docs/19 P0-9）");
    }
    this.jwt = jwt;
    this.serviceToken = serviceToken;
  }

  @Bean
  public PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
  }

  @Bean
  public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http.csrf(csrf -> csrf.disable())
        .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers(
                        "/api/v1/ping",
                        "/auth/login",
                        "/auth/register",
                        "/auth/refresh",
                        "/auth/forgot",
                        "/v3/api-docs/**",
                        "/swagger-ui/**",
                        "/swagger-ui.html",
                        "/actuator/health",
                        "/error")
                    .permitAll()
                    // 管理端（docs/06 §9.6）：admin 角色专用；用户侧工单接口走 anyRequest().authenticated()
                    .requestMatchers("/api/v1/admin/**")
                    .hasRole("ADMIN")
                    .requestMatchers("/internal/**")
                    .hasRole("SERVICE")
                    .anyRequest()
                    .authenticated())
        .addFilterBefore(new JwtAuthFilter(jwt), UsernamePasswordAuthenticationFilter.class)
        .addFilterBefore(new ServiceTokenFilter(serviceToken), JwtAuthFilter.class);
    return http.build();
  }

  /** service-token 校验（仅匹配 /manage/internal/**；其余路径放行交给安全链）。 */
  static class ServiceTokenFilter implements Filter {

    private final String expected;

    ServiceTokenFilter(String expected) {
      this.expected = expected;
    }

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
        throws IOException, jakarta.servlet.ServletException {
      HttpServletRequest req = (HttpServletRequest) request;
      String path = req.getRequestURI();
      if (path.startsWith("/internal/")) {
        String header = req.getHeader("Authorization");
        if (header == null
            || !header.startsWith("Bearer ")
            || !header.substring(7).equals(expected)) {
          ((HttpServletResponse) response)
              .sendError(HttpServletResponse.SC_UNAUTHORIZED, "bad service token");
          return;
        }
        SecurityContextHolder.getContext()
            .setAuthentication(
                new UsernamePasswordAuthenticationToken(
                    "service", null, List.of(new SimpleGrantedAuthority("ROLE_SERVICE"))));
      }
      chain.doFilter(request, response);
    }
  }
}
