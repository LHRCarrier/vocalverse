package com.vocalverse.console;

import com.vocalverse.console.auth.CurrentAdminArgumentResolver;
import com.vocalverse.console.rbac.ConsolePermissionInterceptor;
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * 控制台 WebMvc 接线（docs/50 §3.3：{@code ConsoleModuleConfig}）。
 *
 * <p>三件事：
 *
 * <ol>
 *   <li>注册 {@link ConsolePermissionInterceptor}：只拦截 {@code /api/v1/console/**}，
 *       <b>不碰既有路径</b>（拦截器是按路径加的，模式里只有控制台前缀）；
 *   <li>注册 {@link CurrentAdminArgumentResolver}：让 controller 能写 {@code @CurrentAdmin
 *       ConsolePrincipal me}；
 *   <li><b>钉死事务切面的 order</b>（见下）。
 * </ol>
 *
 * <p>注意：{@code WebMvcConfigurer} 的实现会被应用全局共享，所以本类的 {@code addInterceptors} 必须严格限定路径 ——
 * 否则会在用户侧路由上引入控制台语义。
 *
 * <h2>为什么在这里写 @EnableTransactionManagement(order = HIGHEST_PRECEDENCE)</h2>
 *
 * <p>{@code javap} 实测 spring-tx 6.1.14：{@code EnableTransactionManagement.order()} 默认 {@code
 * 2147483647}（= {@code Ordered.LOWEST_PRECEDENCE}），与不写 {@code @Order} 的普通 {@code @Aspect}
 * <b>取值相同</b> → 两者的相对顺序未定义。{@code AuditAspect} 明确要跑在事务<b>外层</b>， 所以必须把事务切面钉到 {@code
 * HIGHEST_PRECEDENCE}（最内层），使其与 {@code AuditAspect} 的 {@code HIGHEST_PRECEDENCE + 100}
 * 形成确定的「审计在外、事务在内」结构。
 *
 * <p>副作用评估（只影响本模块的 Bean）：把事务切面排到最内层意味着其他切面（如本模块没有的 {@code @Cacheable}/{@code @Async}）会排在事务外层。{@code
 * com.vocalverse.console.*} 之外没有任何 切面参与（本仓 {@code @Aspect} 仅 {@code AuditAspect} 一个），既有模块的事务语义不受影响
 * —— 既有代码里没有任何 {@code @Aspect}，order 变化对它们不可观测。
 */
@Configuration
@EnableTransactionManagement(order = Ordered.HIGHEST_PRECEDENCE)
public class ConsoleModuleConfig implements WebMvcConfigurer {

  private final ConsolePermissionInterceptor permissionInterceptor;
  private final CurrentAdminArgumentResolver currentAdminResolver =
      new CurrentAdminArgumentResolver();

  public ConsoleModuleConfig(ConsolePermissionInterceptor permissionInterceptor) {
    this.permissionInterceptor = permissionInterceptor;
  }

  @Override
  public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(permissionInterceptor).addPathPatterns("/api/v1/console/**");
  }

  @Override
  public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
    resolvers.add(currentAdminResolver);
  }
}
