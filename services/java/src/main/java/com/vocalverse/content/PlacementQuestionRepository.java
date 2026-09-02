package com.vocalverse.content;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface PlacementQuestionRepository extends JpaRepository<PlacementQuestionEntity, Long> {

  List<PlacementQuestionEntity> findByExamRevisionOrderByItemIndexAsc(Integer examRevision);

  boolean existsByExamRevisionAndItemIndex(Integer examRevision, Integer itemIndex);

  /** 当前最大题库版本；空表返回 0（Java 侧再 +1 作新版本）。 */
  @Query("select coalesce(max(p.examRevision), 0) from PlacementQuestionEntity p")
  Integer maxExamRevision();
}
