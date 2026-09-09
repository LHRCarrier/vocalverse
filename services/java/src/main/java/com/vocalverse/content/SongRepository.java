package com.vocalverse.content;

import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SongRepository extends JpaRepository<SongEntity, Long> {

  @Query(
      "select s from SongEntity s where (:status is null or s.status = :status) order by s.id desc")
  Page<SongEntity> search(@Param("status") String status, Pageable pageable);

  /** 种子幂等查重（SongSeeder：按 title 只增不改）。 */
  Optional<SongEntity> findByTitle(String title);
}
