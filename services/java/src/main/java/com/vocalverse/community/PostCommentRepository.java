package com.vocalverse.community;

import java.time.Instant;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 评论仓库（Java 写方；展示过滤 status='visible'；keyset ASC 分页）。 */
public interface PostCommentRepository extends JpaRepository<PostCommentEntity, Long> {

  @Query(
      "SELECT c FROM PostCommentEntity c "
          + "WHERE c.postId = :postId AND c.status = 'visible' "
          + "AND (:ts IS NULL OR (c.createdAt > :ts OR (c.createdAt = :ts AND c.id > :id))) "
          + "ORDER BY c.createdAt ASC, c.id ASC")
  List<PostCommentEntity> page(
      @Param("postId") Long postId,
      @Param("ts") Instant ts,
      @Param("id") Long id,
      org.springframework.data.domain.Pageable pageable);
}
