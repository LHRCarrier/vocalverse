package com.vocalverse.community;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/** 互动时序单（Java 写方；like/coin/share 唯一 (actor, post, action) 幂等）。 */
public interface PostInteractionRepository extends JpaRepository<PostInteractionEntity, Long> {

  Optional<PostInteractionEntity> findByActorIdAndPostIdAndAction(
      Long actorId, Long postId, String action);

  List<PostInteractionEntity> findByActorIdAndPostIdInAndAction(
      Long actorId, List<Long> postIds, String action);

  void deleteByActorIdAndPostIdAndAction(Long actorId, Long postId, String action);
}
