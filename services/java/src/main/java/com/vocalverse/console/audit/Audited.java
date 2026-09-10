package com.vocalverse.console.audit;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 标记「需要写审计」的写操作（docs/50 §5.3.7 / §9.3）。
 *
 * <p>由 {@link AuditAspect} 处理。语义：标注的方法**成功后**写一行 {@code admin_audit_logs}；
 * 抛异常时不写（异常路径的「denied/failed」留痕由控制器层的 {@link AuditService#recordDenied} 负责， 因为只有那一层才知道错误码）。
 *
 * <p><b>事务不变量</b>：审计行必须与业务写在同一事务里 —— 业务回滚则审计也必须消失， 业务成功则审计绝不可缺。{@link AuditAspect} 通过与
 * {@code @Transactional} 的 advice 排序保证这一点， 详见其类注释（这是本模块的硬约束，不是可选优化）。
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface Audited {

  /** 动作名（{@code domain.thing.verb} 形式，如 {@code moderation.decide}）。 */
  String action();

  /** 目标类型（docs/50 §5.3.7：song|scenario|listening_material|post|comment|admin_user|role|…）。 */
  String targetType() default "";

  /** 人类可读的一句话（写进 {@code summary}）。 */
  String summary() default "";

  /**
   * 目标 id 的参数名（方法参数中取该参数做 {@code target_id}）。
   *
   * <p>取 {@code SpEL} 会带来表达式求值开销与注入面，而审计只需要一个 id —— 按参数名取更简单也更好审计。 留空则 {@code target_id} 为空。
   */
  String targetIdParam() default "";
}
