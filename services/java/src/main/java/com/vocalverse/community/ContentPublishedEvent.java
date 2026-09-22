package com.vocalverse.community;

/**
 * 「内容已发布」领域事件（docs/58 §3.1）——由**生产方**（社区域）定义，送审链路只消费。
 *
 * <p>在 {@code CommunityService.create}/{@code addComment} 的**事务内**发布，由监听器在 {@code AFTER_COMMIT}
 * 阶段异步送审 —— 送审只发生在内容确实落库之后，回滚的事务不会产生审核单。
 *
 * <p>{@code title}/{@code body} 是发布时刻的原文（送审侧自行截断），事件不落库、不写日志。
 */
public record ContentPublishedEvent(
    String targetType, Long targetId, String kind, String title, String body, String domain) {

  public static final String TARGET_POST = "post";
  public static final String TARGET_COMMENT = "comment";

  /** 帖子发布（{@code kind} 为 article/video，{@code domain} 为三个领域之一）。 */
  public static ContentPublishedEvent post(
      Long postId, String kind, String title, String body, String domain) {
    return new ContentPublishedEvent(TARGET_POST, postId, kind, title, body, domain);
  }

  /** 评论发布（无标题/领域；帖子归属由审核单快照的 {@code postId} 承担，不重复携带）。 */
  public static ContentPublishedEvent comment(Long commentId, String body) {
    return new ContentPublishedEvent(TARGET_COMMENT, commentId, "comment", null, body, null);
  }
}
