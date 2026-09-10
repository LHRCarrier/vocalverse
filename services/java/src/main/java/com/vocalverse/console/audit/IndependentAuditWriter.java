package com.vocalverse.console.audit;

import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * **无业务事务**的审计写入器（登录成功、越权被拒、令牌重放告警、只读敏感内容读取）。
 *
 * <p>本类与 {@link AuditService} 的分工是刻意的，也是本模块审计正确性的一部分：
 *
 * <table border="1">
 *   <tr><th></th><th>{@link AuditService}</th><th>本类</th></tr>
 *   <tr><td>proparation</td><td>{@code MANDATORY}（必须有事务）</td><td>{@code REQUIRES_NEW}（自开事务）</td></tr>
 *   <tr><td>与业务写的原子性</td><td><b>同事务</b>：业务回滚 → 审计也无行</td><td>无业务事务；事件本身是既成事实</td></tr>
 *   <tr><td>被业务回滚带走？</td><td>是（这正是要的）</td><td><b>否</b>（「有人试图越权」不该因为业务失败而消失）</td></tr>
 * </table>
 *
 * <p><b>为什么必须分成两个类而不是在 {@code AuditService} 里加一个 {@code REQUIRES_NEW} 方法</b>： 只要 {@code
 * AuditService} 里存在任何一条 {@code REQUIRES_NEW} 路径，就存在「审计落在业务事务之外」的 可能性 —— 而 {@link AuditAspect}
 * 的全部设计目的就是消灭这种可能（见该类关于 {@code @Order} 的说明）。 把两种语义分到两个类，让 {@code AuditService} 可以被一句话审查完：
 * <b>它没有任何一条路径会在业务事务之外写审计</b>。
 *
 * <p>独立事务还带来一个必要性质：本类的写入不会被调用方未提交/已回滚的事务影响， 也不会因为业务异常把日志一起回滚掉。
 */
@Service
public class IndependentAuditWriter {

  private static final Logger log = LoggerFactory.getLogger(IndependentAuditWriter.class);

  private final AuditService audit;

  public IndependentAuditWriter(AuditService audit) {
    this.audit = audit;
  }

  /**
   * 独立事务写一行审计（{@code result=ok}）。
   *
   * <p>{@code REQUIRES_NEW}：挂起外层事务（若有），用一条新连接提交。
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void recordIndependent(
      Long adminUserId,
      String adminUsername,
      String action,
      String targetType,
      String targetId,
      String summary,
      Map<String, Object> detail) {
    audit.write(
        adminUserId,
        adminUsername,
        action,
        targetType,
        targetId,
        AdminAuditLogEntity.RESULT_OK,
        null,
        summary,
        detail,
        ConsoleRequestContext.clientIp());
  }

  /** 独立事务写一行「被拒」（{@code result=denied}）。 */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void recordDeniedIndependent(
      Long adminUserId,
      String adminUsername,
      String action,
      Integer errorCode,
      String summary,
      Map<String, Object> detail) {
    audit.write(
        adminUserId,
        adminUsername,
        action,
        null,
        null,
        AdminAuditLogEntity.RESULT_DENIED,
        errorCode,
        summary,
        detail,
        ConsoleRequestContext.clientIp());
  }

  /**
   * 只读敏感操作的审计（docs/50 §4.2 的 {@code ops:trace:content:read} 隐私闸门）。
   *
   * <p>独立事务 + **失败不改响应**：审计是旁路，读取内容本身已成功，不该因为审计写不进去而回 500。 但失败必须留痕（否则「审计静默失效」不可观测，违背 docs/50 §9.4）。
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void recordSensitiveRead(
      Long adminUserId,
      String adminUsername,
      String action,
      String targetType,
      String targetId,
      String summary) {
    audit.write(
        adminUserId,
        adminUsername,
        action,
        targetType,
        targetId,
        AdminAuditLogEntity.RESULT_OK,
        null,
        summary,
        Map.of("reasonCode", "sensitive_read"),
        ConsoleRequestContext.clientIp());
  }

  /**
   * 包裹一次「需要独立留痕」的调用；审计失败只记日志，不影响业务结果。
   *
   * <p>{@code REQUIRES_NEW} 是必须的：本方法内部还要调 {@link AuditService#write} （{@code
   * MANDATORY}），若这里没有事务，MANDATORY 会抛 {@code
   * IllegalTransactionStateException}。加在这里而不是指望「碰巧已经在外层事务里」—— 越权拒绝与登录成功恰恰是**没有**外层事务的场景。
   *
   * <p>放在这个委托方法而不是每个调用点：调用方（{@code ConsoleExceptionHandler}、{@code ConsoleAuthService}） 都写成 {@code
   * bestEffort(() -> writer.recordXxx(...), "name")}，加在这里等于一次覆盖所有调用点。
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void bestEffort(Runnable recorder, String what) {
    try {
      recorder.run();
    } catch (RuntimeException e) {
      log.warn("独立审计写入失败（{}）：{}", what, e.getMessage());
    }
  }
}
