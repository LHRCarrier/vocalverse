package com.vocalverse.user.controller;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.common.dto.PageView;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import com.vocalverse.user.UserRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 用户管理（docs/06 §9.6 管理端最小集：列表/查询/禁用启用/档案）。admin 角色由 SecurityConfig /api/v1/admin/** 守门；网关路径
 * /manage/api/v1/admin/**（nginx 剥 /manage 前缀）。 禁物理删除（docs/10 P7）—— 禁用只改 status。读侧 Python 不查
 * users.status（P1-10 遗留，见 docs/21 R-11 关联项）。
 */
@RestController
@RequestMapping("/api/v1/admin/users")
public class AdminUserController {

  /** 列表行（不含档案）。 */
  public record UserRow(
      Long id,
      String username,
      String email,
      String nickname,
      String role,
      String status,
      Instant createdAt) {}

  /** 用户 + 学习档案（1:1）。 */
  public record UserDetail(
      Long id,
      String username,
      String email,
      String nickname,
      String role,
      String status,
      String ageGroup,
      String cefrLevel,
      String learningGoal,
      String interestTags,
      String voiceRate,
      String voiceType,
      Integer preferredDifficulty,
      String avatarUrl,
      String cefrLevelSource,
      Instant cefrLevelAt,
      Instant createdAt,
      Instant updatedAt) {}

  /** 禁用/启用（active|disabled；禁物理删除，docs/10 §4.1）。 */
  public record StatusUpdate(@NotBlank @Pattern(regexp = "active|disabled") String status) {}

  /** 档案修改（可空=不更新；cefrLevel 修改时 source=manual + cefrLevelAt=now（docs/11 Q-B07））。 */
  public record ProfileUpdate(
      @Pattern(regexp = "child|teen|adult|senior") String ageGroup,
      @Pattern(regexp = "L[1-4]") String cefrLevel,
      @Size(max = 255) String learningGoal,
      String interestTags,
      @Pattern(regexp = "slow|normal|fast") String voiceRate,
      @Size(max = 32) String voiceType,
      @Min(1) @Max(4) Integer preferredDifficulty,
      @Size(max = 512) String avatarUrl) {}

  private final UserRepository users;
  private final UserProfileRepository profiles;

  public AdminUserController(UserRepository users, UserProfileRepository profiles) {
    this.users = users;
    this.profiles = profiles;
  }

  @GetMapping
  public Envelope<PageView<UserRow>> list(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "active|disabled") String status,
      @RequestParam(required = false) @Size(max = 64) String search) {
    Pageable pageable = PageRequest.of(page - 1, pageSize);
    Page<UserEntity> rows = users.search(status, search, pageable);
    return Envelope.ok(
        PageView.of(
            rows.map(
                u ->
                    new UserRow(
                        u.getId(),
                        u.getUsername(),
                        u.getEmail(),
                        u.getNickname(),
                        u.getRole(),
                        u.getStatus(),
                        u.getCreatedAt()))));
  }

  @GetMapping("/{id}")
  public Envelope<UserDetail> detail(@PathVariable Long id) {
    UserEntity user = requireUser(id);
    UserProfileEntity profile =
        profiles
            .findByUserId(id)
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.NOT_FOUND, "profile not found"));
    return Envelope.ok(
        new UserDetail(
            user.getId(),
            user.getUsername(),
            user.getEmail(),
            user.getNickname(),
            user.getRole(),
            user.getStatus(),
            profile.getAgeGroup(),
            profile.getCefrLevel(),
            profile.getLearningGoal(),
            profile.getInterestTags(),
            profile.getVoiceRate(),
            profile.getVoiceType(),
            profile.getPreferredDifficulty(),
            profile.getAvatarUrl(),
            profile.getCefrLevelSource(),
            profile.getCefrLevelAt(),
            user.getCreatedAt(),
            user.getUpdatedAt()));
  }

  @PatchMapping("/{id}/status")
  public Envelope<UserRow> updateStatus(
      @PathVariable Long id, @Valid @RequestBody StatusUpdate body) {
    UserEntity user = requireUser(id);
    user.setStatus(body.status());
    user.setUpdatedAt(Instant.now());
    users.save(user);
    return Envelope.ok(toRow(user));
  }

  @PatchMapping("/{id}/profile")
  public Envelope<UserDetail> updateProfile(
      @PathVariable Long id, @Valid @RequestBody ProfileUpdate body) {
    UserEntity user = requireUser(id);
    UserProfileEntity profile =
        profiles
            .findByUserId(id)
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.NOT_FOUND, "profile not found"));
    if (body.ageGroup() != null) {
      profile.setAgeGroup(body.ageGroup());
    }
    if (body.cefrLevel() != null) {
      profile.setCefrLevel(body.cefrLevel());
      profile.setCefrLevelSource("manual"); // 人工改档审计（docs/11 Q-B07）
      profile.setCefrLevelAt(Instant.now());
    }
    if (body.learningGoal() != null) {
      profile.setLearningGoal(body.learningGoal());
    }
    if (body.interestTags() != null) {
      profile.setInterestTags(body.interestTags());
    }
    if (body.voiceRate() != null) {
      profile.setVoiceRate(body.voiceRate());
    }
    if (body.voiceType() != null) {
      profile.setVoiceType(body.voiceType());
    }
    if (body.preferredDifficulty() != null) {
      profile.setPreferredDifficulty(body.preferredDifficulty());
    }
    if (body.avatarUrl() != null) {
      profile.setAvatarUrl(body.avatarUrl());
    }
    profile.setUpdatedAt(Instant.now());
    profiles.save(profile);
    return Envelope.ok(toDetail(user, profile));
  }

  private UserEntity requireUser(Long id) {
    return users
        .findById(id)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "user not found"));
  }

  private static UserRow toRow(UserEntity u) {
    return new UserRow(
        u.getId(),
        u.getUsername(),
        u.getEmail(),
        u.getNickname(),
        u.getRole(),
        u.getStatus(),
        u.getCreatedAt());
  }

  private static UserDetail toDetail(UserEntity user, UserProfileEntity profile) {
    return new UserDetail(
        user.getId(),
        user.getUsername(),
        user.getEmail(),
        user.getNickname(),
        user.getRole(),
        user.getStatus(),
        profile.getAgeGroup(),
        profile.getCefrLevel(),
        profile.getLearningGoal(),
        profile.getInterestTags(),
        profile.getVoiceRate(),
        profile.getVoiceType(),
        profile.getPreferredDifficulty(),
        profile.getAvatarUrl(),
        profile.getCefrLevelSource(),
        profile.getCefrLevelAt(),
        user.getCreatedAt(),
        user.getUpdatedAt());
  }
}
