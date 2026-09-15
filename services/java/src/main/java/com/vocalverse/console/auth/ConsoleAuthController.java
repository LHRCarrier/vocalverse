package com.vocalverse.console.auth;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.console.audit.ConsoleRequestContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 控制台认证端点（docs/50 §10.2 前 4 行）。
 *
 * <p>路径 {@code /api/v1/console/auth/**}：网关剥离 {@code /manage} 前缀后命中（与既有 {@code AuthController} 的
 * /auth/** 同语义；docs/50 §10.1 网关写 {@code /manage/api/v1/console/**}）。
 *
 * <p>权限码：login/refresh 免鉴权（permitAll，见 {@code ConsoleSecurityConfig}）；logout/me 只需登录 —— {@code
 * /auth/me} 的语义就是「我是谁」，要求额外的权限码会让「无任何权限的空角色」连自己是谁都查不到， 前端也无法据此渲染 403 页。二者都在安全链上被 {@code
 * hasAuthority("ROLE_CONSOLE")} 保护。
 */
@RestController
@RequestMapping("/api/v1/console/auth")
public class ConsoleAuthController {

  public record LoginRequest(
      @NotBlank @Size(max = 32) String username, @NotBlank String password) {}

  public record RefreshRequest(@NotBlank String refreshToken) {}

  public record TokenResponse(
      String accessToken, String refreshToken, String tokenType, long expiresIn) {}

  /** 登录/刷新响应：令牌 + 主体摘要（前端据此直接渲染侧栏，不必再打一次 /me）。 */
  public record SessionView(
      TokenResponse token,
      Long adminUserId,
      String username,
      String displayName,
      String roleCode,
      Set<String> permissions) {}

  /** {@code GET /auth/me}：档案 + 角色 + 已解析权限码（docs/50 §10.2）。 */
  public record MeView(
      Long adminUserId,
      String username,
      String displayName,
      String roleCode,
      String roleName,
      Set<String> permissions,
      Long sessionId) {}

  private final ConsoleAuthService auth;
  private final com.vocalverse.console.rbac.RbacService rbac;
  private final com.vocalverse.console.rbac.AdminUserRepository adminUsers;
  private final com.vocalverse.console.rbac.AdminRoleRepository roles;

  public ConsoleAuthController(
      ConsoleAuthService auth,
      com.vocalverse.console.rbac.RbacService rbac,
      com.vocalverse.console.rbac.AdminUserRepository adminUsers,
      com.vocalverse.console.rbac.AdminRoleRepository roles) {
    this.auth = auth;
    this.rbac = rbac;
    this.adminUsers = adminUsers;
    this.roles = roles;
  }

  @PostMapping("/login")
  public Envelope<SessionView> login(@Valid @RequestBody LoginRequest body) {
    ConsoleAuthService.LoginResult r =
        auth.login(
            body.username(),
            body.password(),
            ConsoleRequestContext.clientIp(),
            ConsoleRequestContext.userAgent());
    return Envelope.ok(toView(r));
  }

  @PostMapping("/refresh")
  public Envelope<SessionView> refresh(@Valid @RequestBody RefreshRequest body) {
    ConsoleAuthService.LoginResult r =
        auth.refresh(
            body.refreshToken(),
            ConsoleRequestContext.clientIp(),
            ConsoleRequestContext.userAgent());
    return Envelope.ok(toView(r));
  }

  @PostMapping("/logout")
  public Envelope<Map<String, Object>> logout(@CurrentAdmin ConsolePrincipal me) {
    auth.logout(me);
    return Envelope.ok(Map.of("revoked", true));
  }

  @GetMapping("/me")
  public Envelope<MeView> me(@CurrentAdmin ConsolePrincipal me) {
    String roleName = roles.findById(adminUserRoleId(me)).map(r -> r.getName()).orElse("");
    return Envelope.ok(
        new MeView(
            me.adminUserId(),
            me.username(),
            adminUsers
                .findById(me.adminUserId())
                .map(u -> u.getDisplayName())
                .orElse(me.username()),
            me.roleCode(),
            roleName,
            // 权限码以**库为准**再解析一次：JWT 快照用于授权判定，me 用于展示，
            // 两者在「改权但令牌未过期」时可能短暂不同，展示应以库为准（否则运维会看到过期的权限列表）
            new LinkedHashSet<>(rbac.adminCodes(me.adminUserId())),
            me.sessionId()));
  }

  private Long adminUserRoleId(ConsolePrincipal me) {
    return adminUsers.findById(me.adminUserId()).map(u -> u.getRoleId()).orElse(-1L);
  }

  private static SessionView toView(ConsoleAuthService.LoginResult r) {
    return new SessionView(
        new TokenResponse(r.accessToken(), r.refreshToken(), "Bearer", r.expiresIn()),
        r.adminUserId(),
        r.username(),
        r.displayName(),
        r.roleCode(),
        new LinkedHashSet<>(r.permissions() == null ? List.of() : r.permissions()));
  }
}
