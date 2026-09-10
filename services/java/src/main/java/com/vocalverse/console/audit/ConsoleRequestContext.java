package com.vocalverse.console.audit;

import com.vocalverse.common.trace.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.MDC;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/**
 * 当前 HTTP 请求的上下文（审计归因用：{@code ip} / {@code request_id}）。
 *
 * <p>docs/50 §9.2「断点 2」：控制台审计此前拿不到 request_id（因为没有审计日志）。这里直接读 {@code RequestIdFilter} 写进 MDC 的值 ——
 * <b>同源</b>，所以审计里的 {@code request_id} 与 access log、 响应头 {@code X-Request-Id} 必然一致，排障时可直接串起来。
 *
 * <p>无请求上下文（启动 seed、后台任务、单测直接调服务）时全部返回 null —— 审计仍会写，只是没有网络归因， 比「因为拿不到请求就抛异常」可用得多。
 */
public final class ConsoleRequestContext {

  private ConsoleRequestContext() {}

  public static HttpServletRequest current() {
    if (RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attrs) {
      return attrs.getRequest();
    }
    return null;
  }

  /** request_id：优先取 MDC（与日志/access log 同源），回退到请求头。 */
  public static String requestId() {
    String fromMdc = MDC.get(RequestIdFilter.MDC_KEY);
    if (fromMdc != null && !fromMdc.isBlank()) {
      return fromMdc;
    }
    HttpServletRequest req = current();
    return req == null ? null : req.getHeader(RequestIdFilter.HEADER);
  }

  /**
   * 客户端 IP（{@code varchar(45)} 容得下 IPv6）。
   *
   * <p>{@code X-Forwarded-For} 取**第一跳**：网关（nginx）已设置该头，直连时头不存在则用 remoteAddr。 注意该头可被客户端伪造 ——
   * 它只用于审计归因与限流统计，<b>不用于授权判定</b>。
   */
  public static String clientIp() {
    HttpServletRequest req = current();
    if (req == null) {
      return null;
    }
    String xff = req.getHeader("X-Forwarded-For");
    if (xff != null && !xff.isBlank()) {
      int comma = xff.indexOf(',');
      return (comma > 0 ? xff.substring(0, comma) : xff).trim();
    }
    String real = req.getHeader("X-Real-IP");
    if (real != null && !real.isBlank()) {
      return real.trim();
    }
    return req.getRemoteAddr();
  }

  public static String userAgent() {
    HttpServletRequest req = current();
    return req == null ? null : req.getHeader("User-Agent");
  }
}
