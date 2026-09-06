package com.vocalverse.community;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * 帖子仓库（Java 写方唯一入口；计数增减为原子 @Modifying，与互动行写入同事务）。
 *
 * <p>feed 用 JPA Criteria（Java 侧判空）而非 JPQL `:param IS NULL`——首屏三参全 null 时， PostgreSQL 无法推断未类型化 NULL
 * 参数（42P18 could not determine data type of parameter）， H2 容忍、PG 拒绝（2026-09-06 实测修复；JPQL 版在 H2
 * 单测全绿、真机 500）。排序由 Pageable 携带（DESC created_at,id / ASC 详见注释）。
 */
public interface PostRepository
    extends JpaRepository<PostEntity, Long>, JpaSpecificationExecutor<PostEntity> {

  Optional<PostEntity> findFirstBySlug(String slug);

  Optional<PostEntity> findFirstByAuthorIdAndCheckinDate(Long authorId, java.time.LocalDate date);

  Optional<PostEntity> findFirstByAuthorIdAndCheckinDateAndKind(
      Long authorId, java.time.LocalDate date, String kind);

  /** keyset 分页（(created_at, id) DESC）：domain 为 null = 全量混排；ts/id 为 null = 首页。 */
  default List<PostEntity> feed(String domain, Instant ts, Long id, Pageable pageable) {
    return findAll(
            (root, query, cb) -> {
              List<jakarta.persistence.criteria.Predicate> ps = new ArrayList<>();
              ps.add(cb.equal(root.get("status"), "visible"));
              if (domain != null) {
                ps.add(cb.equal(root.get("domain"), domain));
              }
              if (ts != null) {
                ps.add(
                    cb.or(
                        cb.lessThan(root.get("createdAt"), ts),
                        cb.and(
                            cb.equal(root.get("createdAt"), ts), cb.lessThan(root.get("id"), id))));
              }
              return cb.and(ps.toArray(new jakarta.persistence.criteria.Predicate[0]));
            },
            pageable)
        .getContent();
  }

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
