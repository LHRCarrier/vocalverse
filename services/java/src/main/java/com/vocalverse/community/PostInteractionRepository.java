package com.vocalverse.community;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 互动时序单（Java 写方；like/coin/share 唯一 (actor, post, action) 幂等）。 */
public interface PostInteractionRepository extends JpaRepository<PostInteractionEntity, Long> {

  Optional<PostInteractionEntity> findByActorIdAndPostIdAndAction(
      Long actorId, Long postId, String action);

  List<PostInteractionEntity> findByActorIdAndPostIdInAndAction(
      Long actorId, List<Long> postIds, String action);

  void deleteByActorIdAndPostIdAndAction(Long actorId, Long postId, String action);

  /** S2 通知：指向我（作者）可见帖子的互动，按时间倒序取近 window。 */
  @Query(
      "SELECT i FROM PostInteractionEntity i "
          + "WHERE i.postId IN (SELECT p.id FROM PostEntity p WHERE p.authorId = :authorId AND p.status = 'visible') "
          + "ORDER BY i.createdAt DESC")
  List<PostInteractionEntity> findMine(@Param("authorId") Long authorId, Pageable pageable);
}
