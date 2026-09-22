package com.vocalverse.console.moderation.screen;

import com.vocalverse.community.ContentPublishedEvent;
import com.vocalverse.console.moderation.ModerationCaseEntity;
import com.vocalverse.console.moderation.ModerationService;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 自动送审（docs/58）：内容发布 → Jev 判定 → 命中阈值建待审单（{@code source='auto'}）。
 *
 * <h2>只建单，不自动处置</h2>
 *
 * <p>违规概率 ≥ 阈值只意味着「值得人工看一眼」，<b>绝不直接写 {@code posts.status='hidden'}</b>。 三条理由：
 *
 * <ol>
 *   <li>第三方实测的准确率只到中档模型水平（docs/58 §1），自动隐藏的误伤成本远高于多一次人工复核；
 *   <li>处置动作会写目标表并产生用户可见后果，本仓口径是「处置必须由审核员决定并留审计」（docs/50 §6.2）；
 *   <li>概率校准只保证群体命中率，单条 0.96 也可能错 —— 阈值门闸的作用是**控制人工队列的量**，不是替代判断。
 * </ol>
 *
 * <h2>为什么是 REQUIRES_NEW</h2>
 *
 * <p>本方法由 {@code AFTER_COMMIT} 监听器触发。Spring 在 {@code afterCommit} 回调执行时**原事务的资源仍 绑定在线程上**（{@code
 * cleanupAfterCompletion} 尚未执行），此时以默认 REQUIRED 传播开启的「新事务」 会加入一个已提交的事务，写入在收尾时被丢弃。REQUIRES_NEW
 * 显式挂起旧资源、开真正的新事务。
 */
@Service
public class ModerationAutoScreen {

  private static final Logger log = LoggerFactory.getLogger(ModerationAutoScreen.class);

  private final JevDecisionClient jev;
  private final ModerationService moderation;
  private final boolean enabled;
  private final double threshold;

  public ModerationAutoScreen(
      JevDecisionClient jev,
      ModerationService moderation,
      @Value("${vocalverse.moderation.auto-screen.enabled:false}") boolean enabled,
      @Value("${vocalverse.moderation.auto-screen.threshold:0.7}") double threshold) {
    this.jev = jev;
    this.moderation = moderation;
    this.enabled = enabled;
    this.threshold = threshold;
  }

  /** 是否启用（未配密钥时上游客户端也会空返回，这里只做最早的一次短路）。 */
  public boolean enabled() {
    return enabled;
  }

  /**
   * 送审一条内容。
   *
   * @return 建单/复用的审核单 id；未命中阈值或判定不可用 → empty
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public Optional<Long> screen(ContentPublishedEvent event) {
    if (!enabled) {
      return Optional.empty();
    }
    if (!ContentPublishedEvent.TARGET_POST.equals(event.targetType())
        && !ContentPublishedEvent.TARGET_COMMENT.equals(event.targetType())) {
      return Optional.empty(); // media / direct_message 不在本链路（docs/50 §5.4 写方矩阵）
    }
    Optional<JevVerdict> maybe = jev.screen(toRequest(event));
    if (maybe.isEmpty()) {
      return Optional.empty();
    }
    JevVerdict verdict = maybe.get();
    if (verdict.violation() < threshold) {
      log.debug(
          "自动送审未命中：ref={} p={} < {} model={}",
          event.targetType() + "#" + event.targetId(),
          round(verdict.violation()),
          threshold,
          verdict.model());
      return Optional.empty();
    }
    String reasonCode =
        ModerationService.REASON_CODES.contains(verdict.category()) ? verdict.category() : "other";
    short priority = priorityOf(verdict.severity());
    ModerationCaseEntity created =
        moderation.createAuto(
            event.targetType(), event.targetId(), reasonCode, priority, evidence(verdict));
    log.info(
        "自动送审命中：ref={} caseId={} p={} clause={} category={} severity={} priority={} model={}",
        event.targetType() + "#" + event.targetId(),
        created.getId(),
        round(verdict.violation()),
        verdict.clause(),
        reasonCode,
        round(verdict.severity()),
        priority,
        verdict.model());
    return Optional.of(created.getId());
  }

  private JevScreenRequest toRequest(ContentPublishedEvent event) {
    return new JevScreenRequest(
        event.targetType(),
        event.targetId(),
        event.kind(),
        event.title(),
        event.body(),
        event.domain());
  }

  /** 严重度 → 优先级（docs/58 §3.3）：≥2.5 高、≥1.5 中、其余低。 */
  static short priorityOf(double severity) {
    if (severity >= 2.5) {
      return 1;
    }
    if (severity >= 1.5) {
      return 2;
    }
    return 3;
  }

  /** 写进 {@code moderation_cases.snapshot.ai} 的证据（可复核、可对账，不含正文）。 */
  private static Map<String, Object> evidence(JevVerdict verdict) {
    Map<String, Object> ai = new LinkedHashMap<>();
    ai.put("model", verdict.model());
    ai.put("violation", round(verdict.violation()));
    // 条款号是判据的对外锚点（docs/59）：审核员据此对照《社区规范》原文
    ai.put("clause", verdict.clause());
    ai.put("category", verdict.category());
    ai.put("clauseConfidence", round(verdict.clauseConfidence()));
    ai.put("severity", round(verdict.severity()));
    ai.put("severityConfidence", round(verdict.severityConfidence()));
    ai.put("latencyMs", verdict.latencyMs());
    ai.put("inputTokens", verdict.inputTokens());
    return ai;
  }

  /** 保留三位小数：快照是给人看的证据，不需要 double 的完整尾巴。 */
  private static double round(double value) {
    return Math.round(value * 1000.0) / 1000.0;
  }
}
