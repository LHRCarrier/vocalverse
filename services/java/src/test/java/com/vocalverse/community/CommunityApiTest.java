package com.vocalverse.community;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

/**
 * 社区 C 端契约/幂等/权限测试（H2 · docs/37 §9）。
 *
 * <p>说明：① H2 无法建 PG 部分唯一索引（uq_posts_checkin 每日一卡），DB 级守护由 alembic check 真 PG 零 diff + service
 * 层幂等承担（docs/40 §5 风险表回退项）；② 类级 @Transactional 保证每个方法回滚（MockMvc 同线程执行，服务事务并入 测试事务），方法间互不泄漏。
 */
@Transactional
class CommunityApiTest extends AbstractAdminApiTest {

  @Autowired private PostRepository posts;
  @Autowired private jakarta.persistence.EntityManagerFactory entityManagerFactory;

  private static final int CODE_OK = 0;

  private String bearer(String token) {
    return "Bearer " + token;
  }

  private JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  private long createPost(String token, String domain) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                                "{\"title\":\"T\",\"body\":\"Hello world practice\",\"kind\":\"article\",\"domain\":\"%s\"}",
                                domain)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
    return root.path("data").path("id").asLong();
  }

  @Test
  void feed_create_detail_flow() throws Exception {
    String token = registerUser("comm_a");
    // 初始 feed 空
    JsonNode feed =
        json(
            mockMvc
                .perform(get("/api/v1/community/posts").header("Authorization", bearer(token)))
                .andReturn());
    assertEquals(0, feed.path("data").path("items").size());

    // 发帖（领域 news）→ feed 可见 + 作者字段齐全
    long id = createPost(token, "news");
    feed =
        json(
            mockMvc
                .perform(get("/api/v1/community/posts").header("Authorization", bearer(token)))
                .andReturn());
    JsonNode item = feed.path("data").path("items").get(0);
    assertEquals(id, item.path("id").asLong());
    assertEquals("article", item.path("kind").asText());
    assertEquals("news", item.path("domain").asText());
    assertEquals("comm_a", item.path("author").path("nickname").asText());
    assertEquals("L1", item.path("author").path("level").asText());
    assertFalse(item.path("liked").asBoolean());

    // 领域过滤：teaching 不出 news 帖
    feed =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/posts?domain=teaching")
                        .header("Authorization", bearer(token)))
                .andReturn());
    assertEquals(0, feed.path("data").path("items").size());

    // 越权域参数 → 42203
    MvcResult bad =
        mockMvc
            .perform(
                get("/api/v1/community/posts?domain=xxx").header("Authorization", bearer(token)))
            .andReturn();
    assertEquals(42203, json(bad).path("code").asInt());

    // 详情
    JsonNode detail =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/posts/" + id).header("Authorization", bearer(token)))
                .andReturn());
    assertEquals(id, detail.path("data").path("id").asLong());
  }

  @Test
  void createPost_validation() throws Exception {
    String token = registerUser("comm_v");
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"body\":\"x\",\"kind\":\"video\",\"domain\":\"overseas\"}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(CODE_OK, json(r).path("code").asInt()); // kind=video 合法

    r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"body\":\"x\",\"kind\":\"checkin\",\"domain\":\"news\"}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(42203, json(r).path("code").asInt()); // checkin 不接受

    r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"body\":\"\",\"kind\":\"article\",\"domain\":\"news\"}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(42203, json(r).path("code").asInt()); // 空正文
  }

  @Test
  void like_unlike_idempotent_and_count() throws Exception {
    String a = registerUser("comm_like_a");
    String b = registerUser("comm_like_b");
    long id = createPost(a, "news");

    JsonNode like =
        json(
            mockMvc
                .perform(
                    put("/api/v1/community/posts/" + id + "/likes")
                        .header("Authorization", bearer(b)))
                .andReturn());
    assertTrue(like.path("data").path("liked").asBoolean());
    assertEquals(1, like.path("data").path("likeCount").asInt());

    // 重复点赞幂等：不双计
    like =
        json(
            mockMvc
                .perform(
                    put("/api/v1/community/posts/" + id + "/likes")
                        .header("Authorization", bearer(b)))
                .andReturn());
    assertEquals(1, like.path("data").path("likeCount").asInt());

    // 取消 → 归零；再取消幂等（GREATEST 护底不穿负）
    like =
        json(
            mockMvc
                .perform(
                    delete("/api/v1/community/posts/" + id + "/likes")
                        .header("Authorization", bearer(b)))
                .andReturn());
    assertFalse(like.path("data").path("liked").asBoolean());
    assertEquals(0, like.path("data").path("likeCount").asInt());
    like =
        json(
            mockMvc
                .perform(
                    delete("/api/v1/community/posts/" + id + "/likes")
                        .header("Authorization", bearer(b)))
                .andReturn());
    assertEquals(0, like.path("data").path("likeCount").asInt());
  }

  @Test
  void coin_once_idempotent_irreversible() throws Exception {
    String a = registerUser("comm_coin_a");
    String b = registerUser("comm_coin_b");
    long id = createPost(a, "news");

    JsonNode coin =
        json(
            mockMvc
                .perform(
                    put("/api/v1/community/posts/" + id + "/coins")
                        .header("Authorization", bearer(b)))
                .andReturn());
    assertTrue(coin.path("data").path("coined").asBoolean());
    assertEquals(1, coin.path("data").path("coinCount").asInt());

    // 幂等：重复投币不加计
    coin =
        json(
            mockMvc
                .perform(
                    put("/api/v1/community/posts/" + id + "/coins")
                        .header("Authorization", bearer(b)))
                .andReturn());
    assertEquals(1, coin.path("data").path("coinCount").asInt());

    // 不可取消：无 DELETE /coins 端点（405 Method Not Allowed）
    MvcResult delete =
        mockMvc
            .perform(
                delete("/api/v1/community/posts/" + id + "/coins")
                    .header("Authorization", bearer(b)))
            .andReturn();
    assertEquals(405, delete.getResponse().getStatus());
  }

  @Test
  void share_once_idempotent() throws Exception {
    String a = registerUser("comm_share_a");
    String b = registerUser("comm_share_b");
    long id = createPost(a, "news");

    JsonNode share =
        json(
            mockMvc
                .perform(
                    post("/api/v1/community/posts/" + id + "/shares")
                        .header("Authorization", bearer(b)))
                .andReturn());
    assertEquals(1, share.path("data").path("shareCount").asInt());
    share =
        json(
            mockMvc
                .perform(
                    post("/api/v1/community/posts/" + id + "/shares")
                        .header("Authorization", bearer(b)))
                .andReturn());
    assertEquals(1, share.path("data").path("shareCount").asInt());
  }

  @Test
  void checkin_card_only_like_allowed() throws Exception {
    String a = registerUser("comm_ck_a");
    String b = registerUser("comm_ck_b");
    long id = seedCheckin("comm_ck_a");

    // 点赞允许
    assertEquals(
        CODE_OK,
        json(mockMvc
                .perform(
                    put("/api/v1/community/posts/" + id + "/likes")
                        .header("Authorization", bearer(b)))
                .andReturn())
            .path("code")
            .asInt());

    // 评论/投币/分享 40302
    MvcResult comment =
        mockMvc
            .perform(
                post("/api/v1/community/posts/" + id + "/comments")
                    .header("Authorization", bearer(b))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"body\":\"hi\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(40302, json(comment).path("code").asInt());
    assertEquals(
        40302,
        json(mockMvc
                .perform(
                    put("/api/v1/community/posts/" + id + "/coins")
                        .header("Authorization", bearer(b)))
                .andReturn())
            .path("code")
            .asInt());
    assertEquals(
        40302,
        json(mockMvc
                .perform(
                    post("/api/v1/community/posts/" + id + "/shares")
                        .header("Authorization", bearer(b)))
                .andReturn())
            .path("code")
            .asInt());
  }

  @Test
  void comments_add_and_page() throws Exception {
    String a = registerUser("comm_cmt_a");
    long id = createPost(a, "teaching");
    for (int i = 1; i <= 3; i++) {
      mockMvc
          .perform(
              post("/api/v1/community/posts/" + id + "/comments")
                  .header("Authorization", bearer(a))
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(
                      String.format("{\"body\":\"comment %d\"}", i)
                          .getBytes(StandardCharsets.UTF_8)))
          .andReturn();
    }
    // 计数回读
    JsonNode detail =
        json(
            mockMvc
                .perform(get("/api/v1/community/posts/" + id).header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(3, detail.path("data").path("commentCount").asInt());

    // 第一页 2 条 + hasMore + 游标翻页
    JsonNode page1 =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/posts/" + id + "/comments?limit=2")
                        .header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(2, page1.path("data").path("items").size());
    assertTrue(page1.path("data").path("hasMore").asBoolean());
    String cursor = page1.path("data").path("nextCursor").asText();
    JsonNode page2 =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/posts/" + id + "/comments?limit=2&cursor=" + cursor)
                        .header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(1, page2.path("data").path("items").size(), page2.toString());
    assertFalse(page2.path("data").path("hasMore").asBoolean());
  }

  /** J-05：评论页 SQL 往返数恒定（批量聚合作者，防 N+1 回潮）——20 位不同评论者的一页。 */
  @Test
  void comments_page_constant_roundtrips_after_batch() throws Exception {
    String a = registerUser("j05_own");
    long postId = createPost(a, "news");
    // 20 位不同评论者：修复前逐条 loadAuthors（2 查询/条）≈41 次往返；修复后批量 ≈4 次
    for (int i = 0; i < 20; i++) {
      String ct = registerUser("j05_c" + i);
      mockMvc
          .perform(
              post("/api/v1/community/posts/" + postId + "/comments")
                  .header("Authorization", bearer(ct))
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(
                      String.format("{\"body\":\"comment %d\"}", i)
                          .getBytes(StandardCharsets.UTF_8)))
          .andReturn();
    }
    org.hibernate.SessionFactory sf =
        entityManagerFactory.unwrap(org.hibernate.SessionFactory.class);
    sf.getStatistics().clear();
    MvcResult page =
        mockMvc
            .perform(
                get("/api/v1/community/posts/" + postId + "/comments?limit=20")
                    .header("Authorization", bearer(a)))
            .andReturn();
    assertEquals(20, json(page).path("data").path("items").size(), page.toString());
    long statements = sf.getStatistics().getPrepareStatementCount();
    assertTrue(statements <= 8, "评论页 SQL 往返应恒定（J-05 批量聚合），实际 " + statements);
  }

  @Test
  void feed_cursor_pagination_no_duplicates() throws Exception {
    String a = registerUser("comm_page_a");
    for (int i = 0; i < 5; i++) {
      createPost(a, "news");
    }
    String cursor = null;
    Map<Long, Boolean> seen = new HashMap<>();
    int pages = 0;
    do {
      String url = "/api/v1/community/posts?limit=2" + (cursor == null ? "" : "&cursor=" + cursor);
      JsonNode page =
          json(mockMvc.perform(get(url).header("Authorization", bearer(a))).andReturn());
      for (JsonNode item : page.path("data").path("items")) {
        assertFalse(seen.containsKey(item.path("id").asLong()), "游标分页重复：" + item);
        seen.put(item.path("id").asLong(), true);
      }
      cursor = page.path("data").path("nextCursor").asText(null);
      pages++;
    } while (cursor != null && pages < 5);
    assertEquals(5, seen.size());
  }

  @Test
  void delete_only_own_and_hidden_hidden() throws Exception {
    String a = registerUser("comm_del_a");
    String b = registerUser("comm_del_b");
    long id = createPost(a, "overseas");

    // B 删 A 的帖 → 40302
    MvcResult forbid =
        mockMvc
            .perform(delete("/api/v1/community/posts/" + id).header("Authorization", bearer(b)))
            .andReturn();
    assertEquals(40302, json(forbid).path("code").asInt());

    // A 删自己的帖 → 200；feed 消失；B 详情 40402；重复删 40402（幂等视为不存在）
    assertEquals(
        CODE_OK,
        json(mockMvc
                .perform(delete("/api/v1/community/posts/" + id).header("Authorization", bearer(a)))
                .andReturn())
            .path("code")
            .asInt());
    JsonNode feed =
        json(
            mockMvc
                .perform(get("/api/v1/community/posts").header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(0, feed.path("data").path("items").size());
    assertEquals(
        40402,
        json(mockMvc
                .perform(get("/api/v1/community/posts/" + id).header("Authorization", bearer(b)))
                .andReturn())
            .path("code")
            .asInt());
    assertEquals(
        40402,
        json(mockMvc
                .perform(delete("/api/v1/community/posts/" + id).header("Authorization", bearer(a)))
                .andReturn())
            .path("code")
            .asInt());
  }

  @Test
  void unauth_403() throws Exception {
    // SecurityConfig 无 AuthenticationEntryPoint：匿名访问受保护端点 → 403（非 401）
    MvcResult r = mockMvc.perform(get("/api/v1/community/posts")).andReturn();
    assertEquals(403, r.getResponse().getStatus());
  }

  private long seedCheckin(String authorName) throws Exception {
    // 直插打卡卡（模拟 /internal/checkin 物化结果；测试库 seed=false 故需自建）
    Long userId = users.findByUsernameIgnoreCase(authorName).orElseThrow().getId();
    PostEntity e = new PostEntity();
    e.setAuthorId(userId);
    e.setKind("checkin");
    e.setTitle("今日打卡");
    e.setStatus("visible");
    e.setCheckinDate(java.time.LocalDate.now());
    e.setCheckinSnapshot(
        "{\"overall\":80.0,\"pron\":82.0,\"gram\":78.0,\"fluency\":79.0,\"turns\":8,\"duration_s\":260,\"practice_count\":1}");
    Instant now = Instant.now();
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return posts.save(e).getId();
  }
}
