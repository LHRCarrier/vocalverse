package com.vocalverse.content;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ScenarioRepository extends JpaRepository<ScenarioEntity, Long> {

  /** 管理端列表：status/sceneType 可空过滤，按 id 倒序（新建在前）。 */
  @Query(
      "select s from ScenarioEntity s "
          + "where (:status is null or s.status = :status) "
          + "and (:sceneType is null or s.sceneType = :sceneType) "
          + "order by s.id desc")
  Page<ScenarioEntity> search(
      @Param("status") String status, @Param("sceneType") String sceneType, Pageable pageable);
}
