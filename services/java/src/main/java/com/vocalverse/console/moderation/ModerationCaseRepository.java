package com.vocalverse.console.moderation;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * 审核工单仓库（docs/50 §5.3.8）。
 *
 * <p><b>决定必须走 {@link #decide} 的条件 UPDATE</b>（{@code WHERE status='pending'}）——这是 docs/50 §6.2 的
 * 竞态要求：两个并发决定只有一个能改到行，另一个 {@code rowsAffected=0} → 46010。 read-modify-write（先 findById 再
 * setStatus）在 READ COMMITTED 下会让两个请求都成功。
 */
public interface ModerationCaseRepository extends JpaRepository<ModerationCaseEntity, Long> {

  @Query(
      "select c from ModerationCaseEntity c "
          + "where (:status is null or c.status = :status) "
          + "and (:targetType is null or c.targetType = :targetType) "
          + "and (:priority is null or c.priority = :priority) "
          + "and (:assigneeId is null or c.assigneeId = :assigneeId) "
          + "order by c.priority asc, c.id desc")
  Page<ModerationCaseEntity> search(
      @Param("status") String status,
      @Param("targetType") String targetType,
      @Param("priority") Short priority,
      @Param("assigneeId") Long assigneeId,
      Pageable pageable);

  /** 待审/升级单查重（部分唯一索引在 H2 不可建 → 服务层兜底，同 docs/37 uq_posts_checkin 处置）。 */
  @Query(
      "select c from ModerationCaseEntity c "
          + "where c.targetType = :targetType and c.targetId = :targetId "
          + "and c.status in ('pending','escalated') "
          + "order by c.id asc")
  List<ModerationCaseEntity> findOpen(
      @Param("targetType") String targetType, @Param("targetId") Long targetId);

  Optional<ModerationCaseEntity> findFirstByTargetTypeAndTargetIdOrderByIdAsc(
      String targetType, Long targetId);

  /**
   * 原子决定（docs/50 §6.2）：条件 UPDATE + 状态推进。
   *
   * <p>返回 0 行 = 该单已处于终态 / 已被并发决定 / 不存在 → 调用方抛 46010。
   *
   * <p><b>{@code status NOT IN ('approved','rejected','withdrawn')} 而非 {@code
   * status='pending'}</b>： docs/50 §6.2 的表格说「{@code escalate} → {@code
   * escalated}（+priority=1），保持队列中」—— 升级后仍要能被处置， 所以 {@code escalated} 必须可决定。写死 {@code ='pending'}
   * 会让升级过的单永久卡死（终态除外）。
   *
   * <p><b>为什么没有「目标状态 CAS」条件（2026-09-10 移除，实测事故）</b>：原先有一条 {@code and (:currentStatus is null or
   * :currentStatus <> coalesce(:targetStatus, :currentStatus))}， 目的是「目标若已被别人改过则整笔 46010」。它有两个致命问题：
   *
   * <ol>
   *   <li><b>它在语义上不成立</b>：本 UPDATE 只动 {@code moderation_cases}，两个参数都是**查询期已知的常量**， 比较结果对同一次调用是恒定的
   *       —— 它既读不到目标表，也就不可能检测到"别人改了目标"。当目标未被改动时 （approve/reject/escalate，占多数）该条件恒为 false → 0 行 →
   *       **所有决定都误报 46010**；
   *   <li><b>它在 Hibernate 上直接报错</b>：{@code coalesce} 的两个参数都可为 null 时无法做类型推断， 抛出 {@code
   *       JpaSystemException: Unknown data type: "?"} → 决定路径一律 50002 （{@code
   *       ModerationHiddenContentTest} 5 例、{@code ModerationConcurrencyTest} 2 例因此全红）。
   * </ol>
   *
   * <p><b>真正的并发保护在哪</b>：① 审单层面由本方法的 {@code not in (终态)} 条件 UPDATE 提供（0 行 → 46010， 这是 DB 侧 CAS）；②
   * 目标层面由 {@link ModerationService} 在**写目标之前**于同一事务内读取目标状态、 并在「目标已是 hidden/deleted 却要
   * hide/delete」时显式拒绝（防 hide/delete 互相复活）。 若要更进一步做目标级 CAS，正确做法是让**目标表的 UPDATE 自身**带上 {@code where
   * status = :expectedStatus} 并检查行数 —— 而不是在审单的 UPDATE 里比较两个参数。
   */
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      "update ModerationCaseEntity c set c.status = :nextStatus, c.decidedBy = :decidedBy, "
          + "c.decidedAt = :now, c.decisionNote = :note, "
          + "c.priority = :nextPriority, "
          + "c.updatedAt = :now "
          + "where c.id = :id and c.status not in ('approved','rejected','withdrawn')")
  int decide(
      @Param("id") Long id,
      @Param("nextStatus") String nextStatus,
      @Param("decidedBy") Long decidedBy,
      @Param("note") String note,
      @Param("nextPriority") short nextPriority,
      @Param("now") Instant now);

  /** 指派（不改状态；终态单同样拒绝 → 0 行）。 */
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      "update ModerationCaseEntity c set c.assigneeId = :assigneeId, c.updatedAt = :now "
          + "where c.id = :id and c.status in ('pending','escalated')")
  int assign(@Param("id") Long id, @Param("assigneeId") Long assigneeId, @Param("now") Instant now);

  long countByStatus(String status);

  @Query(
      "select c.status as status, count(c) as total from ModerationCaseEntity c group by c.status")
  List<Object[]> countGroupByStatus();

  @Query(
      "select count(c) from ModerationCaseEntity c "
          + "where c.targetType = :targetType and c.targetId = :targetId "
          + "and c.status in ('pending','escalated')")
  long countOpenForTarget(@Param("targetType") String targetType, @Param("targetId") Long targetId);

  // ------------------------------------------------------------------ 看板聚合（docs/50 §10.2
  // /moderation/stats）

  /**
   * 看板数据源：窗口内的「建单时间 + 决定时间 + 终态」三列。
   *
   * <p><b>为什么把日期分桶放在 Java 而不是 SQL</b>：{@code DATE(created_at)} 的正确写法依方言而变 （PG 用 {@code CAST(x AS
   * date)} / {@code date_trunc}，H2 两者行为不同），写死任一种都会在另一端 静默算错或直接报错 —— 本仓已有同类踩坑（docs/37 §9「H2 单测绿、真 PG
   * 500」）。 控制台看板是**低频、小数据量**（窗口内最多几千行）的场景，取回三列在服务层分桶 既方言无关又能单元测试。窗口上限由服务层钳制（见 {@code
   * ModerationService.stats}）。
   */
  @Query(
      "select c.createdAt, c.decidedAt, c.status from ModerationCaseEntity c "
          + "where c.createdAt >= :since or c.decidedAt >= :since")
  List<Object[]> statsRows(@Param("since") Instant since);
}
