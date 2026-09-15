package com.vocalverse.console.rbac;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 声明端点所需权限码（docs/50 §10.2 每个端点都标注了所需码；§4.3 硬规则：前端裁剪永远不构成授权）。
 *
 * <p>由 {@link ConsolePermissionInterceptor} 在 handler 执行前强制校验，缺码 → 46002 + {@code data.required}。
 *
 * <p><b>为什么用注解而不是路径匹配</b>：路径规则在端点增删时会静默失配（新增端点忘了加规则 = 默认放行）。 注解与代码同处一地，改端点的同一次编辑就会看到它，且 {@code
 * ConsolePermissionCoverageTest} 可以断言「每个 console 端点都标了码」——路径方案做不到这种自证。
 */
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface RequireConsolePermission {

  /** 所需权限码（{@link PermissionCatalog} 常量）。 */
  String value();
}
