package com.vocalverse.community;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 私信 SSE 心跳（docs/49 §3.1）：每 25s 向所有长连下发 `:ping` 注释帧。
 *
 * <p>作用有二：① 保活（经 nginx/vite 代理的长连不被 idle 超时切断）；② 让中断的流尽快暴露并清理。
 *
 * <p>开关：`vocalverse.dm.heartbeat-enabled`（测试档默认关闭——固定节奏的心跳会让「事件序列断言」不稳定）。
 */
@Component
@ConditionalOnProperty(
    name = "vocalverse.dm.heartbeat-enabled",
    havingValue = "true",
    matchIfMissing = true)
public class DmHeartbeat {

  private static final Logger log = LoggerFactory.getLogger(DmHeartbeat.class);

  private final DmBroadcaster broadcaster;

  public DmHeartbeat(DmBroadcaster broadcaster) {
    this.broadcaster = broadcaster;
  }

  @Scheduled(fixedDelayString = "${vocalverse.dm.heartbeat-interval-ms:25000}")
  public void ping() {
    int total = broadcaster.totalStreams();
    if (total == 0) {
      return;
    }
    broadcaster.ping();
    log.debug("dm heartbeat sent: streams={}", total);
  }
}
