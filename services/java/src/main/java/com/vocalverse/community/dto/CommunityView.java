package com.vocalverse.community.dto;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;

/** 社区契约视图（docs/37 §5；字段对齐前端 CommunityPost 语义，kind/domain 存储值由前端映射展示文案）。 */
public final class CommunityView {

  private CommunityView() {}

  public record AuthorView(Long id, String nickname, String handle, String tint, String level) {}

  public record CommunityPostView(
      Long id,
      AuthorView author,
      String kind,
      String domain,
      String title,
      String body,
      JsonNode media,
      Instant createdAt,
      int likeCount,
      int coinCount,
      int commentCount,
      int shareCount,
      boolean liked,
      boolean coined,
      Double checkinOverall,
      Integer checkinPracticeCount,
      String checkinDate) {}

  public record FeedPage(List<CommunityPostView> items, String nextCursor, boolean hasMore) {}

  public record CommentView(
      Long id, AuthorView author, String body, Instant createdAt, String replyToNickname) {}

  public record CommentPage(List<CommentView> items, String nextCursor, boolean hasMore) {}

  public record LikeState(boolean liked, int likeCount) {}

  public record CoinState(boolean coined, int coinCount) {}

  public record ShareState(boolean shared, int shareCount) {}
}
