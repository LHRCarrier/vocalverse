package com.vocalverse.community.dto;

import com.vocalverse.community.dto.CommunityView.AuthorView;
import java.time.Instant;
import java.util.List;

/** 私信契约视图（docs/49 §2；字段对齐前端 MessageView / ConversationView 语义）。 */
public final class MessageView {

  private MessageView() {}

  /** 单条消息：{@code mine} = 我发的（前端据此左右分栏，不依赖 id 比较）。 */
  public record DirectMessageView(
      Long id, Long peerId, String body, boolean mine, Instant createdAt) {}

  /** 会话列表行：对端 + 最后一条消息 + 我未读数。 */
  public record ConversationView(
      AuthorView peer,
      Long lastMessageId,
      String lastBody,
      boolean lastMine,
      java.time.OffsetDateTime lastCreatedAt,
      long unreadCount) {}

  /** 会话消息页（keyset 倒序；{@code nextCursor} = 下一页 beforeId）。 */
  public record MessagePage(List<DirectMessageView> items, Long nextCursor, boolean hasMore) {}

  /** 已读上报结果：回带服务端权威水位（前端据此对齐未读）。 */
  public record ReadState(Long peerId, long lastReadId) {}
}
