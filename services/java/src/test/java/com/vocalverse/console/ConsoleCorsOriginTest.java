package com.vocalverse.console;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

/**
 * 控制台 CORS 白名单必须包含 **dev SPA 的端口 5174**（2026-09-10 实测缺陷的回归）。
 *
 * <h2>这个坑为什么"看着不像 CORS 问题"</h2>
 *
 * <p>控制台 dev server 走 Vite 代理，浏览器发的是**同源**请求（5174 → 5174），直觉上"代理已经 绕开 CORS 了"；但代理把 Host 改写成
 * 8080（{@code changeOrigin: true}）后**原样转发** {@code Origin: http://localhost:5174}，于是 Java 侧看到的是"请求打
 * 8080、来源 5174"—— Spring 按**跨源**处理并查白名单。原白名单只有 {@code apps/web} 的 5173，控制台的 5174 靠 {@code
 * VOICEVERSE_CONSOLE_CORS_ORIGINS} 追加，而那个变量只写在 {@code services/java/.env.example} 里（方式 B 下无人加载）→
 * 浏览器登录**必然 403**，且响应体是 Spring 的 "Invalid CORS request" **不是 Envelope**，前端只能显示"服务返回非标准响应（HTTP
 * 403）"—— 症状离原因很远。
 *
 * <p>本测试直接对 {@code consoleCorsConfigurationSource} 取配置来断言（不发真实请求、不需要起服务）： 5174
 * 必须被放行；未登记的源仍必须被拒（证明这是白名单而不是放开）。
 */
class ConsoleCorsOriginTest {

  /** 复刻 @Bean 方法的最小构造：它只用到传入的 origins 字符串，其余协作者不参与。 */
  private static CorsConfigurationSource source(String consoleOrigins) {
    ConsoleSecurityConfig config = new ConsoleSecurityConfig(null, null, null, true);
    return config.consoleCorsConfigurationSource(consoleOrigins);
  }

  private static CorsConfiguration configOf(CorsConfigurationSource source) {
    MockHttpServletRequest request =
        new MockHttpServletRequest("POST", "/api/v1/console/auth/login");
    CorsConfiguration cfg =
        ((UrlBasedCorsConfigurationSource) source).getCorsConfiguration(request);
    assertNotNull(cfg, "控制台路径必须能取到 CORS 配置");
    return cfg;
  }

  @Test
  void console_dev_origin_5174_is_allowed_without_any_env_config() {
    List<String> allowed = configOf(source("")).getAllowedOrigins();
    // 断言必须建立在"没配任何环境变量"的前提下 —— 这正是新克隆仓库的状态
    assertEquals(true, allowed.contains("http://localhost:5174"), "缺少 5174 会让浏览器登录 403：" + allowed);
    assertEquals(true, allowed.contains("http://127.0.0.1:5174"), "127.0.0.1 形态也要在：" + allowed);
    assertEquals(true, allowed.contains("http://localhost:5173"), "既有 apps/web 的 5173 不能被挤掉");
  }

  @Test
  void env_var_still_appends_extra_origins() {
    List<String> allowed =
        configOf(source("http://192.168.1.20:5174, http://10.0.0.5:5174")).getAllowedOrigins();
    assertEquals(true, allowed.contains("http://192.168.1.20:5174"), "环境变量追加失效：" + allowed);
    assertEquals(true, allowed.contains("http://10.0.0.5:5174"), "逗号分隔要 trim：" + allowed);
  }

  @Test
  void unknown_origin_is_not_allowed() {
    List<String> allowed = configOf(source("")).getAllowedOrigins();
    assertEquals(false, allowed.contains("http://evil.example.com"), "白名单不得放开：" + allowed);
    CorsConfiguration cfg = configOf(source(""));
    assertNull(
        cfg.checkOrigin("http://evil.example.com"), "未登记源必须被拒（Spring 的 checkOrigin 返回 null 即拒绝）");
    assertEquals(
        "http://localhost:5174",
        cfg.checkOrigin("http://localhost:5174"),
        "登记源必须回显（否则浏览器仍会判定 CORS 失败）");
  }
}
