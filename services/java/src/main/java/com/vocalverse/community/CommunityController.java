package com.vocalverse.community;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.community.dto.CommunityView.CoinState;
import com.vocalverse.community.dto.CommunityView.CommentPage;
import com.vocalverse.community.dto.CommunityView.CommentView;
import com.vocalverse.community.dto.CommunityView.CommunityPostView;
import com.vocalverse.community.dto.CommunityView.FeedPage;
import com.vocalverse.community.dto.CommunityView.LikeState;
import com.vocalverse.community.dto.CommunityView.ShareState;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 社区 C 端（docs/37 §5 · docs/21 §2.2 社区·内容/评论/互动）：网关 /manage/api/v1/community/*，
 * Bearer（anyRequest().authenticated()，无需 admin）。keyset 游标分页：data={items,next_cursor,has_more}。
 */
@RestController
@RequestMapping("/api/v1/community/posts")
public class CommunityController {

  public record CreatePostRequest(
      @Size(max = 200) String title,
      @NotBlank @Size(max = 8000) String body,
      @NotBlank @Size(max = 16) String kind,
      @NotBlank @Size(max = 16) String domain,
      /** 媒体引用（docs/47 §4.3）；纯文本帖为 null */
      com.fasterxml.jackson.databind.JsonNode media) {}

  public record AddCommentRequest(@NotBlank @Size(max = 500) String body) {}

  private final CommunityService service;

  public CommunityController(CommunityService service) {
    this.service = service;
  }

  @GetMapping
  public Envelope<FeedPage> feed(
      @RequestAttribute("userId") Long userId,
      @RequestParam(required = false) String domain,
      @RequestParam(required = false) String cursor,
      @RequestParam(defaultValue = "10") int limit,
      /** mine=true → 只看本人发帖（「我的发帖」，docs/47 §5.1） */
      @RequestParam(defaultValue = "false") boolean mine) {
    return Envelope.ok(service.feed(userId, domain, cursor, limit, mine));
  }

  @PostMapping
  public Envelope<CommunityPostView> create(
      @RequestAttribute("userId") Long userId, @Valid @RequestBody CreatePostRequest body) {
    return Envelope.ok(
        service.create(
            userId, body.title(), body.body(), body.kind(), body.domain(), body.media()));
  }

  @GetMapping("/{id}")
  public Envelope<CommunityPostView> detail(
      @RequestAttribute("userId") Long userId, @PathVariable Long id) {
    return Envelope.ok(service.detail(userId, id));
  }

  @DeleteMapping("/{id}")
  public Envelope<Void> delete(@RequestAttribute("userId") Long userId, @PathVariable Long id) {
    service.delete(userId, id);
    return Envelope.ok(null);
  }

  @GetMapping("/{id}/comments")
  public Envelope<CommentPage> comments(
      @RequestAttribute("userId") Long userId,
      @PathVariable Long id,
      @RequestParam(required = false) String cursor,
      @RequestParam(defaultValue = "10") int limit) {
    return Envelope.ok(service.comments(userId, id, cursor, limit));
  }

  @PostMapping("/{id}/comments")
  public Envelope<CommentView> addComment(
      @RequestAttribute("userId") Long userId,
      @PathVariable Long id,
      @Valid @RequestBody AddCommentRequest body) {
    return Envelope.ok(service.addComment(userId, id, body.body()));
  }

  @PutMapping("/{id}/likes")
  public Envelope<LikeState> like(@RequestAttribute("userId") Long userId, @PathVariable Long id) {
    return Envelope.ok(service.like(userId, id, true));
  }

  @DeleteMapping("/{id}/likes")
  public Envelope<LikeState> unlike(
      @RequestAttribute("userId") Long userId, @PathVariable Long id) {
    return Envelope.ok(service.like(userId, id, false));
  }

  @PutMapping("/{id}/coins")
  public Envelope<CoinState> coin(@RequestAttribute("userId") Long userId, @PathVariable Long id) {
    return Envelope.ok(service.coin(userId, id));
  }

  @PostMapping("/{id}/shares")
  public Envelope<ShareState> share(
      @RequestAttribute("userId") Long userId, @PathVariable Long id) {
    return Envelope.ok(service.share(userId, id));
  }
}
