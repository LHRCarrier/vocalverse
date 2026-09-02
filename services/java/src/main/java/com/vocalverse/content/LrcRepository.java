package com.vocalverse.content;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LrcRepository extends JpaRepository<LrcEntity, Long> {

  List<LrcEntity> findBySongIdOrderBySeqAsc(Long songId);

  /** 「整首重写」删除旧行（Spring Data 派生删除自带事务）。 */
  void deleteBySongId(Long songId);
}
