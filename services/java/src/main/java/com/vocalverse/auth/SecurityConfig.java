package com.vocalverse.auth;

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
 * 安全策略（docs/18 §3-J1）：/auth/** 开放；其余需 JWT；/internal/** 需 service-token （Python 侧回写委托，docs/06 §2.2
 * 内部 REST）。全部按**网关剥离 /manage 后**的路径匹配。
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

  private final JwtService jwt;
  private final String serviceToken;

  public SecurityConfig(JwtService jwt, @Value("${vocalverse.service-token}") String serviceToken) {
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
                        "/auth/**",
                        "/v3/api-docs/**",
                        "/swagger-ui/**",
                        "/swagger-ui.html",
                        "/actuator/health",
                        "/error")
                    .permitAll()
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
