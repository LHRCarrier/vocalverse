package com.vocalverse.community;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 点赞事实表（Java 写方；(post_id, liker_id) 唯一兜底幂等）。 */
public interface PostLikeRepository extends JpaRepository<PostLikeEntity, Long> {

  Optional<PostLikeEntity> findByPostIdAndLikerId(Long postId, Long likerId);

  List<PostLikeEntity> findByLikerIdAndPostIdIn(Long likerId, List<Long> postIds);

  /**
   * 唯一键原子幂等插入（J-01）：返回 1=本次插入；0=并发/重复已存在（不双计、不报错）。
   *
   * <p>{@code INSERT ... ON CONFLICT DO NOTHING} 由 DB 原子兜底，替代「先查后插」的 check-then-act
   * 竞态窗口（PG 默认 READ COMMITTED 下两次并发 like 会双双查空 → 第二个 INSERT 撞唯一键 →
   * 未捕获 DataIntegrityViolationException → 500）。H2（MODE=PostgreSQL）与 PG 双方言均支持
   * 无目标 {@code ON CONFLICT DO NOTHING}（2026-09-08 实测 H2 2.2.224）。
   */
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      value =
          "INSERT INTO post_likes (post_id, liker_id, created_at) "
              + "VALUES (:postId, :likerId, :createdAt) ON CONFLICT DO NOTHING",
      nativeQuery = true)
  int insertIgnoreConflict(
      @Param("postId") Long postId,
      @Param("likerId") Long likerId,
      @Param("createdAt") Instant createdAt);

  /**
   * 原子删行（J-01）：返回实际删除行数（0/1）—— unlike 只在返回 1（事实行真实存在）时才递减计数，
   * 防并发双击取消重复减计数导致 like_count 与事实行长期漂移。
   */
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query(
      value = "DELETE FROM post_likes WHERE post_id = :postId AND liker_id = :likerId",
      nativeQuery = true)
  int deleteOneByPostIdAndLikerId(@Param("postId") Long postId, @Param("likerId") Long likerId);
}
