package com.vocalverse.content;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ListeningMaterialRepository extends JpaRepository<ListeningMaterialEntity, Long> {

  /** {@code cast} 理由见 {@code AdminAuditLogRepository#search}（2026-09-10 真 PG 实测缺陷）。 */
  @Query(
      "select l from ListeningMaterialEntity l "
          + "where (cast(:status as string) is null or l.status = :status) order by l.id desc")
  Page<ListeningMaterialEntity> search(@Param("status") String status, Pageable pageable);
}
