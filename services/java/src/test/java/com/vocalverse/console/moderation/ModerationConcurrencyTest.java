package com.vocalverse.console.moderation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

/**
 * 审核决定的并发正确性（docs/50 §14.2-Java 第 10 条）。
 *
 * <h2>为什么必须真并发</h2>
 *
 * <p>「两个决定只有一成功」这个性质**只有**在真的并发了两个事务时才被验证。 串行地「先决定一次、再决定一次」也能得到「一个成功一个 46010」，但它验证的是「终态不可再决定」，
 * 不是「条件 UPDATE 消除了检查-写入竞态」—— 把实现换成 read-modify-write，串行版本照样全绿。
 *
 * <p>所以这里用 {@link CyclicBarrier} 让两个线程**同时**进入 {@code decide}， 并断言恰好一个成功、一个 46010（不是「至少一个失败」）。
 *
 * <p>测试方法**不加类级 @Transactional**：多线程各自需要独立事务，套在一个测试事务里会变成同一个连接， 那又退化回串行了。
 */
class ModerationConcurrencyTest extends AbstractConsoleApiTest {

  @Autowired private ModerationService moderationService;
  @Autowired private ModerationCaseRepository cases;
  @Autowired private com.vocalverse.community.PostRepository posts;
  @Autowired private com.vocalverse.config.JwtService appJwt;

  /** 在独立线程里登录（MockMvc 的 SecurityContext 是线程绑定的，必须各自登录）。 */
  private String tokenFor(final String username) throws Exception {
    seedAdmin(username, superRoleCode());
    return login(username, FIXTURE_PASSWORD);
  }

  /**
   * 直接建帖（不走 MockMvc）。
   *
   * <p>踩坑（实测）：早先版本用 MockMvc 发帖，然后把返回的 postId 交给带 `@Transactional` 的
   * `ModerationService.create` —— 但那两条路径的**可见性不同**：MockMvc 请求走真实过滤器/事务，
   * 而测试方法自身没有注解，服务层直调读到的是另一个持久化上下文，表现为
   * `46009 审核对象不存在`（明明刚建成功）。这里直接走仓库，让建帖与建单在同一个上下文里，
   * 消除与「并发」无关的噪音 —— 本类要验证的是**决定**的并发，不是建帖的可见性。
   */
  private long createPost(String token, String title) {
    var e = new com.vocalverse.community.PostEntity();
    e.setAuthorId(appJwt.parseUserId(token));
    e.setKind("article");
    e.setDomain("news");
    e.setTitle(title);
    e.setBody("body");
    e.setStatus("visible");
    var now = java.time.Instant.now();
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return posts.saveAndFlush(e).getId();
  }

  /**
   * 两个线程同时 decide 同一单 → 恰好一个成功、一个 46010。
   *
   * <p>用 {@link ModerationService} 直接调用（而不是 MockMvc）：MockMvc 的请求处理与 {@code SecurityContextHolder}
   * 都是线程绑定的，跨线程走 HTTP 会引入与并发无关的噪音； 服务层调用同样走 {@code @Transactional} + 条件 UPDATE，是本测试要验证的那条路径。
   */
  @Test
  void two_concurrent_decisions_yield_exactly_one_success_and_one_46010() throws Exception {
    String authorToken = tokenFor(uniqueName("cca"));
    String adminName = uniqueName("csa");
    seedAdmin(adminName, superRoleCode());
    long postId = createPost(authorToken, "CONCURRENT_MARKER");

    // 建单（单线程，避免把建单竞态混进来）
    var caseId =
        moderationService
            .create(
                null,
                new ModerationService.CreateRequest(
                    "post", postId, "manual", "spam", (short) 2, null))
            .getId();

    var principal =
        new com.vocalverse.console.auth.ConsolePrincipal(
            adminUsers.findByUsernameIgnoreCase(adminName).orElseThrow().getId(),
            adminName,
            superRoleCode(),
            java.util.Set.of(com.vocalverse.console.rbac.PermissionCatalog.MODERATION_DECIDE),
            null);

    int threads = 2;
    CyclicBarrier barrier = new CyclicBarrier(threads);
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    AtomicInteger ok = new AtomicInteger();
    AtomicInteger conflict = new AtomicInteger();
    AtomicInteger other = new AtomicInteger();
    List<Future<Void>> futures = new ArrayList<>();

    try {
      for (int i = 0; i < threads; i++) {
        final String decision = i == 0 ? "approve" : "reject";
        futures.add(
            pool.submit(
                (Callable<Void>)
                    () -> {
                      barrier.await(10, TimeUnit.SECONDS); // 对齐起跑线
                      try {
                        moderationService.decide(principal, caseId, decision, "spam", "concurrent");
                        ok.incrementAndGet();
                      } catch (ConsoleException e) {
                        if (e.code() == ConsoleErrorCodes.CASE_STATE_CONFLICT) {
                          conflict.incrementAndGet();
                        } else {
                          other.incrementAndGet();
                        }
                      } catch (RuntimeException e) {
                        other.incrementAndGet();
                      }
                      return null;
                    }));
      }
      for (Future<Void> f : futures) {
        f.get(30, TimeUnit.SECONDS);
      }
    } finally {
      pool.shutdownNow();
    }

    assertEquals(
        1,
        ok.get(),
        "必须恰好一个成功（实际 ok="
            + ok.get()
            + " conflict="
            + conflict.get()
            + " other="
            + other.get()
            + "）");
    assertEquals(
        1,
        conflict.get(),
        "另一个必须是 46010（实际 conflict=" + conflict.get() + " other=" + other.get() + "）");
    assertEquals(0, other.get(), "不得出现其他异常（那说明不是竞态而是 bug）");

    // 终态确实只推进了一次
    var after = cases.findById(caseId).orElseThrow();
    assertTrue(
        "approved".equals(after.getStatus()) || "rejected".equals(after.getStatus()),
        "终态应是其中一个： " + after.getStatus());
  }

  /** 已终态的单再决定 → 46010（快路径），且目标状态不被改动。 */
  @Test
  void decision_on_terminal_case_returns_46010() throws Exception {
    String authorToken = tokenFor(uniqueName("cta"));
    String adminName = uniqueName("csa");
    seedAdmin(adminName, superRoleCode());
    long postId = createPost(authorToken, "TERMINAL_MARKER");

    var caseId =
        moderationService
            .create(
                null,
                new ModerationService.CreateRequest(
                    "post", postId, "manual", "spam", (short) 2, null))
            .getId();
    var principal =
        new com.vocalverse.console.auth.ConsolePrincipal(
            adminUsers.findByUsernameIgnoreCase(adminName).orElseThrow().getId(),
            adminName,
            superRoleCode(),
            java.util.Set.of(),
            null);

    moderationService.decide(principal, caseId, "approve", "spam", "first");
    String statusAfterFirst = posts.findById(postId).orElseThrow().getStatus();

    ConsoleException ex =
        org.junit.jupiter.api.Assertions.assertThrows(
            ConsoleException.class,
            () -> moderationService.decide(principal, caseId, "delete", "spam", "second"));
    assertEquals(ConsoleErrorCodes.CASE_STATE_CONFLICT, ex.code());
    assertEquals(statusAfterFirst, posts.findById(postId).orElseThrow().getStatus());
  }

  /** media 目标：approve/reject/escalate 可推进审单，hide/delete 被明确拒绝（Java 不是 media 写方）。 */
  @Test
  void media_target_rejects_hide_and_delete_but_allows_case_state_decisions() throws Exception {
    String adminName = uniqueName("csa");
    seedAdmin(adminName, superRoleCode());
    var principal =
        new com.vocalverse.console.auth.ConsolePrincipal(
            adminUsers.findByUsernameIgnoreCase(adminName).orElseThrow().getId(),
            adminName,
            superRoleCode(),
            java.util.Set.of(),
            null);

    // 直接建一条 media 单（不校验目标存在性：Java 读不到 media_assets，走服务层建单会 46009）
    var entity = new ModerationCaseEntity();
    entity.setTargetType(ModerationCaseEntity.TARGET_MEDIA);
    entity.setTargetId(424242L);
    entity.setSource(ModerationCaseEntity.SOURCE_MANUAL);
    entity.setReasonCode("porn");
    entity.setPriority((short) 1);
    entity.setStatus(ModerationCaseEntity.STATUS_PENDING);
    entity.setCreatedAt(java.time.Instant.now());
    entity.setUpdatedAt(java.time.Instant.now());
    entity = cases.saveAndFlush(entity);

    // hide 必须被拒，且**不得**静默成功
    final long hideCaseId = entity.getId();
    ConsoleException hideEx =
        org.junit.jupiter.api.Assertions.assertThrows(
            ConsoleException.class,
            () -> moderationService.decide(principal, hideCaseId, "hide", "porn", "try hide"));
    assertEquals(ConsoleErrorCodes.INVALID_PARAM, hideEx.code(), hideEx.getMessage());
    assertTrue(
        hideEx.getMessage().contains("媒体") || hideEx.getMessage().contains("media"),
        "错误消息应指向 Python 的媒体端点：" + hideEx.getMessage());
    assertEquals(
        ModerationCaseEntity.STATUS_PENDING,
        cases.findById(hideCaseId).orElseThrow().getStatus(),
        "被拒后审单必须保持 pending（事务回滚）");

    // escalate 允许（只推进审单状态）
    var escalated = moderationService.decide(principal, hideCaseId, "escalate", "porn", "escalate");
    assertEquals(ModerationCaseEntity.STATUS_ESCALATED, escalated.getStatus());

    // escalate 后仍可决定（保持队列中；这正是不能用 status='pending' 写死条件的原因）
    var approved = moderationService.decide(principal, hideCaseId, "approve", "porn", "ok");
    assertEquals(ModerationCaseEntity.STATUS_APPROVED, approved.getStatus());
    assertNotNull(approved.getDecidedAt());
  }
}
