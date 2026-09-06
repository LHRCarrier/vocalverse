package com.vocalverse.community;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.community.dto.CommunityView.FeedPage;
import com.vocalverse.community.dto.CommunityView.FollowRecommend;
import com.vocalverse.community.dto.CommunityView.FollowSummary;
import com.vocalverse.community.dto.CommunityView.NotificationsPage;
import java.util.List;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 社区 S2：关注 / 互动通知（docs/41）。服务原生 /api/v1/community/*（网关 /manage 剥前缀），
 * Bearer；关注幂等（唯一键兜底）、通知为派生聚合（不建表）。
 *
 * <p>注意：/follows/recommendations 为字面路径，请求匹配优先于 /follows/{userId}（Spring 按 精确度解析），勿调换声明顺序的依赖。
 */
@RestController
@RequestMapping("/api/v1/community")
public class CommunitySocialController {

  private final CommunityService service;

  public CommunitySocialController(CommunityService service) {
    this.service = service;
  }

  @PutMapping("/follows/{userId}")
  public Envelope<Void> follow(
      @RequestAttribute("userId") Long userId, @PathVariable("userId") Long targetUserId) {
    service.follow(userId, targetUserId);
    return Envelope.ok(null);
  }

  @DeleteMapping("/follows/{userId}")
  public Envelope<Void> unfollow(
      @RequestAttribute("userId") Long userId, @PathVariable("userId") Long targetUserId) {
    service.unfollow(userId, targetUserId);
    return Envelope.ok(null);
  }

  @GetMapping("/follows")
  public Envelope<List<FollowSummary>> follows(@RequestAttribute("userId") Long userId) {
    return Envelope.ok(service.followingList(userId));
  }

  @GetMapping("/follows/recommendations")
  public Envelope<List<FollowRecommend>> followRecommendations(
      @RequestAttribute("userId") Long userId) {
    return Envelope.ok(service.recommendations(userId));
  }

  @GetMapping("/following-feed")
  public Envelope<FeedPage> followingFeed(
      @RequestAttribute("userId") Long userId,
      @RequestParam(required = false) String cursor,
      @RequestParam(defaultValue = "10") int limit) {
    return Envelope.ok(service.followingFeed(userId, cursor, limit));
  }

  @GetMapping("/notifications")
  public Envelope<NotificationsPage> notifications(
      @RequestAttribute("userId") Long userId,
      @RequestParam(required = false) String cursor,
      @RequestParam(defaultValue = "10") int limit) {
    return Envelope.ok(service.notifications(userId, cursor, limit));
  }
}
