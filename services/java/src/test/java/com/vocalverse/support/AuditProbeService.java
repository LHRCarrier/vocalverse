package com.vocalverse.support;

import com.vocalverse.console.audit.AuditService;
import com.vocalverse.console.auth.ConsolePrincipal;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 审计事务不变量的探测服务（test-only fixture）。
 *
 * <p>为什么需要它：验证「业务回滚 → 审计无行」必须有一个**真实的** {@code @Transactional} 业务方法， 在其中调 {@link
 * AuditService#record}（{@code MANDATORY}），然后抛异常。 直接调 {@code AuditService} 只能测到「无事务时 MANDATORY 抛错」，
 * 测不到 **AOP advice 顺序**（切面 vs 事务切面）这个真正的失效点。
 *
 * <p>放在 {@code com.vocalverse.support} 而非测试类内部类：Spring 的组件扫描不会扫测试类的嵌套类， 内部类上加 {@code @Service}
 * 不会有任何效果（会得到一个 NPE 而不是一个失败的断言）。
 */
@Service
public class AuditProbeService {

  private static final ConsolePrincipal PRINCIPAL =
      new ConsolePrincipal(1L, "audit-tester", "super", Set.of(), null);

  private final AuditService audit;

  public AuditProbeService(AuditService audit) {
    this.audit = audit;
  }

  /** 业务写成功后写审计并提交。 */
  @Transactional
  public void commitCase(String marker) {
    audit.record(
        PRINCIPAL,
        "test.commit",
        "test",
        "1",
        marker,
        Map.of("prevStatus", "pending", "nextStatus", "approved"));
  }

  /** 写审计后抛异常 → 整笔事务回滚，审计也不得残留。 */
  @Transactional
  public void rollbackCase(String marker) {
    audit.record(
        PRINCIPAL,
        "test.rollback",
        "test",
        "1",
        marker,
        Map.of("prevStatus", "pending", "nextStatus", "approved"));
    throw new IllegalStateException("business failure after audit");
  }
}
