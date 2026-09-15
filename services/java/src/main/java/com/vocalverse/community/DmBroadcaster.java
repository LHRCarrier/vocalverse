package com.vocalverse.community;

import com.vocalverse.community.dto.MessageView.DirectMessageView;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArraySet;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 私信实时推送广播器（docs/49 §3 裁决 A · Java SSE + 进程内广播）。
 *
 * <p>边界（docs/49 §3.4 登记）：**单实例内存广播**——多副本部署下跨副本不投递（延迟可见但不丢：接收端 重连时按 {@code since} 游标回放即可补齐）。升级路径 =
 * Redis pub/sub 或 PG NOTIFY，本轮不做。
 *
 * <p>连接护栏：单用户 ≤ {@link #MAX_STREAMS_PER_USER} 条流、全局 ≤ {@link #MAX_STREAMS}——超限直接 完成连接并下发 {@code
 * error} 事件，由前端降级为轮询（同源 6 连接限制下不能无限长连）。
 */
@Component
public class DmBroadcaster {

  private static final Logger log = LoggerFactory.getLogger(DmBroadcaster.class);

  /** 单用户并发流上限（浏览器同源 6 连接：IM 流 + 练习流 + XHR 已临界）。 */
  public static final int MAX_STREAMS_PER_USER = 3;

  /** 全局并发流上限（演示/单实例量级；docs/49 §3.1）。 */
  public static final int MAX_STREAMS = 500;

  private final Map<Long, Set<SseEmitter>> streams = new ConcurrentHashMap<>();
  private final AtomicInteger total = new AtomicInteger();

  /** 注册一条流；超限返回 {@code null}（调用方下发 error 后收口）。 */
  public SseEmitter register(Long userId) {
    if (total.get() >= MAX_STREAMS) {
      log.warn("dm stream rejected: global limit reached user={} total={}", userId, total.get());
      return null;
    }
    Set<SseEmitter> set = streams.computeIfAbsent(userId, k -> new CopyOnWriteArraySet<>());
    if (set.size() >= MAX_STREAMS_PER_USER) {
      log.warn("dm stream rejected: per-user limit reached user={} streams={}", userId, set.size());
      return null;
    }
    SseEmitter emitter = new SseEmitter(null); // 超时由 controller 设定；null = 不过期

    emitter.onCompletion(() -> remove(userId, emitter));
    emitter.onTimeout(() -> remove(userId, emitter));
    emitter.onError(e -> remove(userId, emitter));
    set.add(emitter);
    total.incrementAndGet();
    return emitter;
  }

  private void remove(Long userId, SseEmitter emitter) {
    Set<SseEmitter> set = streams.get(userId);
    if (set != null && set.remove(emitter)) {
      total.decrementAndGet();
      if (set.isEmpty()) {
        streams.remove(userId);
      }
    }
  }

  /** 在线流数（诊断/测试用）。 */
  public int streamCount(Long userId) {
    Set<SseEmitter> set = streams.get(userId);
    return set == null ? 0 : set.size();
  }

  public int totalStreams() {
    return total.get();
  }

  /** 向某用户的所有流下发事件（失败流即时清理；无在线流时静默 no-op）。 */
  public void push(Long userId, String event, Object data) {
    Set<SseEmitter> set = streams.get(userId);
    if (set == null || set.isEmpty()) {
      return;
    }
    for (SseEmitter emitter : new ArrayList<>(set)) {
      sendTo(userId, emitter, event, data);
    }
  }

  /** 只向**指定一条流**下发（断线回放用）：回放内容是该条连接独有的历史，不能广播给同账号的其他流， 否则同一消息会被投递多次（前端虽按 id 去重，但会造成重复渲染与未读抖动）。 */
  public void sendTo(Long userId, SseEmitter emitter, String event, Object data) {
    try {
      emitter.send(SseEmitter.event().name(event).data(data));
    } catch (IOException | IllegalStateException e) {
      // 客户端断开/流已收口：清理，不打断其他流
      remove(userId, emitter);
      log.debug("dm stream send failed (cleaned) user={} event={}", userId, event, e);
    }
  }

  /** 心跳（``:ping`` 注释帧）：保活 + 让代理不因 idle 断链。 */
  public void ping() {
    for (Map.Entry<Long, Set<SseEmitter>> e : streams.entrySet()) {
      for (SseEmitter emitter : new ArrayList<>(e.getValue())) {
        try {
          emitter.send(SseEmitter.event().comment("ping"));
        } catch (IOException | IllegalStateException ex) {
          remove(e.getKey(), emitter);
        }
      }
    }
  }

  /** 新消息事件载荷（对端视角：peer = 发送者；未读回带避免前端二次请求）。 */
  public record NewMessagePayload(DirectMessageView message, long unreadCount) {}

  /** 会话内消息已读回执载荷（本轮仅回给自己的其他流，用于多标签一致）。 */
  public record ReadPayload(Long peerId, long lastReadId) {}

  /** 调试：当前在线用户（按流数降序）。 */
  public List<Long> onlineUsers() {
    List<Long> ids = new ArrayList<>(streams.keySet());
    ids.sort(Comparator.comparingInt((Long id) -> streamCount(id)).reversed());
    return ids;
  }

  /**
   * 渲染一帧 SSE 文本（`event:` + `data:` + 空行）——用于**同步**响应路径（超限拒绝走 `ResponseEntity<String>`：
   * `ResponseBodyEmitter` 在被拒绝的同一次请求里 `send + complete` 会抛 IllegalStateException，2026-09-10 实测）。
   */
  public static String renderFrame(String event, Object data) {
    StringBuilder sb = new StringBuilder();
    sb.append("event:").append(event).append('\n');
    String payload;
    try {
      payload = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(data);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      payload = String.valueOf(data);
    }
    sb.append("data:").append(payload).append("\n\n");
    return sb.toString();
  }
}
