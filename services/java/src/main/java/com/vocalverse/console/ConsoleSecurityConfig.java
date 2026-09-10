package com.vocalverse.console;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.common.dto.Envelope;
import com.vocalverse.console.auth.ConsoleJwtService;
import com.vocalverse.console.auth.ConsoleSecurityFilter;
import com.vocalverse.console.rbac.AdminUserRepository;
import jakarta.servlet.http.HttpServletResponse;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

/**
 * 控制台安全链（docs/50 §4）。<b>本文件是本次交付风险最高的一处，改动理由逐条写在下面。</b>
 *
 * <h2>1. 为什么要新增一条链而不是改既有链</h2>
 *
 * <p>既有 {@code SecurityConfig.filterChain} 是一条 catch-all 链：{@code anyRequest().authenticated()}， 且
 * {@code /api/v1/admin/**} 走 {@code hasRole("ADMIN")}。控制台是**独立身份**（{@code admin_users} 表， 与 {@code
 * users} 无外键、无共享字段，docs/50 §4.1），所需的 authority、entry point、错误码（46xxx）全不同。
 * 把控制台塞进既有链会迫使既有链理解两种身份，是最容易改坏用户侧鉴权的做法。
 *
 * <p>新增链用 {@code securityMatcher("/api/v1/console/**")} + {@code @Order(1)}，既有链保持默认 order （{@code
 * LOWEST_PRECEDENCE}）→ <b>控制台链先匹配</b>，未匹配的请求原样落到既有链。 既有链的代码**一行未改**。
 *
 * <h2>2. 既有 JwtAuthFilter 不会跑在控制台路径上（已核实，两条独立证据）</h2>
 *
 * <ol>
 *   <li>{@code JwtAuthFilter} <b>不是 {@code @Component}</b>：它由 {@code SecurityConfig.filterChain} 里
 *       {@code new JwtAuthFilter(jwt, users, mapper)} 显式构造后 {@code addFilterBefore} 只加进
 *       <b>那一条</b>链。Spring Security 的 {@code FilterChainProxy} 按 {@code securityMatcher} 只执行 匹配链的
 *       filters → 控制台请求只跑本链的 filters；
 *   <li>它也不在 Servlet 容器注册表里：Boot 只自动注册**容器里的 Filter bean**，而这个实例是 new 出来的、 从未进入 {@code
 *       ApplicationContext} 的 bean 注册表，所以不存在「servlet 层先跑一遍再进安全链」的情况 （这正是「按 bean 注册 vs new
 *       出实例」的关键差别；本仓的 {@code RequestIdFilter} 是 {@code @Component}， 它确实会在 servlet 层跑一次，但那是幂等的请求头 /
 *       MDC 处理，与鉴权无关，且对既有路径与 控制台路径一视同仁 —— 不构成跨链行为差异）。
 * </ol>
 *
 * <p>为把话说死，{@code ConsoleAuthApiTest} 用 {@code @SpringBootTest} 起真实上下文断言： 有效 App token 打控制台路径 →
 * 46001；有效控制台 token 打 App 路径 → 被拒（40101 或 40301）。
 *
 * <h2>3. 错误体必须是 Envelope（不能是 Spring 默认错误页）</h2>
 *
 * <p>安全链的拒绝发生在 {@code @RestControllerAdvice} 之前（entry point / access denied handler 层）， 所以必须显式在链上挂
 * {@link #consoleEntryPoint} 与 {@link #consoleAccessDeniedHandler}， 否则前端拿到的是 Spring 默认的 {@code
 * {timestamp,status,error,path}} —— 与 Envelope 契约不符（docs/06 第 7 章 「任何返回必须过 Envelope」）。这也是既有 {@code
 * GlobalExceptionHandler} 类注释里登记的已知边界。
 *
 * <h2>4. CORS：控制台源可配置，既有源原样保留</h2>
 *
 * <p>既有 {@code corsConfigurationSource} 硬编码了 8 个源。按设计（§10.2 网关 {@code /manage/...}、独立 SPA 5174
 * 端口）控制台需要加入口，但**不该**在配置类里再加一个硬编码字面量。本类提供 {@link #consoleCorsConfigurationSource}（{@code @Primary}
 * 的首选源），它 <b>复用同一份既有源清单</b>，再追加 {@code vocalverse.console.cors-origins}（环境变量 {@code
 * VOICEVERSE_CONSOLE_CORS_ORIGINS}，逗号分隔）。 既有源一个不少、一个不改 —— 既有的 App 打包壳（{@code
 * https://localhost}）继续可用。
 *
 * <p><b>Bean 名为什么不能叫 {@code corsConfigurationSource}</b>：Spring Boot 2.1 起默认 {@code
 * allow-bean-definition-overriding=false}，第二个同名 Bean 会直接抛 {@code BeanDefinitionOverrideException}
 * 让**整个应用起不来**（实测踩到过：既有 App 的所有测试 一起变红，且报错信息指向 Bean 定义而不是本模块）。所以用一个独立名字 + {@code @Primary}
 * 来「成为首选」而不是「覆盖定义」。
 */
@Configuration
public class ConsoleSecurityConfig {

  private static final Logger log = LoggerFactory.getLogger(ConsoleSecurityConfig.class);

  /** 控制台前缀（网关剥离 /manage 后的路径；docs/50 §10.2）。 */
  public static final String CONSOLE_PREFIX = "/api/v1/console";

  /** 免鉴权端点（docs/50 §10.2：login / refresh 无需鉴权）。 */
  private static final String[] PUBLIC = {
    CONSOLE_PREFIX + "/auth/login", CONSOLE_PREFIX + "/auth/refresh"
  };

  /** 既有源清单（与 {@code SecurityConfig.corsConfigurationSource} 保持一致；此处只读不改那份代码）。 */
  private static final List<String> EXISTING_ORIGINS =
      List.of(
          "https://localhost",
          "http://localhost",
          "http://127.0.0.1",
          "http://localhost:5173",
          "http://127.0.0.1:5173",
          "http://192.168.0.104:5173",
          "http://192.168.0.104:8088",
          "http://localhost:8088");

  private final ConsoleJwtService jwt;
  private final AdminUserRepository adminUsers;
  private final ObjectMapper mapper;
  private final boolean consoleEnabled;

  public ConsoleSecurityConfig(
      ConsoleJwtService jwt,
      AdminUserRepository adminUsers,
      ObjectMapper mapper,
      @Value("${vocalverse.console.enabled:true}") boolean consoleEnabled) {
    this.jwt = jwt;
    this.adminUsers = adminUsers;
    this.mapper = mapper;
    this.consoleEnabled = consoleEnabled;
  }

  /**
   * 控制台安全链：{@code @Order(1)} → 先于既有 catch-all 链匹配。
   *
   * <p>{@code vocalverse.console.enabled=false} 时挂一个「显式关闭」过滤器： 所有控制台请求直接 46014（{@code
   * ops:overview:read} 系列的「通道未开启」语义）。 <b>为什么不干脆不注册这条链</b>：不注册的话控制台路径会落到既有 catch-all 链 （{@code
   * anyRequest().authenticated()}），请求者会拿到 401 而不是「未开启」—— 那会让「模块没开」看起来像「我令牌有问题」，排障方向完全错。
   * 同理也不用过滤器链整体禁用：明确拒绝比隐式 404/401 更好定位。
   */
  @Bean
  @Order(1)
  public SecurityFilterChain consoleFilterChain(HttpSecurity http) throws Exception {
    if (!consoleEnabled) {
      http.securityMatcher(CONSOLE_PREFIX + "/**")
          .csrf(csrf -> csrf.disable())
          .cors(Customizer.withDefaults())
          .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
          .exceptionHandling(
              ex ->
                  ex.authenticationEntryPoint(
                          (request, response, e) ->
                              writeJson(
                                  response,
                                  mapper,
                                  HttpServletResponse.SC_FORBIDDEN,
                                  ConsoleErrorCodes.TELEMETRY_DISABLED,
                                  "控制台模块未开启（vocalverse.console.enabled=false）"))
                      .accessDeniedHandler(
                          (request, response, e) ->
                              writeJson(
                                  response,
                                  mapper,
                                  HttpServletResponse.SC_FORBIDDEN,
                                  ConsoleErrorCodes.TELEMETRY_DISABLED,
                                  "控制台模块未开启（vocalverse.console.enabled=false）")));
      return http.build();
    }
    http.securityMatcher(CONSOLE_PREFIX + "/**")
        .csrf(csrf -> csrf.disable())
        .cors(Customizer.withDefaults())
        .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers(HttpMethod.OPTIONS, CONSOLE_PREFIX + "/**")
                    .permitAll() // 预检不带 Authorization，必须放行
                    .requestMatchers(PUBLIC)
                    .permitAll()
                    .anyRequest()
                    .hasAuthority("ROLE_CONSOLE"))
        .exceptionHandling(
            ex ->
                ex.authenticationEntryPoint(consoleEntryPoint(mapper))
                    .accessDeniedHandler(consoleAccessDeniedHandler(mapper)))
        .addFilterBefore(
            new ConsoleSecurityFilter(jwt, adminUsers, mapper),
            UsernamePasswordAuthenticationFilter.class);
    return http.build();
  }

  /** 未登录 → 401 + Envelope{46001}（前端据此跳**控制台**登录页，不是 App 登录页）。 */
  static AuthenticationEntryPoint consoleEntryPoint(ObjectMapper mapper) {
    return (request, response, ex) ->
        writeJson(
            response,
            mapper,
            HttpServletResponse.SC_UNAUTHORIZED,
            ConsoleErrorCodes.UNAUTHENTICATED,
            "管理端未登录或控制台令牌已失效");
  }

  /** 已登录但 authority 不符（理论上不会走到：权限码由拦截器判定）→ 403 + Envelope{46002}。 */
  static AccessDeniedHandler consoleAccessDeniedHandler(ObjectMapper mapper) {
    return (request, response, ex) ->
        writeJson(
            response,
            mapper,
            HttpServletResponse.SC_FORBIDDEN,
            ConsoleErrorCodes.PERMISSION_DENIED,
            "管理端权限不足");
  }

  private static void writeJson(
      HttpServletResponse response, ObjectMapper mapper, int status, int code, String message)
      throws java.io.IOException {
    response.setStatus(status);
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write(mapper.writeValueAsString(Envelope.error(code, message)));
  }

  /**
   * CORS 源清单：既有 8 个 + {@code vocalverse.console.cors-origins}（逗号分隔，可空）。
   *
   * <p><b>Bean 名刻意不叫 {@code corsConfigurationSource}</b>：与 {@code SecurityConfig} 的同名 Bean 冲突会抛
   * {@code BeanDefinitionOverrideException}（Boot 默认禁止覆盖），整个应用起不来。 用 {@code @Primary} 让 Spring
   * Security 的 {@code CorsConfigurer}（它按类型注入）取这一份； 既有 {@code
   * SecurityConfig.corsConfigurationSource} Bean 仍在容器里、内容一字未改。
   *
   * <p>两条链最终用的是同一份内容（既有源原样 + 控制台源追加），因此用户侧 CORS 行为不变。
   */
  @Bean
  @Primary
  public CorsConfigurationSource consoleCorsConfigurationSource(
      @Value("${vocalverse.console.cors-origins:}") String consoleOrigins) {
    List<String> origins = new ArrayList<>(EXISTING_ORIGINS);
    if (consoleOrigins != null && !consoleOrigins.isBlank()) {
      for (String o : consoleOrigins.split(",")) {
        String trimmed = o.trim();
        if (!trimmed.isEmpty() && !origins.contains(trimmed)) {
          origins.add(trimmed);
        }
      }
    }
    log.info("CORS 允许源（既有 + 控制台配置）：{}", origins);

    CorsConfiguration cfg = new CorsConfiguration();
    cfg.setAllowedOrigins(List.copyOf(origins));
    cfg.setAllowedMethods(List.of("*"));
    cfg.setAllowedHeaders(List.of("*"));
    cfg.setAllowCredentials(true);
    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", cfg);
    return source;
  }
}
