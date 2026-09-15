package com.vocalverse.console.auth;

import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.MethodParameter;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

/**
 * 把当前控制台主体注入 controller 参数（{@code @CurrentAdmin ConsolePrincipal me}）。
 *
 * <p>等价于既有 {@code @RequestAttribute("userId")} 的用法，但携带 roleCode/perms —— 审计与授权都需要， 从 request
 * attribute 逐个取会在每个 controller 里重复四行样板。
 *
 * <p>主体由 {@link ConsoleSecurityFilter} 写入 request attribute；解析不到即抛 46001
 * （理论上到不了：受保护路径无主体时过滤器已拦截，这里是纵深防御）。
 */
public class CurrentAdminArgumentResolver implements HandlerMethodArgumentResolver {

  public static final String REQUEST_ATTRIBUTE = "consolePrincipal";

  @Override
  public boolean supportsParameter(MethodParameter parameter) {
    return parameter.hasParameterAnnotation(CurrentAdmin.class)
        && ConsolePrincipal.class.isAssignableFrom(parameter.getParameterType());
  }

  @Override
  public Object resolveArgument(
      MethodParameter parameter,
      ModelAndViewContainer mavContainer,
      NativeWebRequest webRequest,
      WebDataBinderFactory binderFactory) {
    Object principal = webRequest.getAttribute(REQUEST_ATTRIBUTE, NativeWebRequest.SCOPE_REQUEST);
    if (principal instanceof ConsolePrincipal p) {
      return p;
    }
    throw ConsoleException.of(ConsoleErrorCodes.UNAUTHENTICATED);
  }

  /** 供过滤器/审计读取当前请求主体。 */
  public static ConsolePrincipal from(HttpServletRequest request) {
    Object p = request.getAttribute(REQUEST_ATTRIBUTE);
    return p instanceof ConsolePrincipal cp ? cp : null;
  }
}
