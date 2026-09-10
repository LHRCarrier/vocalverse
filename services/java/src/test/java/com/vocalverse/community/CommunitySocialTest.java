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
import com.vocalverse.user.UserEntity;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

/**
 * 社区 S2 关注/通知测试（H2 · docs/41）：关注幂等与越权、关注列表/推荐、关注流 keyset、 通知 mergeKey 聚合（多人赞合并「等 N
 * 人」/评论逐条/排除自身动作/仅本人可见帖）。
 */
@Transactional
class CommunitySocialTest extends AbstractAdminApiTest {

  @Autowired private PostRepository posts;
  @Autowired private PostCommentRepository comments;
  @Autowired private PostInteractionRepository interactions;
  @Autowired private jakarta.persistence.EntityManagerFactory entityManagerFactory;

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

  private long createPost(String token) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"title\":\"S2 帖\",\"body\":\"关注流测试内容\",\"kind\":\"article\",\"domain\":\"news\"}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
    return root.path("data").path("id").asLong();
  }

  @Test
  void follow_unfollow_idempotent_and_validation() throws Exception {
    String a = registerUser("s2_follow_a");
    String b = registerUser("s2_follow_b");
    long bId = userIdOf("s2_follow_b");

    // 关注 → 幂等（重复 PUT 不报错）
    MvcResult r =
        mockMvc
            .perform(put("/api/v1/community/follows/" + bId).header("Authorization", bearer(a)))
            .andReturn();
    assertEquals(CODE_OK, json(r).path("code").asInt());
    r =
        mockMvc
            .perform(put("/api/v1/community/follows/" + bId).header("Authorization", bearer(a)))
            .andReturn();
    assertEquals(CODE_OK, json(r).path("code").asInt());

    // 自关注 42203
    long aId = userIdOf("s2_follow_a");
    r =
        mockMvc
            .perform(put("/api/v1/community/follows/" + aId).header("Authorization", bearer(a)))
            .andReturn();
    assertEquals(42203, json(r).path("code").asInt());

    // 目标不存在 40402
    r =
        mockMvc
            .perform(put("/api/v1/community/follows/999999").header("Authorization", bearer(a)))
            .andReturn();
    assertEquals(40402, json(r).path("code").asInt());

    // 列表含 b；取消 → 列表空（幂等）
    JsonNode list =
        json(
            mockMvc
                .perform(get("/api/v1/community/follows").header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(1, list.path("data").size());
    assertEquals("s2_follow_b", list.path("data").get(0).path("author").path("nickname").asText());

    assertEquals(
        CODE_OK,
        json(mockMvc
                .perform(
                    delete("/api/v1/community/follows/" + bId).header("Authorization", bearer(a)))
                .andReturn())
            .path("code")
            .asInt());
    list =
        json(
            mockMvc
                .perform(get("/api/v1/community/follows").header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(0, list.path("data").size());
  }

  @Test
  void recommendations_exclude_self_and_mark_followed() throws Exception {
    String a = registerUser("s2_rec_a");
    registerUser("s2_rec_b");
    long bId = userIdOf("s2_rec_b");
    mockMvc
        .perform(put("/api/v1/community/follows/" + bId).header("Authorization", bearer(a)))
        .andReturn();

    JsonNode recs =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/follows/recommendations")
                        .header("Authorization", bearer(a)))
                .andReturn());
    // 不含自己
    assertFalse(
        java.util.stream.StreamSupport.stream(recs.path("data").spliterator(), false)
            .anyMatch(n -> n.path("author").path("id").asLong() == userIdOf("s2_rec_a")));
    // 已关注的作者 followed=true
    JsonNode bNode =
        java.util.stream.StreamSupport.stream(recs.path("data").spliterator(), false)
            .filter(n -> n.path("author").path("nickname").asText().equals("s2_rec_b"))
            .findFirst()
            .orElseThrow();
    assertTrue(bNode.path("followed").asBoolean());
  }

  /** J-06：推荐关注 limit 生效 + SQL 往返恒定（批量聚合作者/关注判定，防 3N+1 回潮）。 */
  @Test
  void recommendations_limit_and_constant_roundtrips() throws Exception {
    String a = registerUser("j06_rec_a");
    for (int i = 0; i < 7; i++) {
      registerUser("j06_rec_" + i);
    }

    // limit=3 → 只回 3 条（默认 50；修复前全表返回 → 新契约防全量加载）
    JsonNode page =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/follows/recommendations?limit=3")
                        .header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(3, page.path("data").size(), page.toString());

    // 往返恒定：users 分页 1 + 作者批量 2（users+profiles）+ 关注批量 1 ≈ 4
    // （修复前：全表 1 + 7 用户 × 3 查询 = 22+）
    org.hibernate.SessionFactory sf =
        entityManagerFactory.unwrap(org.hibernate.SessionFactory.class);
    sf.getStatistics().clear();
    mockMvc
        .perform(
            get("/api/v1/community/follows/recommendations?limit=50")
                .header("Authorization", bearer(a)))
        .andReturn();
    long statements = sf.getStatistics().getPrepareStatementCount();
    assertTrue(statements <= 8, "推荐关注 SQL 往返应恒定（J-06 批量聚合），实际 " + statements);
  }

  @Test
  void following_feed_only_contains_followed_authors() throws Exception {
    String a = registerUser("s2_ff_a");
    String b = registerUser("s2_ff_b");
    long aId = userIdOf("s2_ff_a");
    createPost(b); // B 自己的帖（不出现在自己的关注流——关注流=被关注作者的帖子）
    long postAAuthor = createPost(a); // A 的帖（B 关注 A 后可看到）

    // b 未关注任何人 → 空
    JsonNode feed =
        json(
            mockMvc
                .perform(get("/api/v1/community/following-feed").header("Authorization", bearer(b)))
                .andReturn());
    assertEquals(0, feed.path("data").path("items").size());

    // b 关注 a → 关注流只含 a 的帖子
    mockMvc
        .perform(put("/api/v1/community/follows/" + aId).header("Authorization", bearer(b)))
        .andReturn();
    feed =
        json(
            mockMvc
                .perform(get("/api/v1/community/following-feed").header("Authorization", bearer(b)))
                .andReturn());
    assertEquals(1, feed.path("data").path("items").size());
    assertEquals(postAAuthor, feed.path("data").path("items").get(0).path("id").asLong());
  }

  @Test
  void notifications_merge_likes_and_split_comments() throws Exception {
    String author = registerUser("s2_nt_author");
    String liker1 = registerUser("s2_nt_liker1");
    String liker2 = registerUser("s2_nt_liker2");
    long authorId = userIdOf("s2_nt_author");
    long liker1Id = userIdOf("s2_nt_liker1");
    long postId = createPost(author);

    // 他人点赞 ×2 → 聚合「等 2 人」；他人评论 → 逐条
    mockMvc
        .perform(
            put("/api/v1/community/posts/" + postId + "/likes")
                .header("Authorization", bearer(liker1)))
        .andReturn();
    mockMvc
        .perform(
            put("/api/v1/community/posts/" + postId + "/likes")
                .header("Authorization", bearer(liker2)))
        .andReturn();
    mockMvc
        .perform(
            post("/api/v1/community/posts/" + postId + "/comments")
                .header("Authorization", bearer(liker1))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"body\":\"好帖\"}".getBytes(StandardCharsets.UTF_8)))
        .andReturn();
    // 自赞不通知（作者自己点自己帖子赞 → 过滤）
    mockMvc
        .perform(
            put("/api/v1/community/posts/" + postId + "/likes")
                .header("Authorization", bearer(author)))
        .andReturn();

    JsonNode noti =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/notifications").header("Authorization", bearer(author)))
                .andReturn());
    JsonNode items = noti.path("data").path("items");
    // like 聚合一条（count=2）+ comment 一条 = 2
    assertEquals(2, items.size(), noti.toString());

    JsonNode likeNoti =
        java.util.stream.StreamSupport.stream(items.spliterator(), false)
            .filter(n -> n.path("type").asText().equals("like"))
            .findFirst()
            .orElseThrow();
    assertEquals(2, likeNoti.path("actorCount").asInt());
    assertEquals(postId, likeNoti.path("postId").asLong());
    assertEquals("S2 帖", likeNoti.path("postTitle").asText());

    JsonNode commentNoti =
        java.util.stream.StreamSupport.stream(items.spliterator(), false)
            .filter(n -> n.path("type").asText().equals("comment"))
            .findFirst()
            .orElseThrow();
    assertEquals("好帖", commentNoti.path("commentBody").asText());
  }

  @Test
  void notifications_only_my_visible_posts_and_cursor() throws Exception {
    String a = registerUser("s2_nt2_a");
    String b = registerUser("s2_nt2_b");
    long aId = userIdOf("s2_nt2_a");
    long postA = createPost(a);
    long postB = createPost(b); // B 的帖子（A 看不到其通知）

    mockMvc
        .perform(
            put("/api/v1/community/posts/" + postA + "/likes").header("Authorization", bearer(b)))
        .andReturn();
    mockMvc
        .perform(
            put("/api/v1/community/posts/" + postB + "/likes").header("Authorization", bearer(a)))
        .andReturn();

    // A 的通知只含自己帖子的非自身动作（B 赞 A 帖 → 1 条；A 赞 B 帖不通知 A）
    JsonNode noti =
        json(
            mockMvc
                .perform(get("/api/v1/community/notifications").header("Authorization", bearer(a)))
                .andReturn());
    assertEquals(1, noti.path("data").path("items").size());
    assertEquals(postA, noti.path("data").path("items").get(0).path("postId").asLong());
  }

  /** J-04：软删/隐藏评论不得在通知里「复活」（findMine 须过滤 c.status='visible'）。 */
  @Test
  void notifications_exclude_softdeleted_comments() throws Exception {
    String author = registerUser("s2_nt3_a");
    String b = registerUser("s2_nt3_b");
    long postId = createPost(author);

    MvcResult comment =
        mockMvc
            .perform(
                post("/api/v1/community/posts/" + postId + "/comments")
                    .header("Authorization", bearer(b))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"body\":\"会被删的评论\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode c1 = json(comment);
    assertEquals(CODE_OK, c1.path("code").asInt(), c1.toString());
    long commentId = c1.path("data").path("id").asLong();

    // 拆除前：通知含 1 条评论
    JsonNode before =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/notifications").header("Authorization", bearer(author)))
                .andReturn());
    assertEquals(1, before.path("data").path("items").size(), before.toString());

    // 软删评论（status=deleted；评论展示路径 page() 早已过滤，唯独通知 findMine 没有——J-04）
    PostCommentEntity c = comments.findById(commentId).orElseThrow();
    c.setStatus("deleted");
    comments.save(c);

    JsonNode after =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/notifications").header("Authorization", bearer(author)))
                .andReturn());
    assertEquals(0, after.path("data").path("items").size(), "软删评论不得出现在通知：\n" + after);

    // 同口径覆盖 hidden（隐藏评论同样不通知）
    MvcResult c2 =
        mockMvc
            .perform(
                post("/api/v1/community/posts/" + postId + "/comments")
                    .header("Authorization", bearer(b))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"body\":\"会被隐藏的评论\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    long hiddenId = json(c2).path("data").path("id").asLong();
    PostCommentEntity h = comments.findById(hiddenId).orElseThrow();
    h.setStatus("hidden");
    comments.save(h);
    JsonNode after2 =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/notifications").header("Authorization", bearer(author)))
                .andReturn());
    assertEquals(0, after2.path("data").path("items").size(), "隐藏评论不得出现在通知：\n" + after2);
  }

  // ------------------------------------------------------------------ J-03：通知分页跨窗口（DB 层 keyset +
  // SQL 聚合）

  /**
   * J-03：通知必须能**跨窗口翻页**——旧实现取「近 50 条互动/评论」后在内存里按游标重筛， 第 51 条及更早的数据永远不可见（docs/41 §1 登记）。修复前：第 2
   * 页为空（游标落在窗口外，窗口内所有行都比游标新）。
   */
  @Test
  void notifications_paging_beyond_window_no_loss() throws Exception {
    String author = registerUser("j03_a");
    long postId = createPost(author);

    // 60 个独立聚合组：60 个不同 actor、60 个不同 UTC 日期（mergeKey = post|action|当日）
    for (int i = 0; i < 60; i++) {
      UserEntity actor = newUser("j03_actor" + i);
      interactions.insertIgnoreConflict(
          actor.getId(), postId, "like", Instant.now().minus(i, ChronoUnit.DAYS));
    }
    entityManagerFactory.unwrap(org.hibernate.SessionFactory.class).getStatistics().clear();

    Set<String> seen = new HashSet<>();
    String cursor = null;
    int pages = 0;
    while (pages < 12) {
      String url =
          "/api/v1/community/notifications?limit=10" + (cursor == null ? "" : "&cursor=" + cursor);
      JsonNode page =
          json(mockMvc.perform(get(url).header("Authorization", bearer(author))).andReturn());
      JsonNode items = page.path("data").path("items");
      if (items.isEmpty()) break;
      for (JsonNode it : items) {
        assertTrue(seen.add(it.path("id").asText()), "通知 id 不得重复：" + it);
      }
      pages++;
      if (!page.path("data").path("hasMore").asBoolean()) break;
      cursor = page.path("data").path("nextCursor").asText();
    }

    assertEquals(60, seen.size(), "通知应能跨窗口翻完全部 60 组（修复前窗口只含最近 50 条、第 2 页即空）：pages=" + pages);
    assertTrue(pages >= 6, "60 组 / 每页 10 应至少 6 页，实际 " + pages);
  }

  /** J-03：评论流同样跨窗口（评论逐条，不受互动窗口截断）。 */
  @Test
  void notifications_comments_beyond_window_no_loss() throws Exception {
    String author = registerUser("j03_c_a");
    String commenter = registerUser("j03_c_b");
    long postId = createPost(author);
    long commenterId = userIdOf("j03_c_b");

    for (int i = 0; i < 60; i++) {
      PostCommentEntity c = new PostCommentEntity();
      c.setPostId(postId);
      c.setAuthorId(commenterId);
      c.setBody("跨窗口评论 " + i);
      c.setStatus("visible");
      c.setCreatedAt(Instant.now().minus(i, ChronoUnit.HOURS));
      c.setUpdatedAt(c.getCreatedAt());
      comments.save(c);
    }
    comments.flush();

    Set<String> seen = new HashSet<>();
    String cursor = null;
    for (int page = 0; page < 12; page++) {
      String url =
          "/api/v1/community/notifications?limit=10" + (cursor == null ? "" : "&cursor=" + cursor);
      JsonNode body =
          json(mockMvc.perform(get(url).header("Authorization", bearer(author))).andReturn());
      JsonNode items = body.path("data").path("items");
      if (items.isEmpty()) break;
      for (JsonNode it : items) {
        if ("comment".equals(it.path("type").asText())) {
          seen.add(it.path("id").asText());
        }
      }
      if (!body.path("data").path("hasMore").asBoolean()) break;
      cursor = body.path("data").path("nextCursor").asText();
    }
    assertEquals(60, seen.size(), "评论通知应跨窗口翻全 60 条（修复前窗口 50 条封顶）");
  }

  private UserEntity newUser(String username) {
    Instant now = Instant.now();
    UserEntity u = new UserEntity();
    u.setUsername(username);
    u.setPasswordHash(passwordEncoder.encode("password123"));
    u.setNickname(username);
    u.setRole("user");
    u.setStatus("active");
    u.setCreatedAt(now);
    u.setUpdatedAt(now);
    return users.save(u);
  }
}
