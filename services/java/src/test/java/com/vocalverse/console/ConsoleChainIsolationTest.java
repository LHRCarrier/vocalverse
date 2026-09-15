package com.vocalverse.console;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.vocalverse.support.AbstractConsoleApiTest;
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.web.DefaultSecurityFilterChain;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

/**
 * 安全链隔离自证（P0-G ／ docs/50 §4）。
 *
 * <p>「新加一条链会不会影响既有鉴权」是本次交付风险最高的地方。本测试从**容器里的真实 {@link FilterChainProxy}** 取链列表断言四件事：
 *
 * <ol>
 *   <li>控制台链排第 0 位（{@code @Order(1)} 真的生效了 —— 若既有 catch-all 链排在前面， 控制台请求会被既有链先吞掉，表现为「控制台 403
 *       但代码看起来对」）；
 *   <li>控制台链的匹配器只吃 {@code /api/v1/console/**}；
 *   <li>{@code JwtAuthFilter} 在控制台链里**不存在**、在既有链里存在；
 *   <li>两个自定义过滤器都**不在** Servlet 容器注册表（不是 {@code @Component} → Boot 不会全局注册）。
 * </ol>
 */
class ConsoleChainIsolationTest extends AbstractConsoleApiTest {

  @Autowired private FilterChainProxy springSecurityFilterChain;
  @Autowired private org.springframework.beans.factory.ListableBeanFactory beanFactory;

  private List<SecurityFilterChain> chains() {
    List<SecurityFilterChain> all = springSecurityFilterChain.getFilterChains();
    assertTrue(all.size() >= 2, "应至少有控制台链 + 既有链：实际 " + all.size());
    return all;
  }

  private static RequestMatcher matcherOf(SecurityFilterChain chain) {
    assertTrue(
        chain instanceof DefaultSecurityFilterChain,
        "本仓的两条链都应是 DefaultSecurityFilterChain；实际 " + chain.getClass());
    return ((DefaultSecurityFilterChain) chain).getRequestMatcher();
  }

  /**
   * 构造可被 {@code AntPathRequestMatcher} 命中的请求。
   *
   * <p>必须显式设 `servletPath`：{@code AntPathRequestMatcher} 取的是 `getServletPath() + getPathInfo()`，而直接
   * `new MockHttpServletRequest(method, uri)` 只填了 requestURI、servletPath 为空 → 匹配恒为
   * false（本测试第一版就栽在这里， 表现为「前置断言失败」，让人误以为链的顺序错了）。
   */
  private static HttpServletRequest req(String path) {
    var r = new org.springframework.mock.web.MockHttpServletRequest("GET", path);
    r.setServletPath(path);
    r.setRequestURI(path);
    return r;
  }

  // ------------------------------------------------------------------ 顺序

  @Test
  void console_chain_is_first_in_the_proxy() {
    List<SecurityFilterChain> all = chains();
    SecurityFilterChain first = all.get(0);
    RequestMatcher consoleMatcher =
        new AntPathRequestMatcher(ConsoleSecurityConfig.CONSOLE_PREFIX + "/**");

    assertTrue(
        consoleMatcher.matches(req(ConsoleSecurityConfig.CONSOLE_PREFIX + "/auth/me")),
        "前置：定义用的匹配器应命中控制台路径");
    assertTrue(
        matcherOf(first).matches(req(ConsoleSecurityConfig.CONSOLE_PREFIX + "/auth/me")),
        "第 0 条链必须是控制台链（@Order(1) 未生效时，控制台请求会被既有链先处理）");
  }

  @Test
  void console_chain_matcher_scope_is_exact() {
    RequestMatcher m = matcherOf(chains().get(0));
    assertTrue(m.matches(req(ConsoleSecurityConfig.CONSOLE_PREFIX + "/auth/login")));
    assertTrue(m.matches(req(ConsoleSecurityConfig.CONSOLE_PREFIX + "/moderation/cases")));
    assertFalse(m.matches(req("/api/v1/admin/users")), "既有管理端路径不得被控制台链匹配");
    assertFalse(m.matches(req("/api/v1/community/posts")), "社区路径不得被控制台链匹配");
    assertFalse(m.matches(req("/auth/login")), "App 登录不得被控制台链匹配");
    assertFalse(m.matches(req("/api/v1/users/me")), "App 用户路径不得被控制台链匹配");
    assertFalse(m.matches(req("/internal/checkin")), "内部端点不得被控制台链匹配");
  }

  /** 既有链仍是 catch-all（未改动），因此既有路径行为不变。 */
  @Test
  void legacy_chain_still_covers_everything_else() {
    RequestMatcher legacy = matcherOf(chains().get(chains().size() - 1));
    assertTrue(legacy.matches(req("/api/v1/admin/users")));
    assertTrue(legacy.matches(req("/api/v1/community/posts")));
    assertTrue(legacy.matches(req("/auth/login")));
    assertTrue(legacy.matches(req("/api/v1/users/me")));
  }

  // ------------------------------------------------------------------ 过滤器隔离

  /** 既有 JwtAuthFilter 不在控制台链里 —— 这是「App 令牌不会误伤控制台」的结构性证据。 */
  @Test
  void jwt_auth_filter_absent_from_console_chain_present_in_legacy_chain() {
    List<Filter> consoleFilters = chains().get(0).getFilters();
    boolean consoleHasJwt =
        consoleFilters.stream().anyMatch(f -> f.getClass().getName().contains("JwtAuthFilter"));
    assertFalse(consoleHasJwt, "控制台链不得包含 JwtAuthFilter：" + consoleFilters);

    boolean legacyHasJwt =
        chains().stream()
            .skip(1)
            .flatMap(c -> c.getFilters().stream())
            .anyMatch(f -> f.getClass().getName().contains("JwtAuthFilter"));
    assertTrue(legacyHasJwt, "既有链必须仍然包含 JwtAuthFilter（既有行为未变）");

    boolean consoleHasConsoleFilter =
        consoleFilters.stream()
            .anyMatch(f -> f.getClass().getName().contains("ConsoleSecurityFilter"));
    assertTrue(consoleHasConsoleFilter, "控制台链必须包含 ConsoleSecurityFilter：" + consoleFilters);
  }

  /**
   * 两个自定义 JWT 过滤器都不得作为全局 servlet filter 注册。
   *
   * <p>这正是「{@code @Component} 的 Filter 会被 Boot 自动注册成全局过滤器」的陷阱 （本仓 {@code RequestIdFilter} 就是
   * {@code @Component}，它确实全局生效 —— 但它是幂等的头/MDC 处理， 与鉴权无关）。鉴权过滤器若被全局注册，会对**所有**请求生效，包括既有 App 路径。
   */
  @Test
  void auth_filters_are_not_globally_registered_as_servlet_filters() {
    String[] names =
        beanFactory.getBeanNamesForType(
            org.springframework.boot.web.servlet.FilterRegistrationBean.class);
    for (String n : names) {
      Object bean = beanFactory.getBean(n);
      if (bean instanceof org.springframework.boot.web.servlet.FilterRegistrationBean<?> frb) {
        String cls = frb.getFilter().getClass().getName();
        assertFalse(cls.contains("ConsoleSecurityFilter"), "控制台过滤器不得全局注册：" + n);
        assertFalse(cls.contains("JwtAuthFilter"), "既有 JWT 过滤器不得全局注册：" + n);
      }
    }

    // ConsoleSecurityFilter 本身也不该是容器里的 Filter bean（它是 new 出来的）
    String[] consoleFilterBeans =
        beanFactory.getBeanNamesForType(com.vocalverse.console.auth.ConsoleSecurityFilter.class);
    assertEquals(
        0, consoleFilterBeans.length, "ConsoleSecurityFilter 不应作为 bean 存在（应由 SecurityChain new 出）");
  }

  /** 控制台 CORS 源可配置，且既有源一个不少。 */
  @Test
  void cors_source_keeps_existing_origins() {
    assertNotNull(cors);
    var cfg = cors.getCorsConfiguration(req("/api/v1/console/auth/login"));
    assertNotNull(cfg);
    List<String> origins = cfg.getAllowedOrigins();
    for (String must :
        List.of("https://localhost", "http://localhost:5173", "http://192.168.0.104:8088")) {
      assertTrue(origins.contains(must), "既有源必须保留：" + must + "（实际 " + origins + "）");
    }
    assertTrue(cfg.getAllowCredentials(), "既有 allowCredentials=true 不得被改掉");
  }

  @Autowired private org.springframework.web.cors.CorsConfigurationSource cors;
}
