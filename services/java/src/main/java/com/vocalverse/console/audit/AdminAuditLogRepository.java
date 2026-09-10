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
   */
  @Query(
      "select a from AdminAuditLogEntity a "
          + "where (:action is null or a.action = :action) "
          + "and (:actionPrefix is null or a.action like concat(:actionPrefix, '%')) "
          + "and (:targetType is null or a.targetType = :targetType) "
          + "and (:adminUserId is null or a.adminUserId = :adminUserId) "
          + "and (:result is null or a.result = :result) "
          + "and (:from is null or a.createdAt >= :from) "
          + "and (:to is null or a.createdAt <= :to) "
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

  /** 上架/下架流水（docs/50 §10.2 GET /content/publish-events）。 */
  @Query(
      "select a from AdminAuditLogEntity a "
          + "where a.action like 'content.%.publish' "
          + "and (:targetType is null or a.targetType = :targetType) "
          + "and (:from is null or a.createdAt >= :from) "
          + "and (:to is null or a.createdAt <= :to) "
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
