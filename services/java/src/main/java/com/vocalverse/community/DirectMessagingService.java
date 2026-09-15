package com.vocalverse.community;

import com.vocalverse.community.DirectMessageRepository.ConversationRow;
import com.vocalverse.community.dto.CommunityView.AuthorView;
import com.vocalverse.community.dto.MessageView.ConversationView;
import com.vocalverse.community.dto.MessageView.DirectMessageView;
import com.vocalverse.community.dto.MessageView.MessagePage;
import com.vocalverse.community.dto.MessageView.ReadState;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserRepository;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 私信服务（Java 写方唯一实现 · docs/49 §1/§2）。
 *
 * <p>口径：会话 = {@code (sender, recipient)} 有序对（不建会话表）；**已读水位 = {@code last_read_id}** （消息 id
 * 单调，避免时间戳水位在并发提交下漏未读）；未读 = 对端 visible 消息中 {@code id > 水位} 的条数。 发送成功后经 {@link DmBroadcaster}
 * 推送给接收者（自己靠本地乐观插入，不推）。
 */
@Service
public class DirectMessagingService {

  private static final int MAX_BODY = 1000;
  private static final int MAX_LIMIT = 50;
  private static final int ARCHIVE_MAX = 200;

  private final DirectMessageRepository messages;
  private final DmReadStateRepository readStates;
  private final UserRepository users;
  private final CommunityService community;
  private final DmBroadcaster broadcaster;

  public DirectMessagingService(
      DirectMessageRepository messages,
      DmReadStateRepository readStates,
      UserRepository users,
      CommunityService community,
      DmBroadcaster broadcaster) {
    this.messages = messages;
    this.readStates = readStates;
    this.users = users;
    this.community = community;
    this.broadcaster = broadcaster;
  }

  // ------------------------------------------------------------------ 读取

  /** 会话列表（对端 + 最后一条 + 我未读）：单条原生聚合查询 + 批量作者。 */
  @Transactional(readOnly = true)
  public List<ConversationView> conversations(Long me, int limit) {
    int size = clamp(limit);
    List<ConversationRow> rows = messages.conversations(me, size);
    if (rows.isEmpty()) {
      return List.of();
    }
    List<Long> peerIds = rows.stream().map(ConversationRow::getPeerId).toList();
    Map<Long, AuthorView> authors = community.loadAuthors(peerIds);
    List<ConversationView> out = new ArrayList<>(rows.size());
    for (ConversationRow r : rows) {
      out.add(
          new ConversationView(
              authors.getOrDefault(r.getPeerId(), unknownAuthor(r.getPeerId())),
              r.getLastMessageId(),
              r.getLastBody(),
              me.equals(r.getLastSenderId()),
              NativeProjections.toInstant(r.getLastCreatedAt()),
              r.getUnreadCount() == null ? 0L : r.getUnreadCount()));
    }
    return out;
  }

  /** 未读合计（会话列表页脚/SSE 推送口径）。 */
  @Transactional(readOnly = true)
  public long totalUnread(Long me) {
    return messages.totalUnread(me);
  }

  /** 会话消息（keyset 倒序；不修改已读水位——水位只由显式 read 上报推进）。 */
  @Transactional(readOnly = true)
  public MessagePage thread(Long me, Long peer, Long beforeId, int limit) {
    requirePeer(me, peer);
    int size = clamp(limit);
    List<DirectMessageEntity> rows =
        messages.page(
            me, peer, beforeId == null ? Long.MAX_VALUE : beforeId, PageRequest.of(0, size + 1));
    boolean hasMore = rows.size() > size;
    List<DirectMessageEntity> page = hasMore ? rows.subList(0, size) : rows;
    List<DirectMessageView> items = page.stream().map(m -> toView(m, me)).toList();
    Long next = hasMore && !page.isEmpty() ? page.get(page.size() - 1).getId() : null;
    return new MessagePage(items, next, hasMore);
  }

  // ------------------------------------------------------------------ 写入

  /** 发送消息：校验（自聊 42203 / 对端不存在 40402 / 长度）→ 落库 → 推送接收者。 */
  @Transactional
  public DirectMessageView send(Long me, Long peer, String body) {
    if (peer == null || peer.equals(me)) {
      throw new CommunityException(42203, "不能给自己发私信", HttpStatus.BAD_REQUEST);
    }
    String text = body == null ? "" : body.strip();
    if (text.isEmpty() || text.length() > MAX_BODY) {
      throw new CommunityException(42203, "私信需 1~" + MAX_BODY + " 字", HttpStatus.BAD_REQUEST);
    }
    UserEntity peerUser = users.findById(peer).orElseThrow(() -> notFound("对方用户不存在或已注销"));

    Instant now = Instant.now();
    DirectMessageEntity m = new DirectMessageEntity();
    m.setSenderId(me);
    m.setRecipientId(peer);
    m.setBody(text);
    m.setStatus(DirectMessageEntity.STATUS_VISIBLE);
    m.setCreatedAt(now);
    messages.save(m);

    DirectMessageView view = toView(m, me);
    // 推送接收者（对端视角的未读数实时回带，前端无需二次请求）
    long peerUnread = unreadFrom(peer, me);
    broadcaster.push(
        peerUser.getId(),
        "message",
        new DmBroadcaster.NewMessagePayload(toView(m, peer), peerUnread));
    return view;
  }

  /**
   * 已读上报：水位 = {@code max(现有, upTo)}（幂等、单调）。
   *
   * <p>{@code upTo} 由前端传「本次已渲染的最后一条对端消息 id」——**不用请求时刻**：时间戳水位会跨过并发提交中 尚未渲染的消息，造成永久漏未读（docs/49 §4.3
   * B2）。
   */
  @Transactional
  public ReadState markRead(Long me, Long peer, Long upTo) {
    requirePeer(me, peer);
    long target = upTo == null ? 0L : upTo;
    DmReadStateEntity state = readStates.findByUserIdAndPeerId(me, peer).orElse(null);
    if (state == null) {
      state = new DmReadStateEntity();
      state.setUserId(me);
      state.setPeerId(peer);
      state.setLastReadId(target);
      state.setUpdatedAt(Instant.now());
      readStates.save(state);
    } else if (target > state.getLastReadId()) {
      state.setLastReadId(target);
      state.setUpdatedAt(Instant.now());
      readStates.save(state);
    }
    // 回执推给自己的其他流（多标签一致；本轮不回执给对方——docs/49 §4.4 不做项）
    broadcaster.push(me, "read", new DmBroadcaster.ReadPayload(peer, state.getLastReadId()));
    return new ReadState(peer, state.getLastReadId());
  }

  // ------------------------------------------------------------------ SSE 支撑

  /**
   * 断线回放：把 {@code id > sinceId} 的**对端来信**按 (peer, 未读数) 分组推送（升序）。
   *
   * <p>只回放来信（自己发的已由发送响应同步到本地），避免双通道重复渲染——前端仍按消息 id 去重兜底。
   * 回放只发给**本次新建的那条流**（历史是该连接的私有增量，不能广播给同账号其他流）。
   */
  @Transactional(readOnly = true)
  public void replaySince(Long me, Long sinceId, SseEmitter emitter) {
    List<DirectMessageEntity> pending =
        messages.incomingSince(me, sinceId == null ? 0L : sinceId, PageRequest.of(0, ARCHIVE_MAX));
    if (pending.isEmpty()) {
      return;
    }
    for (DirectMessageEntity m : pending) {
      long unread = unreadFrom(me, m.getSenderId());
      broadcaster.sendTo(
          me, emitter, "message", new DmBroadcaster.NewMessagePayload(toView(m, me), unread));
    }
  }

  // ------------------------------------------------------------------ 工具

  private long unreadFrom(Long me, Long peer) {
    Long watermark =
        readStates.findByUserIdAndPeerId(me, peer).map(DmReadStateEntity::getLastReadId).orElse(0L);
    return messages.unreadFrom(me, peer, watermark);
  }

  private DirectMessageView toView(DirectMessageEntity m, Long viewer) {
    Long peer = viewer.equals(m.getSenderId()) ? m.getRecipientId() : m.getSenderId();
    return new DirectMessageView(
        m.getId(), peer, m.getBody(), viewer.equals(m.getSenderId()), m.getCreatedAt());
  }

  private void requirePeer(Long me, Long peer) {
    if (peer == null || peer.equals(me)) {
      throw new CommunityException(42203, "会话对象非法", HttpStatus.BAD_REQUEST);
    }
    if (!users.existsById(peer)) {
      throw notFound("对方用户不存在或已注销");
    }
  }

  private AuthorView unknownAuthor(Long id) {
    return new AuthorView(id, "未知用户", null, null, "L1", null);
  }

  private CommunityException notFound(String message) {
    return new CommunityException(40402, message, HttpStatus.NOT_FOUND);
  }

  private int clamp(int limit) {
    return Math.min(Math.max(limit, 1), MAX_LIMIT);
  }
}
