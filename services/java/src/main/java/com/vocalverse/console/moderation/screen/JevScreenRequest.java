package com.vocalverse.console.moderation.screen;

/**
 * 一次送审请求（docs/58 §3）：只携带判定所需的最小内容，不落库、不写日志正文。
 *
 * <p>{@code title}/{@code body} 由调用方截断到 {@code max-chars}（默认 4000）—— 送审不是留存，
 * 截断是隐私最小化与成本控制的共同要求（docs/50 §5.3.8 同口径：控制台只存 500 字快照）。
 */
public record JevScreenRequest(
    String targetType, Long targetId, String kind, String title, String body, String domain) {

  /** 日志用的短标识（不含内容正文）。 */
  public String ref() {
    return targetType + "#" + targetId;
  }
}
