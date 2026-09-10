package com.vocalverse.community;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.community.dto.MessageView.ConversationView;
import com.vocalverse.community.dto.MessageView.DirectMessageView;
import com.vocalverse.community.dto.MessageView.MessagePage;
import com.vocalverse.community.dto.MessageView.ReadState;
import io.swagger.v3.oas.annotations.Hidden;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 私信（IM）控制器（docs/49 §2）。服务原生 `/api/v1/community/messages*`（网关 `/manage` 剥前缀），Bearer。
 *
 * <p>REST 4 端点走统一 Envelope；**SSE 长连是流例外**（`text/event-stream`，非 Envelope）—— 已按
 * `docs/api/envelope.md` 的流式例外口径登记（与 Python 侧 SSE 同类）。
 */
@RestController
@RequestMapping("/api/v1/community/messages")
public class DirectMessageController {

  /** SSE 单连接上限（0 = 不过期；心跳保活 + 前端按需重连，见 docs/49 §3）。 */
  private static final long STREAM_TIMEOUT_MS = 0L;

  private final DirectMessagingService service;
  private final DmBroadcaster broadcaster;

  public DirectMessageController(DirectMessagingService service, DmBroadcaster broadcaster) {
    this.service = service;
    this.broadcaster = broadcaster;
  }

  @GetMapping("/conversations")
  public Envelope<List<ConversationView>> conversations(
      @RequestAttribute("userId") Long userId, @RequestParam(defaultValue = "50") int limit) {
    return Envelope.ok(service.conversations(userId, limit));
  }

  @GetMapping("/unread")
  public Envelope<Long> unread(@RequestAttribute("userId") Long userId) {
    return Envelope.ok(service.totalUnread(userId));
  }

  /** 会话消息（keyset 倒序；`cursor` = 上一页最后一条 id）。 */
  @GetMapping("/{peerId}")
  public Envelope<MessagePage> thread(
      @RequestAttribute("userId") Long userId,
      @PathVariable("peerId") Long peerId,
      @RequestParam(required = false) Long cursor,
      @RequestParam(defaultValue = "20") int limit) {
    return Envelope.ok(service.thread(userId, peerId, cursor, limit));
  }

  @PostMapping("/{peerId}")
  public Envelope<DirectMessageView> send(
      @RequestAttribute("userId") Long userId,
      @PathVariable("peerId") Long peerId,
      @RequestBody SendRequest body) {
    return Envelope.ok(service.send(userId, peerId, body == null ? null : body.body()));
  }

  @PutMapping("/{peerId}/read")
  public Envelope<ReadState> markRead(
      @RequestAttribute("userId") Long userId,
      @PathVariable("peerId") Long peerId,
      @RequestBody(required = false) ReadRequest body) {
    return Envelope.ok(service.markRead(userId, peerId, body == null ? null : body.upTo()));
  }

  /**
   * SSE 长连：实时新消息推送 + 断线按 `since` 回放（docs/49 §3.1）。
   *
   * <p>`since` = 客户端本地已见的最大消息 id；服务端先回放断线期间的**对端来信**（升序），再进入实时推送。 心跳 `:ping` 每 25s（{@link
   * DmHeartbeat}）；单用户 ≤3 流、全局 ≤500，超限下发 `error` 后立即收口（前端降级轮询）。
   *
   * <p><b>响应形态</b>：返回 {@link ResponseBodyEmitter}（非 `SseEmitter`）——消息用注解式 `SseEmitter.event()`
   * 预格式化好转给容器，因此**可以立即下发 `open` 事件**（中间无「未提交响应」的模糊窗口），测试与真实流行为一致 （`SseEmitter` 在首次 `send` 前调
   * `complete()` 不会产出任何帧）。
   *
   * <p><b>超时</b>：`new SseEmitter(0L)` = 不过期，**显式覆盖 Tomcat `asyncTimeout` 默认 30s**（否则长连每 30s 闪断，
   * docs/49 §3.3 阻断项 ③）——保活与回收交给心跳 + 客户端重连。
   */
  @Hidden // 流式端点不进 OpenAPI 契约（Envelope 例外，同 Python SSE 口径）
  @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  public Object stream(
      @RequestAttribute("userId") Long userId, @RequestParam(required = false) Long since) {
    SseEmitter emitter = broadcaster.register(userId);
    if (emitter == null) {
      // 超限：同步回一帧 error（前端据此切轮询）。**不能**用 ResponseBodyEmitter 的 send+complete：
      // 同一次请求内先写后立即收口会抛 IllegalStateException（2026-09-10 实测）
      return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
          .contentType(MediaType.TEXT_EVENT_STREAM)
          .body(DmBroadcaster.renderFrame("error", "stream-limit"));
    }
    try {
      // 连接即建流事件：让前端确认长连可用（并携带服务端看到的 userId，便于排障日志对齐）
      emitter.send(SseEmitter.event().name("open").data(java.util.Map.of("userId", userId)));
    } catch (Exception e) {
      // 建流事件失败即流不可用：交给 onError 清理
      emitter.completeWithError(e);
      return emitter;
    }
    // 断线回放（只发给本条流；条数上限 ARCHIVE_MAX，短事务，不在订阅期持 DB 连接）
    service.replaySince(userId, since, emitter);
    return emitter;
  }

  /** 发送请求体（`body` 1~1000 字，服务层再校验一次）。 */
  public record SendRequest(@Size(max = 1000) String body) {}

  /** 已读上报请求体（`upTo` = 本次已渲染的最后一条对端消息 id）。 */
  public record ReadRequest(Long upTo) {}
}
