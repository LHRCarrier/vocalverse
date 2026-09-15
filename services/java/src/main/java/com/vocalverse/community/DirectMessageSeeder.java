package com.vocalverse.community;

import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserRepository;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * 私信演示种子（docs/49 §0：演示账号之间预置几段对话，避免新登录用户私信列表为空）。
 *
 * <p>幂等：**以「该会话对是否已有任意消息」为判据**——存在即整段跳过（不追加、不改写）， 因此重复启动、手工删单条都不会产生漂移；生产由 {@code
 * vocalverse.community.seed=false}（默认）关闭。
 *
 * <p>@Order(3)：在 {@link com.vocalverse.config.DemoSeeder}(1) 与 {@link CommunitySeeder}(2) 之后，
 * 依赖演示账号已存在（缺失则跳过并告警，不阻塞启动）。
 */
@Component
@Order(3)
public class DirectMessageSeeder implements CommandLineRunner {

  private static final Logger logger = LoggerFactory.getLogger(DirectMessageSeeder.class);

  private final UserRepository users;
  private final DirectMessageRepository messages;

  @Value("${vocalverse.community.seed:false}")
  private boolean enabled;

  public DirectMessageSeeder(UserRepository users, DirectMessageRepository messages) {
    this.users = users;
    this.messages = messages;
  }

  /** 一段演示对话：{@code [0]} = 发送方（'a' 或 'b'），{@code [1]} = 正文，{@code [2]} = 距今分钟数。 */
  private record Line(char from, String body, long minutesAgo) {}

  private static final List<Line> ADULT_TEEN =
      List.of(
          new Line('a', "Hi! Saw your shadowing post — how long do you practice each day?", 320),
          new Line('b', "About 10 minutes before breakfast. Short but every day.", 296),
          new Line('a', "Smart. Consistency beats intensity.", 180),
          new Line('b', "Do you want to try a role-play together tomorrow?", 42));

  private static final List<Line> ADULT_SENIOR =
      List.of(
          new Line('b', "Good evening! Your reading notes helped me a lot.", 1400),
          new Line('a', "Glad it helped — which chapter are you on?", 1380),
          new Line('b', "Chapter three. The vocabulary list at the end is gold.", 45));

  @Override
  public void run(String... args) {
    if (!enabled) {
      return;
    }
    Optional<UserEntity> adult = users.findByUsernameIgnoreCase("demoadult");
    Optional<UserEntity> teen = users.findByUsernameIgnoreCase("demoteen");
    Optional<UserEntity> senior = users.findByUsernameIgnoreCase("demosenior");
    if (adult.isEmpty() || teen.isEmpty() || senior.isEmpty()) {
      logger.warn("私信种子跳过：演示账号缺失（demoadult/demoteen/demosenior）");
      return;
    }
    int created = 0;
    created += seedConversation(adult.get().getId(), teen.get().getId(), ADULT_TEEN);
    created += seedConversation(adult.get().getId(), senior.get().getId(), ADULT_SENIOR);
    if (created > 0) {
      logger.info("私信演示种子就绪：{} 条消息（demoadult ↔ demoteen/demosenior）", created);
    }
  }

  /** 播种一段对话；该对已有任意消息则跳过（幂等）。返回新建条数。 */
  private int seedConversation(Long aId, Long bId, List<Line> lines) {
    boolean exists =
        !messages
            .page(aId, bId, Long.MAX_VALUE, org.springframework.data.domain.PageRequest.of(0, 1))
            .isEmpty();
    if (exists) {
      return 0;
    }
    Instant now = Instant.now();
    for (Line line : lines) {
      DirectMessageEntity m = new DirectMessageEntity();
      m.setSenderId(line.from() == 'a' ? aId : bId);
      m.setRecipientId(line.from() == 'a' ? bId : aId);
      m.setBody(line.body());
      m.setStatus(DirectMessageEntity.STATUS_VISIBLE);
      m.setCreatedAt(now.minus(line.minutesAgo(), ChronoUnit.MINUTES));
      messages.save(m);
    }
    return lines.size();
  }
}
