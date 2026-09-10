package com.vocalverse.community;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * 互动时序单（Java 写方；like/coin/share 唯一 (actor, post, action) 幂等）。
 *
 * <p><b>2026-09-10 管理端隐藏 · 通知中心泄漏修复</b>：本类的两条原生 SQL 是隐藏内容最容易漏掉的读路径 —— 隐藏只改 PostRepository
 * 的话，被隐藏帖子的**点赞者/评论者仍在通知中心可见**， 泄漏的是「谁互动了哪条内容」这层社交图信息，比正文更难察觉。所以这里的 {@code = 'visible'} 全部放宽为
 * {@code NOT IN ('hidden','deleted')}（docs/50 §6.2 联动硬点 1）。
 */
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
   * 后者即便 catch 到冲突，Hibernate 已把当前事务标为 rollback-only，事务提交仍抛 UnexpectedRollbackException（真并发下 500
   * 依旧）——由 DB 原子性彻底消除竞态窗口。
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

  /**
   * J-03（2026-09-10）：通知聚合组的 **DB 层投影**（keyset 分页 + SQL 聚合，替代「近 50 条内存窗口」）。
   *
   * <p>{@code action} 非空 = 互动组（mergeKey {@code postId|action|当日UTC}，count 为组内互动数）； {@code action}
   * 为空 = 单条评论（mergeKey {@code comment|id}，count 恒 1）。排序键 {@code (latestAt DESC, mergeKey ASC)}
   * 即阈值游标口径。
   */
  interface NotificationGroupRow {
    String getMergeKey();

    Long getPostId();

    String getAction();

    Integer getItemCount();

    /**
     * 原生查询的 timestamptz 列投影为 {@link Object}：**PG 返回 {@code Instant}、H2 返回 {@code
     * OffsetDateTime}**（两方言类型不同，Spring Data 无跨类型转换器，2026-09-10 真 PG 联调实测）——服务层用 {@code
     * DirectMessagingService.toInstant(Object)} 归一。
     */
    Object getLatestAt();

    Long getLatestId();
  }

  /**
   * 通知分页查询（J-03）：互动聚合组 UNION 评论单条 → keyset {@code (latestAt, mergeKey)} 过滤 → 排序 → LIMIT。
   *
   * <p>与旧实现的差别：**数据不再被 50 行窗口截断**（第 51 条及更早同样可翻到），且聚合在 SQL 层完成 （每页 O(limit)，而非 O(窗口) 重算）。
   *
   * <p><b>首页游标用哨兵值，不用 NULL</b>（2026-09-10 真 PG 实测）：`(:cursorTs IS NULL OR … merge_key &gt;
   * :cursorKey)` 在 PG 报 `could not determine data type of parameter $4`——游标键参数在「IS NULL 分支」下类型未知（H2
   * 放过， PG 拒绝）。首页传 {@code Instant.MAX} + 空串即恒真，语义等价且两方言一致（同 docs/37 §9「PG 未类型化 NULL」族）。
   */
  @Query(
      value =
          "SELECT merge_key AS mergeKey, post_id AS postId, action AS action, "
              + "       item_count AS itemCount, latest_at AS latestAt, latest_id AS latestId "
              + "FROM ("
              + "  SELECT g.merge_key AS merge_key, g.post_id AS post_id, g.action AS action, "
              + "         COUNT(*) AS item_count, MAX(g.created_at) AS latest_at, MAX(g.id) AS latest_id "
              + "  FROM ("
              + "    SELECT p.post_id || '|' || p.action || '|' || CAST(p.created_at AS date) AS merge_key, "
              + "           p.post_id AS post_id, p.action AS action, p.created_at AS created_at, p.id AS id "
              + "    FROM post_interactions p "
              + "    WHERE p.action = :action AND p.actor_id <> :authorId "
              + "      AND p.post_id IN (SELECT po.id FROM posts po "
              + "                        WHERE po.author_id = :authorId AND po.status NOT IN ('hidden', 'deleted')) "
              + "  ) g "
              + "  GROUP BY g.merge_key, g.post_id, g.action "
              + ") a "
              + "WHERE (a.latest_at < :cursorTs "
              + "       OR (a.latest_at = :cursorTs AND a.merge_key > :cursorKey)) "
              + "ORDER BY a.latest_at DESC, a.merge_key ASC "
              + "LIMIT :pageSize",
      nativeQuery = true)
  List<NotificationGroupRow> notificationGroups(
      @Param("authorId") Long authorId,
      @Param("action") String action,
      @Param("cursorTs") Instant cursorTs,
      @Param("cursorKey") String cursorKey,
      @Param("pageSize") int pageSize);

  /**
   * 互动聚合组「最新一条互动」的 actor（J-03）——组内 ROW_NUMBER 排序取第一行，供「张三 等 N 人…」 展示最新互动者。
   *
   * <p>返回 {@code [merge_key, actor_id]} 两列（mergeKey 同 {@link #notificationGroups} 的格式，两端可对齐）；按 post
   * 过滤后行数 ≤ 该页涉及帖子的互动总量，聚合组数 ≤ 页大小。
   */
  @Query(
      value =
          "SELECT merge_key AS mergeKey, actor_id AS actorId FROM ("
              + "  SELECT p.merge_key AS merge_key, p.actor_id AS actor_id, "
              + "         ROW_NUMBER() OVER (PARTITION BY p.merge_key ORDER BY p.created_at DESC, p.id DESC) AS rn "
              + "  FROM ("
              + "    SELECT p.post_id || '|' || p.action || '|' || CAST(p.created_at AS date) AS merge_key, "
              + "           p.actor_id AS actor_id, p.created_at AS created_at, p.id AS id "
              + "    FROM post_interactions p "
              + "    WHERE p.action = :action AND p.actor_id <> :authorId AND p.post_id IN (:postIds)"
              + "  ) p"
              + ") r WHERE r.rn = 1",
      nativeQuery = true)
  List<Object[]> latestActorPerGroup(
      @Param("action") String action,
      @Param("authorId") Long authorId,
      @Param("postIds") List<Long> postIds);

  /** 评论流分页（J-03）：逐条通知的 DB 层 keyset（{@code (created_at,id)}），不再受 50 条窗口截断。 */
  interface NotificationCommentRow {
    Long getId();

    Long getPostId();

    Long getAuthorId();

    String getBody();

    /** 同 {@link NotificationGroupRow#getLatestAt()}：原生投影的类型随方言不同，服务层归一到 Instant。 */
    Object getCreatedAt();
  }

  /**
   * 评论流分页（J-03）：逐条通知的 DB 层 keyset（{@code (created_at,id)}），不再受 50 条窗口截断。
   *
   * <p>同 {@link #notificationGroups}：**首页游标用哨兵值**（{@code Instant.MAX} + {@code Long.MAX_VALUE}）——
   * 不用 NULL 参数，避免 PG 的 `could not determine data type of parameter`（2026-09-10 真 PG 实测）。
   */
  @Query(
      value =
          "SELECT c.id AS id, c.post_id AS postId, c.author_id AS authorId, "
              + "       c.body AS body, c.created_at AS createdAt "
              + "FROM post_comments c "
              + "WHERE c.status NOT IN ('hidden', 'deleted') "
              + "  AND c.post_id IN (SELECT po.id FROM posts po "
              + "                    WHERE po.author_id = :authorId AND po.status NOT IN ('hidden', 'deleted')) "
              + "  AND c.author_id <> :authorId "
              + "  AND (c.created_at < :cursorTs "
              + "       OR (c.created_at = :cursorTs AND c.id < :cursorId)) "
              + "ORDER BY c.created_at DESC, c.id DESC "
              + "LIMIT :pageSize",
      nativeQuery = true)
  List<NotificationCommentRow> notificationComments(
      @Param("authorId") Long authorId,
      @Param("cursorTs") Instant cursorTs,
      @Param("cursorId") Long cursorId,
      @Param("pageSize") int pageSize);
}
