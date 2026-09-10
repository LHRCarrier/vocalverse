package com.vocalverse.console.audit;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * 审计日志仓库（docs/50 §5.3.7）。append-only：本接口刻意**不声明任何 UPDATE/DELETE**。
 *
 * <p>{@code search} 供 {@code GET /console/audit-logs} 与 {@code GET /console/content/publish-events}
 * 共用（后者即「action like 'content.%.publish'」的派生视图，docs/50 §10.2 明确 publish-events 由审计日志派生）。
 */
public interface AdminAuditLogRepository extends JpaRepository<AdminAuditLogEntity, Long> {

  /**
   * 审计查询（docs/50 §10.2 GET /audit-logs）。
   *
   * <p><b>action 支持前缀匹配</b>（{@code actionPrefix}）：控制台需要「所有审核动作」 （{@code moderation.}
   * 前缀）这类聚合视图。只支持**精确相等**时前端只能逐码回扫再在客户端合并， 且总数只能标成「下界」——那是个真实的可用性缺陷，不是风格问题。
   *
   * <p>精度取舍：精确匹配与前缀匹配**互斥且精确优先**（{@code action} 非空时忽略 {@code actionPrefix}），
   * 避免两个参数同时给出时产生「或」的语义歧义（调用方本意不明时不该猜）。 前缀用 {@code concat(:actionPrefix, '%')} 而不是 {@code like
   * :actionPrefix} 拼字符串 —— 参数化前缀不会让调用方能注入通配符位置（{@code %}/{@code _} 仍会被当作通配符，
   * 但审计动作名是服务端常量，不来自用户输入，风险面为零）。
   *
   * <p><b>⚠️ 每个空值判断都必须写 {@code cast(:p as …)}</b>（2026-09-10 真 PG 实测，本仓同类第三次）： PostgreSQL 在 Parse
   * 阶段就要求确定每个 {@code $n} 的类型，而 `{@code ? is null}` 不提供类型线索； 参数为 NULL 时驱动也不补类型 OID（非 NULL 会补 ——
   * 所以**不带筛选反而必炸**， 「带筛选正常、清空筛选就 500」这种表现极容易把人引向错误方向）。 本查询 7 个参数全可空 ⇒ {@code GET
   * /api/v1/console/audit-logs} 清空筛选即 {@code could not determine data type of parameter $N} → 500。加
   * cast 后 PG 拿到 `{@code cast(? as varchar) is null}`，类型确定、语义逐字不变。
   */
  @Query(
      "select a from AdminAuditLogEntity a "
          + "where (cast(:action as string) is null or a.action = :action) "
          + "and (cast(:actionPrefix as string) is null or a.action like concat(cast(:actionPrefix as string), '%')) "
          + "and (cast(:targetType as string) is null or a.targetType = :targetType) "
          + "and (cast(:adminUserId as long) is null or a.adminUserId = :adminUserId) "
          + "and (cast(:result as string) is null or a.result = :result) "
          + "and (cast(:from as timestamp) is null or a.createdAt >= :from) "
          + "and (cast(:to as timestamp) is null or a.createdAt <= :to) "
          + "order by a.id desc")
  Page<AdminAuditLogEntity> search(
      @Param("action") String action,
      @Param("actionPrefix") String actionPrefix,
      @Param("targetType") String targetType,
      @Param("adminUserId") Long adminUserId,
      @Param("result") String result,
      @Param("from") Instant from,
      @Param("to") Instant to,
      Pageable pageable);

  /**
   * 上架/下架流水（docs/50 §10.2 GET /content/publish-events）。
   *
   * <p>{@code cast} 的理由见 {@link #search} 的长注释（PG 在 Parse 阶段要求参数类型）。
   * 本接口**没有**"参数为空就绕开查询"的分支（流水视图永远走这一条），所以清空筛选必然踩到 —— 实测 {@code GET
   * /content/publish-events?page_size=8} → 500 + {@code could not determine data type of parameter
   * $3}。
   */
  @Query(
      "select a from AdminAuditLogEntity a "
          + "where a.action like 'content.%.publish' "
          + "and (cast(:targetType as string) is null or a.targetType = :targetType) "
          + "and (cast(:from as timestamp) is null or a.createdAt >= :from) "
          + "and (cast(:to as timestamp) is null or a.createdAt <= :to) "
          + "order by a.id desc")
  Page<AdminAuditLogEntity> publishEvents(
      @Param("targetType") String targetType,
      @Param("from") Instant from,
      @Param("to") Instant to,
      Pageable pageable);

  /**
   * 审核单决定历史（docs/50 §5.3.7 单一审计流）：本表既是审计也是审核历史，{@code moderation_cases} 只存当前状态。
   *
   * <p>{@code targetId} 是字符串化列（媒体用 public_id），所以按字符串比较。
   */
  @Query(
      "select a from AdminAuditLogEntity a "
          + "where a.targetType = :targetType and a.targetId = :targetId "
          + "order by a.id asc")
  List<AdminAuditLogEntity> decisionHistory(
      @Param("targetType") String targetType, @Param("targetId") String targetId);
}
