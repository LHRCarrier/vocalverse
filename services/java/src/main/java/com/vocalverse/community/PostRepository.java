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
 *
 * <h2>统一可见谓词（2026-09-10 · 管理端隐藏功能落地）</h2>
 *
 * <p>本类所有「可见」判定从 {@code status = 'visible'} 改为 <b>{@code status NOT IN
 * ('hidden','deleted')}</b>（docs/50 §6.2 联动硬点 1 选的方案： 新增 {@code hidden} 语义可见性，而不是「隐藏时直接写
 * deleted」——后者会让「隐藏」与「删除」在库里 不可区分，恢复无从下手）。
 *
 * <p>注意：本类改动**只覆盖 PostRepository 的 8 处**，但那不是全部。隐藏若只改这里会**从通知中心泄漏** （帖子标题、评论正文、互动者都会被看到），所以同批还改了：
 * {@link PostCommentRepository}（评论列表）、{@link PostInteractionRepository}（通知聚合的两条原生 SQL）、 {@link
 * DirectMessageRepository}（防御性统一）、{@code CommunityService}（详情/作者可见性）。 判断「有没有漏」的方法不是数数量，而是全包 {@code
 * grep -rn visible}： 每一处都必须能回答「隐藏内容在这个读路径上会不会出现」。
 */
public interface PostRepository
    extends JpaRepository<PostEntity, Long>, JpaSpecificationExecutor<PostEntity> {

  Optional<PostEntity> findFirstBySlug(String slug);

  Optional<PostEntity> findFirstByAuthorIdAndCheckinDate(Long authorId, java.time.LocalDate date);

  Optional<PostEntity> findFirstByAuthorIdAndCheckinDateAndKind(
      Long authorId, java.time.LocalDate date, String kind);

  /**
   * keyset 分页（(created_at, id) DESC）：domain 为 null = 全量混排；ts/id 为 null = 首页； authorId 非 null =
   * 只看该作者（「我的发帖」，docs/47 §5.1 · 2026-09-09 组长实测补）。
   *
   * <p>作者视图同样过滤 hidden：docs/50 §6.2 联动硬点 3「{@code hidden} 对作者也隐藏」—— 作者改从「我的帖子」的 hidden
   * 状态位看到处置结果，而不是继续在正常列表里看到被封的内容。
   */
  default List<PostEntity> feed(
      String domain, Long authorId, Instant ts, Long id, Pageable pageable) {
    return findAll(
            (root, query, cb) -> {
              List<jakarta.persistence.criteria.Predicate> ps = new ArrayList<>();
              ps.add(visibleStatusPredicate(root, cb));
              if (domain != null) {
                ps.add(cb.equal(root.get("domain"), domain));
              }
              if (authorId != null) {
                ps.add(cb.equal(root.get("authorId"), authorId));
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

  /**
   * S2 关注流：仅关注作者的新内容（keyset DESC）。J-06：用相关 EXISTS 子查询（follower=:me AND followee=p.author_id）替代巨型
   * authorIds IN（关注集到数万时 IN 列表使索引失效/走 seq scan）； 空关注由调用方 countByFollowerId 快检短路。
   */
  default List<PostEntity> followingFeed(Long me, Instant ts, Long id, Pageable pageable) {
    return findAll(
            (root, query, cb) -> {
              List<jakarta.persistence.criteria.Predicate> ps = new ArrayList<>();
              ps.add(visibleStatusPredicate(root, cb));
              jakarta.persistence.criteria.Subquery<Long> sq = query.subquery(Long.class);
              jakarta.persistence.criteria.Root<FollowEntity> f = sq.from(FollowEntity.class);
              sq.select(f.get("followeeId"));
              sq.where(
                  cb.equal(f.get("followerId"), me),
                  cb.equal(f.get("followeeId"), root.get("authorId")));
              ps.add(cb.exists(sq));
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

  /** 统一可见谓词（Criteria 版）：{@code status NOT IN ('hidden','deleted')}。 */
  static jakarta.persistence.criteria.Predicate visibleStatusPredicate(
      jakarta.persistence.criteria.Root<PostEntity> root,
      jakarta.persistence.criteria.CriteriaBuilder cb) {
    return cb.not(root.get("status").in("hidden", "deleted"));
  }

  /** 帖子详情（docs/50 §6.2：隐藏后详情页也不可见）。 */
  @Query("SELECT p FROM PostEntity p WHERE p.status NOT IN ('hidden', 'deleted') AND p.id = :id")
  Optional<PostEntity> findVisible(@Param("id") Long id);

  /** 计数原子自增（同事务；可见性条件防软删/隐藏内容继续累计；清缓存保证回读新值）。 */
  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "UPDATE PostEntity p SET p.likeCount = p.likeCount + 1 "
          + "WHERE p.id = :id AND p.status NOT IN ('hidden', 'deleted')")
  int incrementLike(@Param("id") Long id);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      value =
          "UPDATE posts SET like_count = GREATEST(like_count - 1, 0) "
              + "WHERE id = :id AND status NOT IN ('hidden', 'deleted')",
      nativeQuery = true)
  int decrementLike(@Param("id") Long id);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "UPDATE PostEntity p SET p.coinCount = p.coinCount + 1 "
          + "WHERE p.id = :id AND p.status NOT IN ('hidden', 'deleted')")
  int incrementCoin(@Param("id") Long id);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "UPDATE PostEntity p SET p.shareCount = p.shareCount + 1 "
          + "WHERE p.id = :id AND p.status NOT IN ('hidden', 'deleted')")
  int incrementShare(@Param("id") Long id);

  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "UPDATE PostEntity p SET p.commentCount = p.commentCount + 1 "
          + "WHERE p.id = :id AND p.status NOT IN ('hidden', 'deleted')")
  int incrementComment(@Param("id") Long id);
}
