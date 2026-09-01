package com.vocalverse.auth;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.user.RefreshTokenEntity;
import com.vocalverse.user.RefreshTokenRepository;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import com.vocalverse.user.UserRepository;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 认证最小集（docs/18 §3-J1）：注册 / 登录 / 刷新 / 我的。用户表 Alembic 真源，JPA 纯映射。 路径不带 /manage：网关（nginx/Vite）剥离
 * /manage 前缀后命中（与 PingController /api/v1 同语义， docs/06 §2.1 注记 3；2026-09-01 修复曾误加前缀：网关路径 /auth/login
 * 无匹配 → 403）。
 */
@RestController
@RequestMapping("/auth")
public class AuthController {

  public record RegisterRequest(
      @NotBlank @Size(max = 64) String username,
      @Size(max = 254) String email,
      @NotBlank @Size(min = 8, max = 72) String password,
      @NotBlank @Size(max = 64) String nickname,
      @Size(max = 16) String ageGroup) {}

  public record LoginRequest(@NotBlank String username, @NotBlank String password) {}

  public record RefreshRequest(@NotBlank String refreshToken) {}

  public record TokenResponse(
      String accessToken, String refreshToken, long expiresIn, long userId) {}

  public record MeView(Long userId, String username, String nickname, String level) {}

  private static final long REFRESH_TTL_SECONDS = 30L * 24 * 3600;

  private final UserRepository users;
  private final UserProfileRepository profiles;
  private final RefreshTokenRepository refreshTokens;
  private final PasswordEncoder passwordEncoder;
  private final JwtService jwt;

  public AuthController(
      UserRepository users,
      UserProfileRepository profiles,
      RefreshTokenRepository refreshTokens,
      PasswordEncoder passwordEncoder,
      JwtService jwt) {
    this.users = users;
    this.profiles = profiles;
    this.refreshTokens = refreshTokens;
    this.passwordEncoder = passwordEncoder;
    this.jwt = jwt;
  }

  @PostMapping("/register")
  public Envelope<TokenResponse> register(
      @Valid @RequestBody RegisterRequest body, HttpServletRequest request) {
    if (users.findByUsernameIgnoreCase(body.username()).isPresent()) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "username taken");
    }
    Instant now = Instant.now();
    UserEntity user = new UserEntity();
    user.setUsername(body.username());
    user.setEmail(body.email());
    user.setPasswordHash(passwordEncoder.encode(body.password()));
    user.setNickname(body.nickname());
    user.setRole("user");
    user.setStatus("active");
    user.setCreatedAt(now);
    user.setUpdatedAt(now);
    user = users.save(user);

    UserProfileEntity profile = new UserProfileEntity();
    profile.setUserId(user.getId());
    profile.setAgeGroup(
        body.ageGroup() == null || body.ageGroup().isBlank() ? "adult" : body.ageGroup());
    profile.setCefrLevel("L1");
    profile.setVoiceRate("normal");
    profile.setCefrLevelSource("manual");
    profile.setCreatedAt(now);
    profile.setUpdatedAt(now);
    profiles.save(profile);

    return Envelope.ok(issue(user.getId(), request));
  }

  @PostMapping("/login")
  public Envelope<TokenResponse> login(
      @Valid @RequestBody LoginRequest body, HttpServletRequest request) {
    UserEntity user =
        users
            .findByUsernameIgnoreCase(body.username())
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "bad credentials"));
    if (!"active".equals(user.getStatus())
        || !passwordEncoder.matches(body.password(), user.getPasswordHash())) {
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "bad credentials");
    }
    return Envelope.ok(issue(user.getId(), request));
  }

  @PostMapping("/refresh")
  public Envelope<TokenResponse> refresh(
      @Valid @RequestBody RefreshRequest body, HttpServletRequest request) {
    String hash = sha256(body.refreshToken());
    RefreshTokenEntity token =
        refreshTokens
            .findByTokenHash(hash)
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid refresh"));
    if (token.getRevokedAt() != null || token.getExpiresAt().isBefore(Instant.now())) {
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "refresh expired");
    }
    token.setRevokedAt(Instant.now()); // rotation：旧行吊销
    refreshTokens.save(token);
    return Envelope.ok(issue(token.getUserId(), request));
  }

  @GetMapping("/me")
  public Envelope<MeView> me(
      @org.springframework.web.bind.annotation.RequestAttribute("userId") Long userId) {
    UserEntity user =
        users
            .findById(userId)
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "no such user"));
    String level = profiles.findByUserId(userId).map(UserProfileEntity::getCefrLevel).orElse("L1");
    return Envelope.ok(new MeView(user.getId(), user.getUsername(), user.getNickname(), level));
  }

  private TokenResponse issue(Long userId, HttpServletRequest request) {
    String access = jwt.generateAccessToken(userId);
    String refresh = jwt.generateAccessToken(userId) + "-" + System.currentTimeMillis();
    RefreshTokenEntity entity = new RefreshTokenEntity();
    entity.setUserId(userId);
    entity.setTokenHash(sha256(refresh));
    entity.setExpiresAt(Instant.now().plusSeconds(REFRESH_TTL_SECONDS));
    entity.setUserAgent(request.getHeader("User-Agent"));
    entity.setIp(request.getRemoteAddr());
    refreshTokens.save(entity);
    return new TokenResponse(access, refresh, 3600, userId);
  }

  static String sha256(String raw) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(raw.getBytes(StandardCharsets.UTF_8));
      StringBuilder sb = new StringBuilder(hash.length * 2);
      for (byte b : hash) {
        sb.append(String.format("%02x", b));
      }
      return sb.toString();
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException(e);
    }
  }
}
