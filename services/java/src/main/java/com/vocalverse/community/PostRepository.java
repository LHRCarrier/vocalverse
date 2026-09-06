package com.vocalverse.community;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 帖子仓库（Java 写方唯一入口；计数增减为原子 @Modifying，与互动行写入同事务）。 */
public interface PostRepository extends JpaRepository<PostEntity, Long> {

  Optional<PostEntity> findFirstBySlug(String slug);

  Optional<PostEntity> findFirstByAuthorIdAndCheckinDate(Long authorId, java.time.LocalDate date);

  Optional<PostEntity> findFirstByAuthorIdAndCheckinDateAndKind(
      Long authorId, java.time.LocalDate date, String kind);

  /**
   * 领域流（keyset）：domain 过滤 + (created_at, id) DESC 游标。
   *
   * <p>domain 为 NULL 时返回全量（含打卡卡 NULL domain）。JPQL 的 (:domain IS NULL OR ...) 在 H2/PG 均可参数化；游标条件按
   * (ts,id) 双键比较。
   */
  @Query(
      "SELECT p FROM PostEntity p "
          + "WHERE p.status = 'visible' "
          + "AND (:domain IS NULL OR p.domain = :domain) "
          + "AND (:ts IS NULL OR (p.createdAt < :ts OR (p.createdAt = :ts AND p.id < :id))) "
          + "ORDER BY p.createdAt DESC, p.id DESC")
  List<PostEntity> feed(
      @Param("domain") String domain,
      @Param("ts") Instant ts,
      @Param("id") Long id,
      org.springframework.data.domain.Pageable pageable);

  @Query("SELECT p FROM PostEntity p WHERE p.status = 'visible' AND p.id = :id")
  Optional<PostEntity> findVisible(@Param("id") Long id);

  /** 计数原子自增（同事务；status='visible' 条件防软删内容继续累计；清缓存保证回读新值）。 */
  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "UPDATE PostEntity p SET p.likeCount = p.likeCount + 1 WHERE p.id = :id AND p.status = 'visible'")
  int incrementLike(@Param("id") Long id);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      value =
          "UPDATE posts SET like_count = GREATEST(like_count - 1, 0) "
              + "WHERE id = :id AND status = 'visible'",
      nativeQuery = true)
  int decrementLike(@Param("id") Long id);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "UPDATE PostEntity p SET p.coinCount = p.coinCount + 1 WHERE p.id = :id AND p.status = 'visible'")
  int incrementCoin(@Param("id") Long id);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "UPDATE PostEntity p SET p.shareCount = p.shareCount + 1 WHERE p.id = :id AND p.status = 'visible'")
  int incrementShare(@Param("id") Long id);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "UPDATE PostEntity p SET p.commentCount = p.commentCount + 1 WHERE p.id = :id AND p.status = 'visible'")
  int incrementComment(@Param("id") Long id);
}
