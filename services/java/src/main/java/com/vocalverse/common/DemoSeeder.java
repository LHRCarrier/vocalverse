package com.vocalverse.common;

import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import com.vocalverse.user.UserRepository;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * 演示账号播种（docs/07 ADR 35：预置 3 画像账号直接登录，演示推荐差异/年龄差异/水平差异）。
 *
 * <p>幂等：按 username 查重后跳过。密码统一 demo123456（仅演示环境启用，生产镜像由 VOICEVERSE_SEED_DEMO=false 关闭）。
 */
@Component
public class DemoSeeder implements CommandLineRunner {

  private static final Logger logger = LoggerFactory.getLogger(DemoSeeder.class);

  private final UserRepository users;
  private final UserProfileRepository profiles;
  private final PasswordEncoder encoder;

  public DemoSeeder(UserRepository users, UserProfileRepository profiles, PasswordEncoder encoder) {
    this.users = users;
    this.profiles = profiles;
    this.encoder = encoder;
  }

  @Override
  public void run(String... args) {
    seed("demoadult", "成年中级", "adult", "L3", "normal");
    seed("demoteen", "青少年初级", "teen", "L1", "normal");
    seed("demosenior", "老年高级", "senior", "L4", "slow");
    logger.info("演示账号就绪：demoadult / demoteen / demosenior（密码 demo123456）");
  }

  private void seed(
      String username, String nickname, String ageGroup, String level, String voiceRate) {
    if (users.findByUsernameIgnoreCase(username).isPresent()) {
      return;
    }
    Instant now = Instant.now();
    UserEntity user = new UserEntity();
    user.setUsername(username);
    user.setPasswordHash(encoder.encode("demo123456"));
    user.setNickname(nickname);
    user.setRole("user");
    user.setStatus("active");
    user.setCreatedAt(now);
    user.setUpdatedAt(now);
    user = users.save(user);

    UserProfileEntity profile = new UserProfileEntity();
    profile.setUserId(user.getId());
    profile.setAgeGroup(ageGroup);
    profile.setCefrLevel(level);
    profile.setVoiceRate(voiceRate);
    profile.setCefrLevelSource("manual");
    profile.setCreatedAt(now);
    profile.setUpdatedAt(now);
    profiles.save(profile);
  }
}
