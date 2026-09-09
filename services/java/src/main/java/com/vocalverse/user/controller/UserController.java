package com.vocalverse.user.controller;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import com.vocalverse.user.UserRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 用户自助资料（社区 S3 · docs/47 §4.2）：网关 /manage/api/v1/users/me，Bearer（anyRequest().authenticated()）。
 *
 * <p>只做**写**（PATCH）：读取沿用既有 {@code GET /auth/me}（本次扩展 avatarUrl），避免两个近重复的 GET 端点 （docs/48 §3-A
 * 裁定）。可改字段：nickname / handle / tint / avatarUrl。
 *
 * <p>handle 大小写不敏感唯一（迁移 0011 建 lower(handle) 唯一索引）：先查后写 + DB 唯一键兜底， 冲突返回
 * 40904（docs/api/error-codes.md）。
 */
@RestController
@RequestMapping("/api/v1/users")
public class UserController {

  public record PatchMeRequest(
      @Size(min = 1, max = 64) String nickname,
      @Size(max = 32) String handle,
      @Size(max = 16) String tint,
      @Size(max = 512) String avatarUrl) {}

  public record MeView(
      Long userId,
      String username,
      String nickname,
      String level,
      String handle,
      String tint,
      String avatarUrl) {}

  private final UserRepository users;
  private final UserProfileRepository profiles;

  public UserController(UserRepository users, UserProfileRepository profiles) {
    this.users = users;
    this.profiles = profiles;
  }

  @PatchMapping("/me")
  @Transactional
  public Envelope<MeView> patchMe(
      @RequestAttribute("userId") Long userId, @Valid @RequestBody PatchMeRequest body) {
    UserEntity user =
        users
            .findById(userId)
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "no such user"));

    if (body.nickname() != null && !body.nickname().isBlank()) {
      user.setNickname(body.nickname().trim());
      user.setUpdatedAt(Instant.now());
      users.save(user);
    }

    UserProfileEntity profile = profiles.findByUserId(userId).orElse(null);
    if (profile != null) {
      boolean dirty = false;
      if (body.handle() != null) {
        String handle = body.handle().trim();
        if (handle.isEmpty()) {
          throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY, "handle 不能为空");
        }
        if (profiles.existsByHandleIgnoreCaseAndUserIdNot(handle, userId)) {
          // GlobalExceptionHandler 把 ResponseStatusException 409 映射为 40904（docs/api/error-codes.md）
          throw new ResponseStatusException(HttpStatus.CONFLICT, "该 @handle 已被占用");
        }
        profile.setHandle(handle);
        dirty = true;
      }
      if (body.tint() != null) {
        profile.setTint(body.tint().trim());
        dirty = true;
      }
      if (body.avatarUrl() != null) {
        String url = body.avatarUrl().trim();
        if (!url.isEmpty() && !url.startsWith("/api/v1/media/")) {
          // 只允许本服务签发的媒体地址（与发帖 media 同口径，docs/47 §4.3）
          throw new ResponseStatusException(
              HttpStatus.UNPROCESSABLE_ENTITY, "avatarUrl 只能引用本服务的媒体地址");
        }
        profile.setAvatarUrl(url.isEmpty() ? null : url);
        dirty = true;
      }
      if (dirty) {
        profile.setUpdatedAt(Instant.now());
        profiles.save(profile);
      }
    }

    String level = profile == null ? "L1" : profile.getCefrLevel();
    return Envelope.ok(
        new MeView(
            user.getId(),
            user.getUsername(),
            user.getNickname(),
            level,
            profile == null ? null : profile.getHandle(),
            profile == null ? null : profile.getTint(),
            profile == null ? null : profile.getAvatarUrl()));
  }
}
