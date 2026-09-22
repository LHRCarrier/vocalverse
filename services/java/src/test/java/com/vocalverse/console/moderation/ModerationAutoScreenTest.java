package com.vocalverse.console.moderation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.sun.net.httpserver.HttpServer;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 自动送审链路（docs/58）：内容发布 → Jev 判定 → {@code source='auto'} 建单。
 *
 * <h2>为什么起一个真的 HTTP 桩而不是 mock 掉客户端</h2>
 *
 * <p>本用例要验证的正是「HTTP 请求体长什么样、响应怎么解析、失败怎么降级」——mock 掉 {@code JevDecisionClient} 会把这三点全部跳过，只剩下对 Mockito
 * 的断言。桩服务用 JDK 自带的 {@link HttpServer}（零新依赖），按 canned 响应控制判定结果。
 *
 * <p>{@code async=false}（SyncTaskExecutor）让 AFTER_COMMIT 监听器在请求线程内跑完 —— 断言不需要等待/轮询，
 * 也不会出现「测试偶发看不到审核单」。生产档是异步（application.yml 默认 true）。
 *
 * <p>类上**没有** {@code @Transactional}：事件在提交后才触发，测试事务会让提交永远不发生， 监听器一次都不会跑（这正是本用例要覆盖的接线）。
 */
class ModerationAutoScreenTest extends AbstractConsoleApiTest {

  /** 桩响应：status + body。测试方法通过 {@link #CANNED} 切换。 */
  private record Canned(int status, String body) {}

  private static final String VIOLATION_BODY =
      """
      {"model":"jev-1.13.0","answers":{
        "is_violation":{"type":"noul","noul":0.96},
        "clause":{"type":"choice","choice":"R2","probabilities":{"R2":0.88,"none":0.12},"confidence":0.81},
        "severity":{"type":"score","score":1.96,"legend":{"0":"无问题","1":"轻微","2":"中等","3":"严重"},
                    "probabilities":{"0":0.0,"1":0.21,"2":0.62,"3":0.17},"confidence":0.61}},
       "usage":{"input_tokens":362,"output_tokens":36}}
      """;

  private static final String BENIGN_BODY =
      """
      {"model":"jev-1.13.0","answers":{
        "is_violation":{"type":"noul","noul":0.05},
        "clause":{"type":"choice","choice":"none","probabilities":{"none":0.95},"confidence":0.9},
        "severity":{"type":"score","score":0.1,"legend":{"0":"无问题"},"probabilities":{"0":0.95},"confidence":0.9}},
       "usage":{"input_tokens":120,"output_tokens":20}}
      """;

  private static final AtomicReference<Canned> CANNED =
      new AtomicReference<>(new Canned(200, VIOLATION_BODY));

  private static HttpServer server;

  @DynamicPropertySource
  static void jevProperties(DynamicPropertyRegistry registry) throws Exception {
    server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    server.createContext(
        "/v1/systemone",
        exchange -> {
          Canned canned = CANNED.get();
          byte[] payload = canned.body().getBytes(StandardCharsets.UTF_8);
          exchange.getResponseHeaders().add("Content-Type", "application/json");
          exchange.sendResponseHeaders(canned.status(), payload.length);
          try (OutputStream out = exchange.getResponseBody()) {
            out.write(payload);
          }
        });
    server.start();
    int port = server.getAddress().getPort();
    registry.add("vocalverse.moderation.auto-screen.enabled", () -> true);
    registry.add("vocalverse.moderation.auto-screen.base-url", () -> "http://127.0.0.1:" + port);
    registry.add("vocalverse.moderation.auto-screen.api-key", () -> "test-key");
    registry.add("vocalverse.moderation.auto-screen.async", () -> false);
    registry.add("vocalverse.moderation.auto-screen.threshold", () -> 0.7);
  }

  @AfterAll
  static void stopServer() {
    if (server != null) {
      server.stop(0);
    }
  }

  // ------------------------------------------------------------------ 夹具

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

  private long createPost(String token, String body) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                                "{\"title\":\"T\",\"body\":\"%s\",\"kind\":\"article\",\"domain\":\"news\"}",
                                body)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(0, root.path("code").asInt(), root.toString());
    return root.path("data").path("id").asLong();
  }

  private long addComment(String token, long postId, String body) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/posts/" + postId + "/comments")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format("{\"body\":\"%s\"}", body).getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(0, root.path("code").asInt(), root.toString());
    return root.path("data").path("id").asLong();
  }

  /** 查某目标下的审核单（默认 open 视图）；没有则返回 null。 */
  private JsonNode findCase(String modToken, String targetType, long targetId) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                get("/api/v1/console/moderation/cases")
                    .param("status", "open")
                    .param("targetType", targetType)
                    .param("page_size", "100")
                    .header("Authorization", bearer(modToken)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(0, root.path("code").asInt(), root.toString());
    for (JsonNode row : root.path("data").path("items")) {
      if (row.path("targetId").asLong() == targetId) {
        return row;
      }
    }
    return null;
  }

  private String moderatorToken() throws Exception {
    return seedAdminAndLogin(uniqueName("mod"), "moderator");
  }

  // ------------------------------------------------------------------ 用例

  @Test
  void violationContentCreatesAutoCaseWithEvidence() throws Exception {
    CANNED.set(new Canned(200, VIOLATION_BODY));
    String token = registerUser(uniqueName("auto_u"));
    long postId = createPost(token, "you are an idiot, shut up");

    String mod = moderatorToken();
    JsonNode row = findCase(mod, "post", postId);
    assertNotNull(row, "违规内容应自动建单（source=auto）");
    assertEquals("auto", row.path("source").asText());
    assertEquals("abuse", row.path("reasonCode").asText(), "类型应映射到 reason code");
    assertEquals(2, row.path("priority").asInt(), "severity 1.96 → 中优先级");
    assertEquals("pending", row.path("status").asText());

    // 判定证据写进 snapshot.ai：审核员要能看到「为什么这单在队列里」+ 命中哪条规范
    JsonNode ai = row.path("snapshot").path("ai");
    assertEquals("jev-1.13.0", ai.path("model").asText());
    assertEquals(0.96, ai.path("violation").asDouble(), 1e-9);
    assertEquals("R2", ai.path("clause").asText(), "条款号是判据锚点（docs/59）");
    assertEquals("abuse", ai.path("category").asText());
    assertEquals(0.81, ai.path("clauseConfidence").asDouble(), 1e-9);
    assertEquals(1.96, ai.path("severity").asDouble(), 1e-9);
    assertEquals(362, ai.path("inputTokens").asInt());
  }

  @Test
  void benignContentDoesNotCreateCase() throws Exception {
    CANNED.set(new Canned(200, BENIGN_BODY));
    String token = registerUser(uniqueName("auto_b"));
    long postId = createPost(token, "Great tips for practicing speaking every day!");

    assertNull(findCase(moderatorToken(), "post", postId), "低于阈值不应建单");
  }

  @Test
  void upstreamFailureDegradesWithoutBreakingPublish() throws Exception {
    CANNED.set(new Canned(500, "{\"error\":\"boom\"}"));
    String token = registerUser(uniqueName("auto_f"));
    // 发布本身必须成功（送审是旁路，失败降级放行）
    long postId = createPost(token, "publish must survive jev outage");
    assertTrue(postId > 0);

    assertNull(findCase(moderatorToken(), "post", postId), "上游失败不应建单");
  }

  @Test
  void commentIsScreenedToo() throws Exception {
    CANNED.set(new Canned(200, BENIGN_BODY));
    String token = registerUser(uniqueName("auto_c"));
    long postId = createPost(token, "a clean post");

    CANNED.set(new Canned(200, VIOLATION_BODY));
    long commentId = addComment(token, postId, "spam spam spam buy now");

    JsonNode row = findCase(moderatorToken(), "comment", commentId);
    assertNotNull(row, "评论同样要送审（社区最高频 UGC）");
    assertEquals("auto", row.path("source").asText());
  }

  /**
   * 升级件仍在默认队列里（docs/58 §5.1）。
   *
   * <p>修复前：{@code status='pending'} 的默认筛选把 {@code escalated} 排除在待办之外， 升级 = 单子从队列消失；现在 {@code
   * status='open'} 聚合 {@code pending + escalated}。
   */
  @Test
  void escalatedCaseStaysVisibleInOpenQueue() throws Exception {
    CANNED.set(new Canned(200, VIOLATION_BODY));
    String token = registerUser(uniqueName("auto_e"));
    long postId = createPost(token, "escalate me");

    String mod = moderatorToken();
    JsonNode row = findCase(mod, "post", postId);
    assertNotNull(row);
    long caseId = row.path("id").asLong();

    MvcResult escalated =
        mockMvc
            .perform(
                post("/api/v1/console/moderation/cases/" + caseId + "/decision")
                    .header("Authorization", bearer(mod))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"decision\":\"escalate\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(0, json(escalated).path("code").asInt(), json(escalated).toString());

    assertNotNull(findCase(mod, "post", postId), "升级后仍在 open 队列（修复前会消失）");

    // 旧口径对照：escalated 不在 pending 视图里 —— open 与 pending 确实不同，防止测试假绿
    MvcResult pendingView =
        mockMvc
            .perform(
                get("/api/v1/console/moderation/cases")
                    .param("status", "pending")
                    .param("page_size", "100")
                    .header("Authorization", bearer(mod)))
            .andReturn();
    boolean foundInPending = false;
    for (JsonNode r : json(pendingView).path("data").path("items")) {
      if (r.path("id").asLong() == caseId) {
        foundInPending = true;
      }
    }
    assertFalse(foundInPending, "该单已升级，不应出现在 pending 视图（本断言用于证明 open≠pending）");
  }
}
