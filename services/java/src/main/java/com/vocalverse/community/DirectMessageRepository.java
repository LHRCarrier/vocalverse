package com.vocalverse.community;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 私信消息仓库（Java 写 · docs/49 §2）。会话双方都算「我」（peer 视角），keyset 一律倒序。 */
public interface DirectMessageRepository extends JpaRepository<DirectMessageEntity, Long> {

  /** 会话说读取：我 → 对方 或 对方 → 我，{@code id < beforeId} 阈值（首页传 {@code Long.MAX_VALUE}）。 */
  @Query(
      "SELECT m FROM DirectMessageEntity m "
          + "WHERE m.status = 'visible' "
          + "  AND ((m.senderId = :me AND m.recipientId = :peer) "
          + "    OR (m.senderId = :peer AND m.recipientId = :me)) "
          + "  AND m.id < :beforeId "
          + "ORDER BY m.id DESC")
  List<DirectMessageEntity> page(
      @Param("me") Long me,
      @Param("peer") Long peer,
      @Param("beforeId") Long beforeId,
      Pageable pageable);

  /**
   * SSE 断线回放：我参与、且**对端**发来的、{@code id > sinceId} 的消息（升序，上限 rows）。
   *
   * <p>只回放「别人发给我的」——自己发的已由发送响应同步到本地（避免双通道重复渲染）。
   */
  @Query(
      "SELECT m FROM DirectMessageEntity m "
          + "WHERE m.status = 'visible' AND m.recipientId = :me AND m.senderId <> :me "
          + "  AND m.id > :sinceId ORDER BY m.id ASC")
  List<DirectMessageEntity> incomingSince(
      @Param("me") Long me, @Param("sinceId") Long sinceId, Pageable pageable);

  /** 会话列表：与我往来的每个对端一行（最新消息时间/正文 + 我未读条数）。 */
  interface ConversationRow {
    Long getPeerId();

    Long getLastMessageId();

    String getLastBody();

    Long getLastSenderId();

    /**
     * 原生查询的 timestamptz 列投影为 {@link Object}：**PG 返回 {@code Instant}、H2 返回 {@code
     * OffsetDateTime}**（同一份接口投影在两种方言下类型不同，Spring Data 无跨类型转换器——2026-09-10 实跑， H2 测试绿、真 PG 联调
     * 500：`Cannot project java.time.Instant to java.time.OffsetDateTime`）； 由 {@code
     * DirectMessagingService.toInstant(Object)} 归一，两个方言都能跑。
     */
    Object getLastCreatedAt();

    Long getUnreadCount();
  }

  /**
   * 会话列表（单查询 · docs/49 §2）：对端集合 = 我收发的全部对方；未读 = 对方发来且 {@code id > 水位} 的条数。
   *
   * <p>分三层（**方言兼容 + 防串话**）：① 展开对端与消息 id；② 每对端取 {@code MAX(id)}；③ 用 **该对端自己的 last_id**
   * 回查最后一条的正文/发送者/时间。
   *
   * <p>踩坑（2026-09-10 实测）：把 {@code MAX(x.id)} 直接写进标量子查询在 H2 报 `Invalid use of aggregate
   * function`；而若用「全表 MAX(id) 回查发送者」会把别的会话的消息当成本会话最后一条（跨会话串话， 表现为 `lastMine`/`lastBody`
   * 错位）——必须用每行自己的 last_id 关联。
   */
  @Query(
      value =
          "SELECT a.peer_id AS peerId, a.last_message_id AS lastMessageId, "
              + "       (SELECT m2.body FROM direct_messages m2 WHERE m2.id = a.last_message_id) AS lastBody, "
              + "       (SELECT m3.sender_id FROM direct_messages m3 WHERE m3.id = a.last_message_id) AS lastSenderId, "
              + "       (SELECT m4.created_at FROM direct_messages m4 WHERE m4.id = a.last_message_id) AS lastCreatedAt, "
              + "       (SELECT COUNT(*) FROM direct_messages m5 "
              + "         WHERE m5.sender_id = a.peer_id AND m5.recipient_id = :me "
              + "           AND m5.status = 'visible' AND m5.id > COALESCE("
              + "             (SELECT r.last_read_id FROM dm_read_state r "
              + "               WHERE r.user_id = :me AND r.peer_id = a.peer_id), 0)) AS unreadCount "
              + "FROM ("
              + "  SELECT x.peer_id AS peer_id, MAX(x.id) AS last_message_id "
              + "  FROM ("
              + "    SELECT CASE WHEN m.sender_id = :me THEN m.recipient_id ELSE m.sender_id END AS peer_id, "
              + "           m.id AS id "
              + "    FROM direct_messages m "
              + "    WHERE m.status = 'visible' AND (m.sender_id = :me OR m.recipient_id = :me)"
              + "  ) x "
              + "  GROUP BY x.peer_id"
              + ") a "
              + "ORDER BY a.last_message_id DESC "
              + "LIMIT :limit",
      nativeQuery = true)
  List<ConversationRow> conversations(@Param("me") Long me, @Param("limit") int limit);

  /** 未读总览（SSE 推送用）：单个对端的未读数。 */
  @Query(
      "SELECT COUNT(m) FROM DirectMessageEntity m "
          + "WHERE m.status = 'visible' AND m.recipientId = :me AND m.senderId = :peer AND m.id > :sinceId")
  long unreadFrom(@Param("me") Long me, @Param("peer") Long peer, @Param("sinceId") Long sinceId);

  /** 全部未读合计（会话列表页脚数用；与 conversations 的 SUM 同口径）。 */
  @Query(
      value =
          "SELECT COUNT(*) FROM direct_messages m "
              + "WHERE m.status = 'visible' AND m.recipient_id = :me AND m.id > COALESCE("
              + "  (SELECT r.last_read_id FROM dm_read_state r "
              + "    WHERE r.user_id = :me AND r.peer_id = m.sender_id), 0)",
      nativeQuery = true)
  long totalUnread(@Param("me") Long me);
}
