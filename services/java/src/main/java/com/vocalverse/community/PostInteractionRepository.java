package com.vocalverse.community;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 互动时序单（Java 写方；like/coin/share 唯一 (actor, post, action) 幂等）。 */
public interface PostInteractionRepository extends JpaRepository<PostInteractionEntity, Long> {

  Optional<PostInteractionEntity> findByActorIdAndPostIdAndAction(
      Long actorId, Long postId, String action);

  List<PostInteractionEntity> findByActorIdAndPostIdInAndAction(
      Long actorId, List<Long> postIds, String action);

  void deleteByActorIdAndPostIdAndAction(Long actorId, Long postId, String action);

  /**
   * 唯一键原子幂等插入（J-01）：返回 1=本次新增；0=已存在（重复请求返回当前态，不双计）。
   *
   * <p>DB 层 {@code ON CONFLICT DO NOTHING} 兜底，替代「先查后插 + catch DataIntegrityViolationException」：
   * 后者即便 catch 到冲突，Hibernate 已把当前事务标为 rollback-only，事务提交仍抛
   * UnexpectedRollbackException（真并发下 500 依旧）——由 DB 原子性彻底消除竞态窗口。
   */
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      value =
          "INSERT INTO post_interactions (actor_id, post_id, action, created_at) "
              + "VALUES (:actorId, :postId, :action, :createdAt) ON CONFLICT DO NOTHING",
      nativeQuery = true)
  int insertIgnoreConflict(
      @Param("actorId") Long actorId,
      @Param("postId") Long postId,
      @Param("action") String action,
      @Param("createdAt") Instant createdAt);

  /** S2 通知：指向我（作者）可见帖子的互动，按时间倒序取近 window。 */
  @Query(
      "SELECT i FROM PostInteractionEntity i "
          + "WHERE i.postId IN (SELECT p.id FROM PostEntity p WHERE p.authorId = :authorId AND p.status = 'visible') "
          + "ORDER BY i.createdAt DESC")
  List<PostInteractionEntity> findMine(@Param("authorId") Long authorId, Pageable pageable);
}
