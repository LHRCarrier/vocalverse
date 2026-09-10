package com.vocalverse.community;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.result.MockMvcResultMatchers;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 私信（IM）测试（H2 · docs/49）：会话列表与未读、会话消息 keyset、发送校验（自聊/不存在/长度）、 已读水位单调与幂等、SSE 长连（open 帧 + 断线按 since
 * 回放 + since 之后的新消息实时投递）。
 *
 * <p>测试档关闭心跳（`vocalverse.dm.heartbeat-enabled=false`）：固定节奏的心跳会让事件序列断言不稳定。
 */
@Transactional
class DirectMessageTest extends AbstractAdminApiTest {

  @Autowired private DirectMessageRepository messages;
  @Autowired private DmReadStateRepository readStates;
  @Autowired private DirectMessagingService service;
  @Autowired private DmBroadcaster broadcaster;

  private static final int CODE_OK = 0;

  private String bearer(String token) {
    return "Bearer " + token;
  }

  private JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  private long userIdOf(String username) {
    return users.findByUsernameIgnoreCase(username).orElseThrow().getId();
  }

  private JsonNode send(String token, long peerId, String body) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/messages/" + peerId)
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        objectMapper
                            .createObjectNode()
                            .put("body", body)
                            .toString()
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    return json(r);
  }

  private JsonNode conversations(String token) throws Exception {
    return json(
        mockMvc
            .perform(
                get("/api/v1/community/messages/conversations")
                    .header("Authorization", bearer(token)))
            .andReturn());
  }

  private JsonNode thread(String token, long peerId, Long cursor) throws Exception {
    String url =
        "/api/v1/community/messages/" + peerId + (cursor == null ? "" : "?cursor=" + cursor);
    return json(mockMvc.perform(get(url).header("Authorization", bearer(token))).andReturn());
  }

  // ------------------------------------------------------------------ 发送与列表

  @Test
  void send_rejects_self_missing_peer_and_bad_body() throws Exception {
    String a = registerUser("dm_val_a");
    long aId = userIdOf("dm_val_a");

    // 自聊 42203
    assertEquals(42203, send(a, aId, "hi").path("code").asInt());
    // 对端不存在 40402
    assertEquals(40402, send(a, 999999L, "hi").path("code").asInt());
    // 空正文 / 超长 42203
    assertEquals(42203, send(a, 999999L, "   ").path("code").asInt());
    String b = registerUser("dm_val_b");
    long bId = userIdOf("dm_val_b");
    assertEquals(42203, send(a, bId, "x".repeat(1001)).path("code").asInt());
    // 正常发送
    JsonNode ok = send(a, bId, "  hello  ");
    assertEquals(CODE_OK, ok.path("code").asInt(), ok.toString());
    assertEquals("hello", ok.path("data").path("body").asText(), "正文应 strip");
    assertTrue(ok.path("data").path("mine").asBoolean(), "发送方视角 mine=true");
    assertEquals(bId, ok.path("data").path("peerId").asLong());
  }

  @Test
  void conversations_show_peer_last_message_and_unread() throws Exception {
    String a = registerUser("dm_conv_a");
    String b = registerUser("dm_conv_b");
    String c = registerUser("dm_conv_c");
    long aId = userIdOf("dm_conv_a");
    long bId = userIdOf("dm_conv_b");
    long cId = userIdOf("dm_conv_c");

    // 会话顺序按「最新消息」判定；两条消息需拉开时间戳（同毫秒会并列，属测试构造问题非实现缺陷）
    send(a, bId, "hi B");
    Thread.sleep(5);
    send(b, aId, "hi A");
    Thread.sleep(5);
    send(c, aId, "hi from C");
    JsonNode list = conversations(a);
    assertEquals(CODE_OK, list.path("code").asInt(), list.toString());
    JsonNode items = list.path("data");
    assertEquals(2, items.size(), "两个对端各一行：" + list);

    JsonNode cRow = null;
    JsonNode bRow = null;
    for (JsonNode n : items) {
      if (n.path("peer").path("id").asLong() == cId) cRow = n;
      if (n.path("peer").path("id").asLong() == bId) bRow = n;
    }
    assertNotNull(cRow, "C 的会话应在列表：" + list);
    assertNotNull(bRow, "B 的会话应在列表：" + list);

    // 会话行的 lastMessageId 必须等于「该会话自己最新一条」——两处独立读取（thread 与会话列表）交叉验证，
    // 防「跨会话串话」（曾把别的会话最新消息当成本会话最后一条：lastBody/lastMine 会整体错位）
    long bLast = thread(a, bId, null).path("data").path("items").get(0).path("id").asLong();
    long cLast = thread(a, cId, null).path("data").path("items").get(0).path("id").asLong();
    assertEquals(bLast, bRow.path("lastMessageId").asLong(), "B 行应指向 B 会话自己的最新消息：" + bRow);
    assertEquals(cLast, cRow.path("lastMessageId").asLong(), "C 行应指向 C 会话自己的最新消息：" + cRow);
    // 未读：B 与 C 各发 1 条我未读
    assertEquals(1, cRow.path("unreadCount").asLong(), "C 一行未读 1：" + cRow);
    assertEquals(1, bRow.path("unreadCount").asLong(), "B 一行未读 1：" + bRow);
    // 最后一条发送方（A 视角）：B/C 两条都是对方发的 → lastMine=false
    assertEquals("hi from C", cRow.path("lastBody").asText(), cRow.toString());
    assertFalse(cRow.path("lastMine").asBoolean(), "最后一条是 C 发的：" + cRow);
    assertEquals("hi A", bRow.path("lastBody").asText(), "B 的最新一条是「hi A」：" + bRow);
    assertFalse(bRow.path("lastMine").asBoolean(), "最后一条是 B 发的（A 视角 mine=false）：" + bRow);
    // 反向：B 视角看，会话最后一条是「hi A」（B 自己发的）→ lastMine=true
    JsonNode bList = conversations(b);
    assertEquals(bLast, bList.path("data").get(0).path("lastMessageId").asLong(), bList.toString());
    assertTrue(bList.path("data").get(0).path("lastMine").asBoolean(), "B 视角最后一条是自己发的：" + bList);
    // 会话按最新消息倒序：C 更近 → 在前
    assertEquals(cId, items.get(0).path("peer").path("id").asLong(), "按最后消息时间倒序：" + list);
    // 未读合计端点
    JsonNode unread =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/messages/unread").header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(2, unread.path("data").asLong(), "C 1 条 + B 1 条 = 2：" + unread);
  }

  @Test
  void read_watermark_is_monotonic_and_clears_unread() throws Exception {
    String a = registerUser("dm_read_a");
    String b = registerUser("dm_read_b");
    long aId = userIdOf("dm_read_a");
    long bId = userIdOf("dm_read_b");

    send(b, aId, "m1");
    send(b, aId, "m2");
    JsonNode before = conversations(a);
    assertEquals(2, before.path("data").get(0).path("unreadCount").asLong(), before.toString());

    long lastId = before.path("data").get(0).path("lastMessageId").asLong();
    // 只读到 m1（upTo = 倒数第二条 id）→ 剩 1 条未读
    long firstId = lastId - 1;
    JsonNode r1 =
        json(
            mockMvc
                .perform(
                    put("/api/v1/community/messages/" + bId + "/read")
                        .header("Authorization", bearer(a))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(("{\"upTo\":" + firstId + "}").getBytes(StandardCharsets.UTF_8)))
                .andReturn());
    assertEquals(firstId, r1.path("data").path("lastReadId").asLong(), r1.toString());
    assertEquals(1, conversations(a).path("data").get(0).path("unreadCount").asLong());

    // 重复上报旧水位（幂等 + 单调不回退）
    mockMvc
        .perform(
            put("/api/v1/community/messages/" + bId + "/read")
                .header("Authorization", bearer(a))
                .contentType(MediaType.APPLICATION_JSON)
                .content(("{\"upTo\":" + firstId + "}").getBytes(StandardCharsets.UTF_8)))
        .andReturn();
    assertEquals(
        firstId,
        readStates.findByUserIdAndPeerId(aId, bId).orElseThrow().getLastReadId(),
        "水位不得回退");

    // 读到 m2 → 未读清零
    mockMvc
        .perform(
            put("/api/v1/community/messages/" + bId + "/read")
                .header("Authorization", bearer(a))
                .contentType(MediaType.APPLICATION_JSON)
                .content(("{\"upTo\":" + lastId + "}").getBytes(StandardCharsets.UTF_8)))
        .andReturn();
    assertEquals(0, conversations(a).path("data").get(0).path("unreadCount").asLong());
  }

  // ------------------------------------------------------------------ 会话消息 keyset

  @Test
  void thread_pages_with_cursor_without_duplicates() throws Exception {
    String a = registerUser("dm_page_a");
    String b = registerUser("dm_page_b");
    long aId = userIdOf("dm_page_a");
    long bId = userIdOf("dm_page_b");

    for (int i = 0; i < 25; i++) {
      assertEquals(CODE_OK, send(a, bId, "m" + i).path("code").asInt());
    }

    List<Long> seen = new ArrayList<>();
    Long cursor = null;
    int pages = 0;
    while (pages++ < 10) {
      JsonNode page = thread(a, bId, cursor);
      JsonNode items = page.path("data").path("items");
      if (items.isEmpty()) break;
      for (JsonNode m : items) {
        seen.add(m.path("id").asLong());
        assertTrue(m.path("mine").asBoolean(), "A 视角全部 mine=true");
        assertEquals(bId, m.path("peerId").asLong());
      }
      if (!page.path("data").path("hasMore").asBoolean()) break;
      cursor = page.path("data").path("nextCursor").asLong();
    }
    assertEquals(25, seen.size(), "翻页应见全部 25 条（无重复无遗漏）");
    assertEquals(25, seen.stream().distinct().count(), "不得重复：" + seen);
    // 倒序（第一页 id 最大）
    assertTrue(seen.get(0) > seen.get(seen.size() - 1), "keyset 倒序：" + seen);

    // 对方视角（B 看 A）：mine=false
    JsonNode bView = thread(b, aId, null);
    assertFalse(bView.path("data").path("items").get(0).path("mine").asBoolean(), bView.toString());

    // 自聊/不存在
    assertEquals(42203, thread(a, aId, null).path("code").asInt());
    assertEquals(40402, thread(a, 999999L, null).path("code").asInt());
  }

  // ------------------------------------------------------------------ SSE 实时通道

  @Test
  void stream_delivers_new_message_and_replays_since_cursor() throws Exception {
    String a = registerUser("dm_sse_a");
    String b = registerUser("dm_sse_b");
    long aId = userIdOf("dm_sse_a");
    long bId = userIdOf("dm_sse_b");

    // 先有一条历史（B 建流时应回放它）
    long historical = send(a, bId, "before-stream").path("data").path("id").asLong();

    MvcResult stream =
        mockMvc
            .perform(
                get("/api/v1/community/messages/stream?since=" + (historical - 1))
                    .header("Authorization", bearer(b))
                    .accept(MediaType.TEXT_EVENT_STREAM))
            .andExpect(MockMvcResultMatchers.request().asyncStarted())
            .andReturn();
    // 建流 + 回放：open 帧在前，回放帧携带刚发的消息（B 视角 peer=A）
    String frames = stream.getResponse().getContentAsString(StandardCharsets.UTF_8);
    assertTrue(hasFrame(stream, "open"), "应下发 open 帧：" + frames);
    assertTrue(hasFrame(stream, "message"), "应回放 since 之后的来信：" + frames);
    String replay = frameData(stream, "message");
    JsonNode replayed = objectMapper.readTree(replay);
    assertEquals("before-stream", replayed.path("message").path("body").asText(), replay);
    assertEquals(aId, replayed.path("message").path("peerId").asLong(), "B 视角 peer=A：" + replay);
    assertFalse(replayed.path("message").path("mine").asBoolean(), "收件方 mine=false：" + replay);
    assertEquals(1, replayed.path("unreadCount").asLong(), "回带未读数：" + replay);

    // 实时投递：A 再发一条 → B 的流收到 message 事件（新消息，非回放）
    long sent = send(a, bId, "live").path("data").path("id").asLong();
    List<String> liveFrames = framesAfter(stream, 2);
    String live = liveFrames.isEmpty() ? null : liveFrames.get(liveFrames.size() - 1);
    assertNotNull(live, "应收到实时 message 帧");
    JsonNode liveNode = objectMapper.readTree(live);
    assertEquals(sent, liveNode.path("message").path("id").asLong(), live);
    assertEquals("live", liveNode.path("message").path("body").asText(), live);
    assertEquals(2, liveNode.path("unreadCount").asLong(), "回带最新未读数：" + live);

    // 收尾：收口流（清理注册表，避免影响其他用例）
    broadcaster.push(bId, "close", "");
  }

  /** 广播器单测面：注册、投递、异常流清理（不经过 HTTP，直接验投递与计数）。 */
  @Test
  void broadcaster_delivers_to_registered_streams_only() {
    Long me = 424242L;
    SseEmitter healthy = broadcaster.register(me);
    assertNotNull(healthy);
    assertEquals(1, broadcaster.streamCount(me));

    // 正常投递不抛错；未注册用户静默 no-op（不得抛错）
    broadcaster.push(me, "message", "payload");
    broadcaster.push(999999L, "message", "nobody");
    assertEquals(1, broadcaster.streamCount(me), "投递失败不应误删健康流");

    // 已收口的流：再次投递 → 发送抛错 → 注册表自动清理（不打断其他流）
    healthy.complete();
    healthy.completeWithError(new IllegalStateException("closed"));
    broadcaster.push(me, "message", "after-close");
    assertEquals(0, broadcaster.streamCount(me), "失效流应被清理出注册表");
  }

  /** 超限拒绝：同步 429 + `error` 帧（前端据此切轮询），且不占用异步响应。 */
  @Test
  void stream_rejects_beyond_per_user_limit() throws Exception {
    String a = registerUser("dm_limit_a");
    long aId = userIdOf("dm_limit_a");

    for (int i = 0; i < DmBroadcaster.MAX_STREAMS_PER_USER; i++) {
      MvcResult ok =
          mockMvc
              .perform(
                  get("/api/v1/community/messages/stream")
                      .header("Authorization", bearer(a))
                      .accept(MediaType.TEXT_EVENT_STREAM))
              .andExpect(MockMvcResultMatchers.request().asyncStarted())
              .andReturn();
      assertTrue(hasFrame(ok, "open"), "第 " + (i + 1) + " 条流应建流成功");
    }
    assertEquals(DmBroadcaster.MAX_STREAMS_PER_USER, broadcaster.streamCount(aId));

    MvcResult rejected =
        mockMvc
            .perform(
                get("/api/v1/community/messages/stream")
                    .header("Authorization", bearer(a))
                    .accept(MediaType.TEXT_EVENT_STREAM))
            .andReturn();
    assertEquals(429, rejected.getResponse().getStatus(), "超限应回 429");
    String body = rejected.getResponse().getContentAsString(StandardCharsets.UTF_8);
    assertTrue(body.contains("event:error") && body.contains("stream-limit"), "应含 error 帧：" + body);
  }

  // ------------------------------------------------------------------ SSE 帧解析工具

  /** 响应里是否已包含指定事件名的帧。 */
  private boolean hasFrame(MvcResult result, String event) {
    return frameData(result, event) != null;
  }

  /**
   * 取指定事件名的最后一帧 data。
   *
   * <p>MockMvc 的异步流响应：帧已由 `SseEmitter` 预格式化后直接写入 MockHttpServletResponse （形如
   * `event:open\ndata:{...}\n\n`）。
   */
  private String frameData(MvcResult result, String event) {
    List<String> matched = new ArrayList<>();
    for (String block : responseBlocks(result)) {
      if (block.contains("event:" + event)) {
        for (String line : block.split("\n")) {
          if (line.startsWith("data:")) {
            matched.add(line.substring("data:".length()).trim());
          }
        }
      }
    }
    return matched.isEmpty() ? null : matched.get(matched.size() - 1);
  }

  /** 取全部 data 帧（按出现顺序）；{@code skip} = 跳过前 N 帧。 */
  private List<String> framesAfter(MvcResult result, int skip) {
    List<String> out = new ArrayList<>();
    for (String block : responseBlocks(result)) {
      for (String line : block.split("\n")) {
        if (line.startsWith("data:")) {
          out.add(line.substring("data:".length()).trim());
        }
      }
    }
    return skip > 0 && out.size() > skip
        ? out.subList(skip, out.size())
        : (skip > 0 ? List.of() : out);
  }

  private List<String> responseBlocks(MvcResult result) {
    String raw;
    try {
      raw = result.getResponse().getContentAsString(StandardCharsets.UTF_8);
    } catch (Exception e) {
      raw = "";
    }
    return List.of(raw.split("\n\n"));
  }
}
