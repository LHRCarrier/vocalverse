package com.vocalverse.user;

import com.vocalverse.common.dto.Envelope;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 内部委托接口（docs/18 §3-J1）：Python 入学测试完成后回写 user_profiles.cefr_level。 */
@RestController
@RequestMapping("/manage/internal")
public class InternalLevelController {

  public record LevelRequest(@NotNull Long userId, @NotNull String level) {}

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
                () ->
                    new org.springframework.web.server.ResponseStatusException(
                        org.springframework.http.HttpStatus.NOT_FOUND, "profile not found"));
    profile.setCefrLevel(body.level());
    profile.setCefrLevelSource("placement");
    profile.setUpdatedAt(Instant.now());
    profiles.save(profile);
    return Envelope.ok(profile.getUserId());
  }
}
