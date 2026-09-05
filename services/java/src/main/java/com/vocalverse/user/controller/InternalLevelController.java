package com.vocalverse.user.controller;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 内部委托接口（docs/18 §3-J1）：Python 入学测试完成后回写 user_profiles.cefr_level。 网关剥离 /manage 前缀后命中，本服务路径不带
 * /manage（与 /auth 同语义）。
 *
 * <p>契约（docs/21 §5 / local/34 D-2）：POST /internal/level 请求体 {userId, level, source?,
 * levelAt?}。字段必须为 {@code userId}（camelCase，Jackson 默认）——这是 C2/P0-6 曾致 「定档回写 100% 断」的根因（Python 曾发
 * user_id）。
 *
 * <p>幂等 PUT（C9）：仅当 {@code levelAt} 不早于现值时才落库（较新数据生效），防止旧数据/乱序 回调覆盖新档位；source 缺省
 * "placement"（管理端人工改档走 /admin profile PATCH source=manual）。
 */
@RestController
@RequestMapping("/internal")
public class InternalLevelController {

  public record LevelRequest(
      @NotNull Long userId, @NotNull String level, String source, Instant levelAt) {}

  private final UserProfileRepository profiles;

  public InternalLevelController(UserProfileRepository profiles) {
    this.profiles = profiles;
  }

  @PostMapping("/level")
  public Envelope<Long> setLevel(@Valid @RequestBody LevelRequest body) {
    UserProfileEntity profile =
        profiles
            .findByUserId(body.userId())
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.NOT_FOUND, "profile not found"));

    // 幂等 PUT（C9）：旧数据（levelAt 早于现值）忽略，不覆盖。
    if (body.levelAt() != null
        && profile.getCefrLevelAt() != null
        && body.levelAt().isBefore(profile.getCefrLevelAt())) {
      return Envelope.ok(profile.getUserId());
    }

    profile.setCefrLevel(body.level());
    profile.setCefrLevelSource(body.source() == null ? "placement" : body.source());
    profile.setCefrLevelAt(body.levelAt() != null ? body.levelAt() : Instant.now());
    profile.setUpdatedAt(Instant.now());
    profiles.save(profile);
    return Envelope.ok(profile.getUserId());
  }
}
