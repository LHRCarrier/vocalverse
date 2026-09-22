package com.vocalverse.console.moderation.screen;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * TypeSafe System One（Jev）HTTP 客户端（docs/58 §3.2）。
 *
 * <p>一次调用把三个问题**并行**问完（官方口径：问题并行评估，加问题几乎不加延迟）：
 *
 * <ol>
 *   <li>{@code is_violation}（noul）—— 是否违反社区规范；
 *   <li>{@code category}（choice）—— 违规类型，选项键与 {@code ModerationService.REASON_CODES} **逐字同值**，
 *       避免维护一张映射表（映射表是「后端加了原因码、这里忘了加」的漂移源）；
 *   <li>{@code severity}（score）—— 严重度 0..3。
 * </ol>
 *
 * <h2>为什么所有失败都是 Optional.empty</h2>
 *
 * <p>送审是**旁路增强**：Jev 未配置 / 超时 / 429 / 529 / 响应缺字段，一律降级放行（内容照常可见、 不建单），只留一行 WARN。反向做法（送审失败 →
 * 发布失败）会把一个第三方依赖变成社区功能的单点。
 *
 * <h2>内容与隐私</h2>
 *
 * <p>只发判定必需的字段（标题/正文截断到 {@code max-chars}），不发作者 id / 用户 id； 日志只打 {@code post#12}
 * 这类引用与概率，**不打正文**（docs/50 §9.3 日志纪律）。
 */
@Component
public class JevHttpClient implements JevDecisionClient {

  private static final Logger log = LoggerFactory.getLogger(JevHttpClient.class);

  /**
   * 内容准则条款（键 = 《社区规范》条款号，值 = 条款摘要）——**判据唯一真源是 `docs/59`**， 这里保持逐条同义（用户页 `MobileGuidelinesView.vue`
   * 是全文呈现）。
   *
   * <p>{@code none} 不是条款，是「不违规」选项：choice 必须给全选项集，否则内容合规时模型也会被迫选一条。
   */
  private static final Map<String, Object> CLAUSE_RULES =
      orderedMap(
          "R1", "垃圾信息：重复刷屏、灌水、纯符号/乱码、恶意 @",
          "R2", "辱骂骚扰：辱骂、人身攻击、歧视、跟踪骚扰、死亡威胁",
          "R3", "色情低俗：色情、露骨性暗示、擦边引流、未成年人性化表达",
          "R4", "暴力血腥：宣扬暴力、血腥、自残、恐怖主义与极端组织",
          "R5", "涉政敏感：煽动对立与仇恨、政治谣言、国家主权与安全敏感表述",
          "R6", "广告引流：广告、站外引流、拉群推销、刷单返利、博彩赌博",
          "R7", "版权侵权：盗版资源、未授权全文转载、冒用他人作品",
          "R8", "虚假信息：谣言、伪科学、诈骗、伪造成绩或经历",
          "R9", "其他违规：泄露隐私、冒充官方等破坏社区秩序的内容",
          "none", "内容不违规，未命中任何条款");

  /** 条款号 → 控制台原因码（值集 = {@code ModerationService.REASON_CODES}，测试钉死覆盖）。 */
  private static final Map<String, String> CLAUSE_TO_REASON =
      orderedMap(
          "R1", "spam",
          "R2", "abuse",
          "R3", "porn",
          "R4", "violence",
          "R5", "politics",
          "R6", "ad",
          "R7", "copyright",
          "R8", "misinfo",
          "R9", "other");

  private final RestClient http;
  private final boolean enabled;
  private final String model;
  private final int maxChars;

  public JevHttpClient(
      @Value("${vocalverse.moderation.auto-screen.enabled:false}") boolean enabled,
      @Value("${vocalverse.moderation.auto-screen.base-url:https://api.typesafe.ai}")
          String baseUrl,
      @Value("${vocalverse.moderation.auto-screen.api-key:}") String apiKey,
      @Value("${vocalverse.moderation.auto-screen.model:jev-latest}") String model,
      @Value("${vocalverse.moderation.auto-screen.timeout-ms:10000}") int timeoutMs,
      @Value("${vocalverse.moderation.auto-screen.max-chars:4000}") int maxChars) {
    this.enabled = enabled && apiKey != null && !apiKey.isBlank();
    this.model = model;
    this.maxChars = Math.max(200, maxChars);
    SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofMillis(Math.min(3000, Math.max(500, timeoutMs))));
    factory.setReadTimeout(Duration.ofMillis(Math.max(500, timeoutMs)));
    this.http =
        RestClient.builder()
            .baseUrl(baseUrl)
            .requestFactory(factory)
            .defaultHeader("Authorization", "Bearer " + (apiKey == null ? "" : apiKey))
            .build();
    if (enabled && !this.enabled) {
      log.warn("自动送审已开启但未配置 TYPESAFE_API_KEY → 实际不送审（内容不受影响）");
    }
  }

  /** 是否真正可用（开启且配了密钥）；false 时 {@link #screen} 直接空返回，不做网络调用。 */
  public boolean available() {
    return enabled;
  }

  @Override
  public Optional<JevVerdict> screen(JevScreenRequest request) {
    if (!enabled) {
      return Optional.empty();
    }
    long started = System.currentTimeMillis();
    try {
      Map<String, Object> body = new LinkedHashMap<>();
      body.put("model", model);
      body.put("state", stateOf(request));
      body.put("questions", questions());
      JsonNode root =
          http.post()
              .uri("/v1/systemone")
              .contentType(MediaType.APPLICATION_JSON)
              .body(body)
              .retrieve()
              .body(JsonNode.class);
      long latency = System.currentTimeMillis() - started;
      Optional<JevVerdict> verdict = parse(root, latency);
      if (verdict.isEmpty()) {
        log.warn("送审响应缺字段，已跳过：ref={} latencyMs={}", request.ref(), latency);
      }
      return verdict;
    } catch (Exception e) {
      // 超时 / 连接失败 / 4xx / 5xx / 解析失败统一降级；异常信息可能含 URL，但不含正文
      log.warn(
          "送审调用失败，降级放行：ref={} err={} elapsedMs={}",
          request.ref(),
          e.getMessage(),
          System.currentTimeMillis() - started);
      return Optional.empty();
    }
  }

  // ------------------------------------------------------------------ 请求构造

  private Map<String, Object> stateOf(JevScreenRequest request) {
    Map<String, Object> state = new LinkedHashMap<>();
    state.put("contentType", "post".equals(request.targetType()) ? "帖子" : "评论");
    if (request.kind() != null && !request.kind().isBlank()) {
      state.put("kind", request.kind());
    }
    if (request.domain() != null && !request.domain().isBlank()) {
      state.put("domain", request.domain());
    }
    if (request.title() != null && !request.title().isBlank()) {
      state.put("title", truncate(request.title()));
    }
    state.put("body", truncate(request.body() == null ? "" : request.body()));
    // 判据随请求下发（docs/59 §维护说明）：条款文本在 state，问题只引用 `communityRules`
    Map<String, Object> rules = new LinkedHashMap<>();
    for (Map.Entry<String, Object> e : CLAUSE_RULES.entrySet()) {
      if (!"none".equals(e.getKey())) {
        rules.put(e.getKey(), e.getValue());
      }
    }
    state.put("communityRules", rules);
    return state;
  }

  private Map<String, Object> questions() {
    Map<String, Object> noul = new LinkedHashMap<>();
    noul.put("type", "noul");
    noul.put("instructions", "这段用户生成内容是否违反英语学习社区的社区规范？");
    noul.put(
        "criteria",
        orderedMap(
            "true", "存在垃圾信息、辱骂骚扰、色情低俗、暴力血腥、涉政敏感、广告引流、版权侵权、虚假信息等违规",
            "false", "正常的英语学习交流内容，不违反社区规范"));

    Map<String, Object> clause = new LinkedHashMap<>();
    clause.put("type", "choice");
    clause.put("instructions", "这段内容违反了 `communityRules` 的哪一条？逐条对照；若内容不违规，选 none。");
    clause.put("criteria", CLAUSE_RULES);

    Map<String, Object> score = new LinkedHashMap<>();
    score.put("type", "score");
    score.put("instructions", "该内容若违规，严重程度如何？");
    score.put("criteria", List.of("无问题", "轻微", "中等", "严重"));

    Map<String, Object> questions = new LinkedHashMap<>();
    questions.put("is_violation", noul);
    questions.put("clause", clause);
    questions.put("severity", score);
    return questions;
  }

  // ------------------------------------------------------------------ 响应解析

  private Optional<JevVerdict> parse(JsonNode root, long latencyMs) {
    if (root == null) {
      return Optional.empty();
    }
    JsonNode answers = root.path("answers");
    JsonNode violation = answers.path("is_violation").path("noul");
    if (violation.isMissingNode() || !violation.isNumber()) {
      return Optional.empty();
    }
    JsonNode clause = answers.path("clause");
    JsonNode severity = answers.path("severity");
    String modelId = root.path("model").asText(model);
    String clauseId = clause.path("choice").asText("none");
    return Optional.of(
        new JevVerdict(
            modelId,
            violation.asDouble(),
            clauseId,
            CLAUSE_TO_REASON.getOrDefault(clauseId, "other"),
            clause.path("confidence").asDouble(0),
            severity.path("score").asDouble(0),
            severity.path("confidence").asDouble(0),
            latencyMs,
            root.path("usage").path("input_tokens").asInt(0)));
  }

  private String truncate(String text) {
    String trimmed = text.strip();
    return trimmed.length() <= maxChars ? trimmed : trimmed.substring(0, maxChars);
  }

  /** 保持插入顺序的 map（Jackson 序列化时顺序稳定，便于对账）。 */
  @SuppressWarnings("unchecked")
  private static <V> Map<String, V> orderedMap(Object... kv) {
    Map<String, V> map = new LinkedHashMap<>();
    for (int i = 0; i + 1 < kv.length; i += 2) {
      map.put(String.valueOf(kv[i]), (V) kv[i + 1]);
    }
    return map;
  }

  /** 供测试断言：choice 选项键（R1~R9 + none）。 */
  static Map<String, Object> clauseCriteria() {
    return CLAUSE_RULES;
  }

  /** 供测试断言：条款号 → 原因码映射。 */
  static Map<String, String> clauseToReason() {
    return CLAUSE_TO_REASON;
  }
}
