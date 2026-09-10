package com.vocalverse.console.moderation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.community.CommunityService;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 隐藏内容必须在**所有**读路径上消失（docs/50 §14.2-Java 第 9 条「跨模块回归，最关键的用例」）。
 *
 * <h2>为什么这个测试覆盖 8 条读路径而不是 3 条</h2>
 *
 * <p>第一版只测了 feed / 详情 / 评论列表。那只覆盖了 {@code PostRepository} 与 {@code PostCommentRepository} ——
 * 而隐藏内容**还会从通知中心泄漏**： {@code PostInteractionRepository} 的两条原生 SQL（互动聚合组 + 评论流）里各自硬编码了 {@code status
 * = 'visible'}，被隐藏帖子的点赞者、评论正文会继续出现在作者的「通知」里。 泄漏的是「谁和哪条内容互动过」这层社交图信息，比正文更难被察觉， 而只测
 * feed/详情/评论的用例**照样全绿**。所以这里加上：
 *
 * <ul>
 *   <li>我的发帖（同一 feed 接口的 authorId 视图）；
 *   <li>关注流（followingFeed，另一条 PostRepository 谓词路径）；
 *   <li>通知中心 —— 互动聚合组（{@code notificationGroups} 原生 SQL）；
 *   <li>通知中心 —— 评论流（{@code notificationComments} 原生 SQL）。
 * </ul>
 */
class ModerationHiddenContentTest extends AbstractConsoleApiTest {

  @Autowired private com.vocalverse.community.PostRepository posts;
  @Autowired private com.vocalverse.community.PostCommentRepository commentRepo;
  @Autowired private com.vocalverse.community.PostInteractionRepository interactions;
  @Autowired private com.vocalverse.config.JwtService appJwt;

  // ------------------------------------------------------------------ 请求助手

  private String registerUser(String username) throws Exception {
    String body =
        String.format(
            "{\"username\":\"%s\",\"password\":\"password123\",\"nickname\":\"%s\",\"ageGroup\":\"adult\"}",
            username, username);
    MvcResult r =
        mockMvc
            .perform(
                post("/auth/register")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(0, json(r).path("code").asInt(), "注册应成功");
    MvcResult login =
        mockMvc
            .perform(
                post("/auth/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                                "{\"username\":\"%s\",\"password\":\"password123\"}", username)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    return json(login).path("data").path("accessToken").asText();
  }

  private JsonNode getJson(String path, String token) throws Exception {
    return json(mockMvc.perform(get(path).header("Authorization", bearer(token))).andReturn());
  }

  private JsonNode postJson(String path, String token, String body) throws Exception {
    var req = post(path).header("Authorization", bearer(token));
    if (body != null) {
      req =
          req.contentType(MediaType.APPLICATION_JSON)
              .content(body.getBytes(StandardCharsets.UTF_8));
    }
    return json(mockMvc.perform(req).andReturn());
  }

  /** 关注端点是 **PUT /api/v1/community/follows/{userId}**（CommunitySocialController）。 */
  private JsonNode follow(String userId, String token) throws Exception {
    return json(
        mockMvc
            .perform(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put(
                        "/api/v1/community/follows/" + userId)
                    .header("Authorization", bearer(token)))
            .andReturn());
  }

  private long createPost(String token, String title) throws Exception {
    JsonNode r =
        postJson(
            "/api/v1/community/posts",
            token,
            String.format(
                "{\"title\":\"%s\",\"body\":\"MARKER_BODY\",\"kind\":\"article\",\"domain\":\"news\"}",
                title));
    assertEquals(0, r.path("code").asInt(), "发帖应成功：" + r);
    return r.path("data").path("id").asLong();
  }

  private JsonNode decide(String consoleToken, long caseId, String decision) throws Exception {
    return postJson(
        "/api/v1/console/moderation/cases/" + caseId + "/decision",
        consoleToken,
        String.format("{\"decision\":\"%s\",\"reasonCode\":\"spam\"}", decision));
  }

  private long openCase(String consoleToken, String targetType, long targetId) throws Exception {
    JsonNode r =
        postJson(
            "/api/v1/console/moderation/cases",
            consoleToken,
            String.format(
                "{\"targetType\":\"%s\",\"targetId\":%d,\"reasonCode\":\"spam\",\"priority\":2}",
                targetType, targetId));
    assertEquals(0, r.path("code").asInt(), "建单应成功：" + r);
    return r.path("data").path("id").asLong();
  }

  private long interactionGroupCount(Long authorId) {
    return interactions
        .notificationGroups(
            authorId, CommunityService.ACTION_LIKE, Instant.now().plusSeconds(60), "", 50)
        .size();
  }

  private long commentStreamCount(Long authorId) {
    return interactions
        .notificationComments(authorId, Instant.now().plusSeconds(60), Long.MAX_VALUE, 50)
        .size();
  }

  // ------------------------------------------------------------------ 主用例

  /** 隐藏帖子 → 8 条读路径全部不可见。 */
  @Test
  void hidden_post_disappears_from_every_read_path() throws Exception {
    String authorToken = registerUser(uniqueName("ha"));
    String otherToken = registerUser(uniqueName("hb"));
    String consoleToken = seedAdminAndLogin(uniqueName("csm"), superRoleCode());
    Long authorId = appJwt.parseUserId(authorToken);

    long postId = createPost(authorToken, "HIDDEN_TITLE_MARKER");

    // 制造互动 + 关注，让通知中心与关注流里真的**有数据**（否则后面的 0 断言是假绿）
    JsonNode like =
        json(
            mockMvc
                .perform(
                    org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put(
                            "/api/v1/community/posts/" + postId + "/likes")
                        .header("Authorization", bearer(otherToken))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"on\":true}".getBytes(StandardCharsets.UTF_8)))
                .andReturn());
    assertEquals(0, like.path("code").asInt(), "点赞应成功：" + like);
    JsonNode comment =
        postJson(
            "/api/v1/community/posts/" + postId + "/comments",
            otherToken,
            "{\"body\":\"SECRET_COMMENT_BODY\"}");
    assertEquals(0, comment.path("code").asInt(), "评论应成功：" + comment);
    follow(String.valueOf(authorId), otherToken);

    // 隐藏前：这些读路径里**确实**能看到内容（正向基线，防止「恒空」的假通过）
    assertTrue(
        getJson("/api/v1/community/posts", authorToken)
            .path("data")
            .path("items")
            .toString()
            .contains("HIDDEN_TITLE_MARKER"),
        "隐藏前 feed 应可见（基线）");
    assertTrue(interactionGroupCount(authorId) > 0, "隐藏前应有互动组（基线）");
    assertTrue(commentStreamCount(authorId) > 0, "隐藏前应有评论流（基线）");
    assertTrue(
        getJson("/api/v1/community/notifications", authorToken)
            .path("data")
            .toString()
            .contains("SECRET_COMMENT_BODY"),
        "隐藏前通知里应有评论正文（基线）");

    // 隐藏
    long caseId = openCase(consoleToken, "post", postId);
    JsonNode decided = decide(consoleToken, caseId, "hide");
    assertEquals(0, decided.path("code").asInt(), "hide 决定应成功：" + decided);
    assertEquals("approved", decided.path("data").path("status").asText());
    assertEquals("hidden", posts.findById(postId).orElseThrow().getStatus());

    // ① feed
    assertFalse(
        getJson("/api/v1/community/posts", authorToken)
            .path("data")
            .path("items")
            .toString()
            .contains("HIDDEN_TITLE_MARKER"),
        "feed 不得出现被隐藏的帖子");
    // ② 详情
    assertNotEquals(
        0,
        getJson("/api/v1/community/posts/" + postId, authorToken).path("code").asInt(),
        "详情应不可见");
    // ③ 评论列表
    assertNotEquals(
        0,
        getJson("/api/v1/community/posts/" + postId + "/comments", authorToken)
            .path("code")
            .asInt(),
        "评论列表应不可见");
    // ④ 我的发帖（docs/50 §6.2 硬点 3：hidden 对作者也隐藏）
    assertFalse(
        getJson("/api/v1/community/posts?authorId=" + authorId, authorToken)
            .path("data")
            .path("items")
            .toString()
            .contains("HIDDEN_TITLE_MARKER"),
        "「我的发帖」不得出现被隐藏的帖子");
    // ⑤ 关注流
    assertFalse(
        getJson("/api/v1/community/following-feed", otherToken)
            .path("data")
            .toString()
            .contains("HIDDEN_TITLE_MARKER"),
        "关注流不得出现被隐藏的帖子");
    // ⑥ 通知中心 · 互动聚合组
    assertEquals(0, interactionGroupCount(authorId), "通知的互动组必须排除被隐藏帖子（否则泄漏「谁赞了我」）");
    // ⑦ 通知中心 · 评论流
    assertEquals(0, commentStreamCount(authorId), "通知的评论流必须排除被隐藏帖子/评论");
    // ⑧ 通知接口本体
    assertFalse(
        getJson("/api/v1/community/notifications", authorToken)
            .path("data")
            .toString()
            .contains("SECRET_COMMENT_BODY"),
        "通知接口不得泄漏被隐藏内容的评论正文");
  }

  /** 隐藏评论 → 该评论从评论列表与通知中心消失（帖子本身仍可见）。 */
  @Test
  void hidden_comment_disappears_from_comment_list_and_notifications() throws Exception {
    String authorToken = registerUser(uniqueName("ca"));
    String otherToken = registerUser(uniqueName("cb"));
    String consoleToken = seedAdminAndLogin(uniqueName("csm"), superRoleCode());
    Long authorId = appJwt.parseUserId(authorToken);

    long postId = createPost(authorToken, "VISIBLE_POST");
    JsonNode comment =
        postJson(
            "/api/v1/community/posts/" + postId + "/comments",
            otherToken,
            "{\"body\":\"COMMENT_TO_HIDE\"}");
    assertEquals(0, comment.path("code").asInt(), comment.toString());
    long commentId = comment.path("data").path("id").asLong();

    assertTrue(
        getJson("/api/v1/community/posts/" + postId + "/comments", authorToken)
            .path("data")
            .path("items")
            .toString()
            .contains("COMMENT_TO_HIDE"),
        "隐藏前评论应可见（基线）");
    assertTrue(commentStreamCount(authorId) > 0, "隐藏前评论流应有数据（基线）");

    long caseId = openCase(consoleToken, "comment", commentId);
    assertEquals(0, decide(consoleToken, caseId, "hide").path("code").asInt());
    assertEquals("hidden", commentRepo.findById(commentId).orElseThrow().getStatus());

    JsonNode after = getJson("/api/v1/community/posts/" + postId + "/comments", authorToken);
    assertEquals(0, after.path("code").asInt(), "帖子仍可见");
    assertFalse(
        after.path("data").path("items").toString().contains("COMMENT_TO_HIDE"), "评论列表不得出现被隐藏的评论");
    assertEquals(0, commentStreamCount(authorId), "通知的评论流不得出现被隐藏评论");
    assertFalse(
        getJson("/api/v1/community/notifications", authorToken)
            .path("data")
            .toString()
            .contains("COMMENT_TO_HIDE"),
        "通知接口不得出现被隐藏评论");
  }

  /** delete 决定 → 目标写 deleted，同样从读路径消失。 */
  @Test
  void deleted_post_disappears_too() throws Exception {
    String authorToken = registerUser(uniqueName("da"));
    String consoleToken = seedAdminAndLogin(uniqueName("csm"), superRoleCode());
    long postId = createPost(authorToken, "TO_DELETE_MARKER");

    long caseId = openCase(consoleToken, "post", postId);
    assertEquals(0, decide(consoleToken, caseId, "delete").path("code").asInt());

    assertEquals("deleted", posts.findById(postId).orElseThrow().getStatus());
    assertFalse(
        getJson("/api/v1/community/posts", authorToken)
            .path("data")
            .path("items")
            .toString()
            .contains("TO_DELETE_MARKER"));
  }

  /**
   * hide 与 delete 互相不可复活：对已经 {@code deleted} 的内容决定 {@code hide} 必须被拒，
   * 而不是把删除悄悄改成隐藏（那等于「审核动作把更严的处置降级」）。
   */
  @Test
  void hide_on_deleted_target_is_rejected_not_resurrected() throws Exception {
    String authorToken = registerUser(uniqueName("ra"));
    String consoleToken = seedAdminAndLogin(uniqueName("csm"), superRoleCode());
    long postId = createPost(authorToken, "RESURRECT_MARKER");

    long firstCase = openCase(consoleToken, "post", postId);
    assertEquals(0, decide(consoleToken, firstCase, "delete").path("code").asInt());
    assertEquals("deleted", posts.findById(postId).orElseThrow().getStatus());

    // 为同一目标再建一单（上一单已终态），然后下 hide
    long secondCase = openCase(consoleToken, "post", postId);
    JsonNode hideAgain = decide(consoleToken, secondCase, "hide");

    assertNotEquals(0, hideAgain.path("code").asInt(), "对已删除内容下 hide 必须被拒：" + hideAgain);
    assertEquals(
        "deleted", posts.findById(postId).orElseThrow().getStatus(), "被拒之后目标状态不得被改动（事务已回滚）");
  }

  /**
   * 审计里的 {@code detail} 必须记录**目标的真实前后状态**，与库里的 {@code posts.status} 一致。
   *
   * <p>这是「审计不得说谎」的直接断言：只记 {@code decision=hide} 而不记 {@code prevStatus/nextStatus}，
   * 事后无法回答「这条内容当时到底可不可见」。
   */
  @Test
  void audit_detail_records_real_target_before_after_status() throws Exception {
    String authorToken = registerUser(uniqueName("aa"));
    String consoleToken = seedAdminAndLogin(uniqueName("csm"), superRoleCode());
    long postId = createPost(authorToken, "AUDIT_MARKER");
    long caseId = openCase(consoleToken, "post", postId);

    assertEquals(0, decide(consoleToken, caseId, "hide").path("code").asInt());
    String persisted = posts.findById(postId).orElseThrow().getStatus();
    assertEquals("hidden", persisted);

    JsonNode detail = getJson("/api/v1/console/moderation/cases/" + caseId, consoleToken);
    assertEquals(0, detail.path("code").asInt(), detail.toString());

    JsonNode history = detail.path("data").path("history");
    assertTrue(history.size() >= 2, "应有建单 + 决定两条历史：" + history);

    JsonNode decideEntry = null;
    for (JsonNode h : history) {
      if ("moderation.decide".equals(h.path("action").asText())) {
        decideEntry = h;
      }
    }
    assertTrue(decideEntry != null, "应存在 moderation.decide 审计：" + history);
    JsonNode d = decideEntry.path("detail");
    assertEquals("hide", d.path("decision").asText(), d.toString());
    assertEquals("pending", d.path("prevStatus").asText(), "审单前态");
    assertEquals("approved", d.path("nextStatus").asText(), "审单后态");
    assertEquals("visible", d.path("before").asText(), "目标的真实前态必须是 visible：" + d);
    assertEquals(
        persisted, d.path("after").asText(), "审计记录的目标后态必须与库里 posts.status 一致（否则审计在说谎）：" + d);
  }
}
