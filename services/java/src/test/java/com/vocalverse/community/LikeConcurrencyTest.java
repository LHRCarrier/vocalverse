package com.vocalverse.community;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;

/**
 * J-01 点赞并发幂等回归（真实事务 · 多线程直调 service）。
 *
 * <p>与 {@link CommunityApiTest} 的类级 @Transactional 不同：本类**不**挂测试事务——MockMvc 请求与 service
 * 调用各自开独立事务，多线程并发 like/unlike 才可能落入「先查后插」的 check-then-act 竞态窗口：修复前并发双击 → 第二个 INSERT 撞唯一键 → 未捕获
 * DataIntegrityViolationException → 500；并发双击取消 → 双减 → like_count 与事实行漂移（修复前本测试即红）。
 *
 * <p>线程由 {@code CountDownLatch} 栅栏对齐放行（全部先查空 → 同时插入，最大化窗口命中率）， 断言幂等返回 + 计数与事实行一致（改前失败/改后通过的双向证据）。
 */
class LikeConcurrencyTest extends AbstractAdminApiTest {

  private static final int CODE_OK = 0;

  @Autowired private CommunityService service;
  @Autowired private PostRepository posts;
  @Autowired private PostLikeRepository likes;

  private JsonNode json(org.springframework.test.web.servlet.MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  private long createPost(String token, String domain) throws Exception {
    org.springframework.test.web.servlet.MvcResult r =
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

  private String bearer(String token) {
    return "Bearer " + token;
  }

  /** 并发 like 多次：全部幂等返回（无异常 = 无 500 根因），like_count 只计 1、事实行唯一。 */
  @Test
  void concurrentLikeIdempotent_no500_countOnce() throws Exception {
    String a = registerUser("j01_like_a");
    String b = registerUser("j01_like_b");
    long postId = createPost(a, "news");
    long userId = users.findByUsernameIgnoreCase("j01_like_b").orElseThrow().getId();

    int n = 6;
    ExecutorService pool = Executors.newFixedThreadPool(n);
    try {
      CountDownLatch ready = new CountDownLatch(n);
      CountDownLatch go = new CountDownLatch(1);
      List<Callable<Object>> tasks = new ArrayList<>();
      for (int i = 0; i < n; i++) {
        tasks.add(
            () -> {
              ready.countDown();
              go.await();
              // 修复前：并发线程在唯一键上抛 DataIntegrityViolationException → Future.get 抛
              // ExecutionException（即真机 500 的服务端根因）；修复后全部幂等返回 like=true。
              return service.like(userId, postId, true);
            });
      }
      List<Future<Object>> futures = new ArrayList<>();
      for (Callable<Object> t : tasks) {
        futures.add(pool.submit(t));
      }
      assertTrue(ready.await(10, TimeUnit.SECONDS), "线程未全部就绪");
      go.countDown();
      for (Future<Object> f : futures) {
        assertNotNull(f.get(10, TimeUnit.SECONDS));
      }
    } finally {
      pool.shutdownNow();
    }

    PostEntity p = posts.findById(postId).orElseThrow();
    assertEquals(1, p.getLikeCount(), "并发双击只计 1 次");
    assertTrue(likes.findByPostIdAndLikerId(postId, userId).isPresent());
    assertEquals(1, likes.findByLikerIdAndPostIdIn(userId, List.of(postId)).size(), "事实行唯一");
  }

  /** 并发 unlike 多次：仅减一次 ↓ like_count 与事实行行数一致（防漂移）。 */
  @Test
  void concurrentUnlike_decrementsOnce_noDrift() throws Exception {
    String a = registerUser("j01_un_a");
    String b = registerUser("j01_un_b");
    String c = registerUser("j01_un_c");
    long postId = createPost(a, "news");
    long bId = users.findByUsernameIgnoreCase("j01_un_b").orElseThrow().getId();
    long cId = users.findByUsernameIgnoreCase("j01_un_c").orElseThrow().getId();
    // B、C 各点赞一次 → like_count=2
    service.like(bId, postId, true);
    service.like(cId, postId, true);
    assertEquals(2, posts.findById(postId).orElseThrow().getLikeCount());

    int n = 6;
    ExecutorService pool = Executors.newFixedThreadPool(n);
    try {
      CountDownLatch ready = new CountDownLatch(n);
      CountDownLatch go = new CountDownLatch(1);
      List<Callable<Object>> tasks = new ArrayList<>();
      for (int i = 0; i < n; i++) {
        tasks.add(
            () -> {
              ready.countDown();
              go.await();
              return service.like(bId, postId, false);
            });
      }
      List<Future<Object>> futures = new ArrayList<>();
      for (Callable<Object> t : tasks) {
        futures.add(pool.submit(t));
      }
      assertTrue(ready.await(10, TimeUnit.SECONDS), "线程未全部就绪");
      go.countDown();
      for (Future<Object> f : futures) {
        assertNotNull(f.get(10, TimeUnit.SECONDS));
      }
    } finally {
      pool.shutdownNow();
    }

    PostEntity p = posts.findById(postId).orElseThrow();
    // 修复前：6 次并发双双「删除+递减」→ like_count=GREATEST(2-6,0)=0，事实行剩 1 行（C）→ 漂移 1；
    // 修复后：仅实际删除行的那一次递减 → 2-1=1，与事实行数一致。
    assertEquals(1, p.getLikeCount(), "并发取消只减一次");
    assertEquals(1, likes.findByLikerIdAndPostIdIn(cId, List.of(postId)).size(), "计数与事实行一致（无漂移）");
    assertFalse(likes.findByPostIdAndLikerId(postId, bId).isPresent(), "B 的行已删除");
    assertTrue(likes.findByPostIdAndLikerId(postId, cId).isPresent(), "C 的行保留");
  }
}
