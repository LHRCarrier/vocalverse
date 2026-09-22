package com.vocalverse.console.moderation.screen;

import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/**
 * 送审执行器（docs/58 §3.1）。
 *
 * <p>单线程 + 有界队列：送审是顺序旁路，不需要并发；队列满时**丢弃**而不是让发帖请求代跑 （CallerRunsPolicy 会把 10s 的第三方延迟加到用户请求上，那是本末倒置）。
 *
 * <p>{@code async=false} 时退化为同步执行器，供测试使用（判定链路端到端可断言，不引入等待/轮询）。
 */
@Configuration
public class ModerationAutoScreenConfig {

  private static final Logger log = LoggerFactory.getLogger(ModerationAutoScreenConfig.class);

  @Bean(name = "moderationScreenExecutor")
  public Executor moderationScreenExecutor(
      @Value("${vocalverse.moderation.auto-screen.async:true}") boolean async) {
    if (!async) {
      return new SyncTaskExecutor();
    }
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("mod-screen-");
    executor.setRejectedExecutionHandler(
        (r, e) -> log.warn("自动送审队列已满（capacity={}），丢弃本次送审；内容发布不受影响", e.getQueue().size()));
    executor.initialize();
    return executor;
  }
}
