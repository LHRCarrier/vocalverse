package com.vocalverse.console.audit;

import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.auth.CurrentAdminArgumentResolver;
import jakarta.servlet.http.HttpServletRequest;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * {@link Audited} 的切面：把审计行写在**与业务写同一个事务**里（docs/50 §9.3 硬要求）。
 *
 * <h2>@Order 取值与它为什么保证不变量</h2>
 *
 * <p>两处 order 必须成对设置，缺一不可：
 *
 * <ul>
 *   <li>{@code ConsoleModuleConfig} 上的 {@code @EnableTransactionManagement(order =
 *       Ordered.HIGHEST_PRECEDENCE)} —— 事务切面排到<b>最内层</b>；
 *   <li>本切面的 {@code @Order(Ordered.HIGHEST_PRECEDENCE + 100)} —— 审计切面排在事务切面<b>外层</b>。
 * </ul>
 *
 * <pre>
 *   AuditAspect.around                       ← @Order(HIGHEST+100)，外层
 *     TransactionInterceptor                 ← @Order(HIGHEST)，开事务
 *       businessMethod()                     ← 业务写
 *     commit / rollback
 *   audit write                              ← 在事务内 → 已提交则行在，回滚则行无
 * </pre>
 *
 * <h2>为什么不能「什么都不设」（这是原来的真实缺陷）</h2>
 *
 * <p>{@code javap} 实测 spring-tx 6.1.14 的 {@code EnableTransactionManagement.order()} 默认值是 {@code
 * 2147483647}（= {@link Ordered#LOWEST_PRECEDENCE}），而一个普通 {@code @Aspect} 不写 {@code @Order}
 * 时拿到的也是同一个值 —— <b>两者相等时 AOP 的执行顺序是未定义的</b>（取决于 Bean 注册顺序，不是任何契约）。
 * 一旦事务切面跑在外层，审计写入就落在业务事务<b>之外</b>，业务回滚后审计行照样落库 → 审计记下一次并未发生的成功操作。「一本会撒谎的审计」比没有审计更糟：它会被当成证据。 所以这里把两处
 * order 都钉死，并用 {@code AuditTransactionInvariantTest} 双向验证。
 *
 * <p><b>反向保护</b>：{@link AuditService#record} 声明 {@code Propagation.MANDATORY}，所以万一有人改动了 这里的
 * order、或某个被标注的方法忘了 {@code @Transactional}，会在<b>第一次调用时立刻</b> 抛 {@code
 * IllegalTransactionStateException}（而不是悄悄写入一条自动提交的孤儿审计行）。 排序保证「正常路径正确」，MANDATORY
 * 保证「排序被改坏时立刻可见」——两道防线缺一不可。
 */
@Aspect
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 100)
public class AuditAspect {

  private final AuditService audit;

  public AuditAspect(AuditService audit) {
    this.audit = audit;
  }

  @Around("@annotation(audited)")
  public Object around(ProceedingJoinPoint pjp, Audited audited) throws Throwable {
    String targetId = resolveTargetId(pjp, audited.targetIdParam());
    ConsolePrincipal principal = currentPrincipal();
    try {
      Object result = pjp.proceed();
      // 业务已成功 → 写审计（同事务）。审计插入失败会让整个事务回滚，
      // 这正是 docs/50 §9.3 的要求：「宁可写不成功，不可无痕写成功」。
      audit.record(
          principal,
          audited.action(),
          blankToNull(audited.targetType()),
          targetId,
          blankToNull(audited.summary()),
          // detail 留空：切面不知道业务的前后状态（那是 Service 层才知道的事）。
          // 需要 detail 的地方直接在 Service 里调 AuditService.record(...)，同样是同事务写入。
          null);
      return result;
    } catch (Throwable t) {
      // 失败路径不写「成功」审计：异常会让事务回滚，此时任何写入都会一起消失（写也白写）。
      // 「被拒/失败」的留痕由 controller 层在**自己的**事务里用 recordFailed 落库 —— 那里才有错误码。
      throw t;
    }
  }

  /** 取 {@code targetIdParam} 指定的方法参数（按名字匹配；找不到返回 null）。 */
  private static String resolveTargetId(ProceedingJoinPoint pjp, String paramName) {
    if (paramName == null || paramName.isBlank()) {
      return null;
    }
    if (!(pjp.getSignature() instanceof MethodSignature sig)) {
      return null;
    }
    String[] names = sig.getParameterNames();
    Object[] args = pjp.getArgs();
    if (names == null) {
      return null;
    }
    for (int i = 0; i < names.length && i < args.length; i++) {
      if (paramName.equals(names[i]) && args[i] != null) {
        return String.valueOf(args[i]);
      }
    }
    return null;
  }

  private static ConsolePrincipal currentPrincipal() {
    HttpServletRequest req = ConsoleRequestContext.current();
    return req == null ? null : CurrentAdminArgumentResolver.from(req);
  }

  private static String blankToNull(String s) {
    return s == null || s.isBlank() ? null : s;
  }
}
