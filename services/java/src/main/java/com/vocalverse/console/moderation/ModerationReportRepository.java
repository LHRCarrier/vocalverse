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

/** 举报仓库（docs/50 §5.3.9）。处理同样是条件 UPDATE（{@code WHERE status='pending'}），重复处理 → 46015。 */
public interface ModerationReportRepository extends JpaRepository<ModerationReportEntity, Long> {

  @Query(
      "select r from ModerationReportEntity r "
          + "where (:status is null or r.status = :status) "
          + "and (:targetType is null or r.targetType = :targetType) "
          + "order by r.id desc")
  Page<ModerationReportEntity> search(
      @Param("status") String status, @Param("targetType") String targetType, Pageable pageable);

  /** 同一举报人对同一目标的待处理记录（部分唯一索引的 H2 侧兜底 + 46015 幂等的判定源）。 */
  @Query(
      "select r from ModerationReportEntity r "
          + "where r.reporterUserId = :reporterUserId and r.targetType = :targetType "
          + "and r.targetId = :targetId and r.status = 'pending' "
          + "order by r.id asc")
  List<ModerationReportEntity> findPending(
      @Param("reporterUserId") Long reporterUserId,
      @Param("targetType") String targetType,
      @Param("targetId") Long targetId);

  Optional<ModerationReportEntity> findFirstByReporterUserIdAndTargetTypeAndTargetIdOrderByIdAsc(
      Long reporterUserId, String targetType, Long targetId);

  /** 同一目标下最早的一条举报（「判重」时必须指向一条**真实存在**的重复源，否则 duplicate 无关联可留）。 */
  Optional<ModerationReportEntity> findFirstByTargetTypeAndTargetIdOrderByIdAsc(
      String targetType, Long targetId);

  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      "update ModerationReportEntity r set r.status = :nextStatus, r.handledBy = :handledBy, "
          + "r.handledAt = :now, r.caseId = :caseId, r.updatedAt = :now "
          + "where r.id = :id and r.status = 'pending'")
  int handle(
      @Param("id") Long id,
      @Param("nextStatus") String nextStatus,
      @Param("handledBy") Long handledBy,
      @Param("caseId") Long caseId,
      @Param("now") Instant now);

  long countByStatus(String status);
}
