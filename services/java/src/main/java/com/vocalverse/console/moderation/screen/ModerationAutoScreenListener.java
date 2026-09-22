package com.vocalverse.console.moderation.screen;

import com.vocalverse.community.ContentPublishedEvent;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 内容发布 → 异步送审的接线（docs/58 §3.1）。
 *
 * <p>三点设计口径：
 *
 * <ol>
 *   <li><b>AFTER_COMMIT</b>：只对真正落库的内容送审 —— 事务回滚（比如评论数自增失败）不该产生审核单；
 *   <li><b>独立线程</b>：Jev 端到端 70–500ms（跨洋实测更慢），不能让发帖请求等它。队列满了直接丢弃 （丢一次送审只影响这一条内容的自动发现，绝不影响发布）；
 *   <li><b>兜底 catch</b>：监听器里的任何异常都不允许冒泡回请求线程（AFTER_COMMIT 的异常会打进日志并 影响响应收尾），所以这里双层 try。
 * </ol>
 */
@Component
public class ModerationAutoScreenListener {

  private static final Logger log = LoggerFactory.getLogger(ModerationAutoScreenListener.class);

  private final ModerationAutoScreen screen;
  private final Executor executor;

  public ModerationAutoScreenListener(
      ModerationAutoScreen screen, @Qualifier("moderationScreenExecutor") Executor executor) {
    this.screen = screen;
    this.executor = executor;
  }

  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
  public void onContentPublished(ContentPublishedEvent event) {
    if (!screen.enabled()) {
      return;
    }
    try {
      executor.execute(
          () -> {
            try {
              screen.screen(event);
            } catch (Exception e) {
              log.warn(
                  "自动送审执行失败，已忽略：ref={} err={}",
                  event.targetType() + "#" + event.targetId(),
                  e.getMessage());
            }
          });
    } catch (RejectedExecutionException e) {
      log.warn("自动送审队列已满，丢弃本次：ref={}（内容已正常发布）", event.targetType() + "#" + event.targetId());
    }
  }
}
