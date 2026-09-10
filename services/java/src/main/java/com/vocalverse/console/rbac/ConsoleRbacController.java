package com.vocalverse.console.rbac;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.common.dto.PageView;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.console.audit.AuditService;
import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.auth.CurrentAdmin;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 权限控制台：管理员账号 / 角色 / 权限目录（docs/50 §10.2）。
 *
 * <p>每个端点声明所需权限码（{@link RequireConsolePermission}），由 {@link ConsolePermissionInterceptor} 服务端强制校验
 * —— 前端裁剪只是体验（docs/50 §4.3 硬规则）。
 *
 * <p>「改账号状态/改角色/重置口令」三条路径都必须**同时** bump {@code token_epoch} 并吊销该账号会话 （{@link
 * RbacService#invalidateAdmin}）：只做其中一件都会留下「已降权但令牌还能用」的窗口。
 */
@RestController
@RequestMapping("/api/v1/console")
public class ConsoleRbacController {

  /** 口令强度：10~64（docs/50 §4.1），且不得与用户名相同。 */
  private static final int PASSWORD_MIN = 10;

  private static final int PASSWORD_MAX = 64;

  public record AdminCreate(
      @NotBlank @Size(max = 32) @Pattern(regexp = "[A-Za-z0-9_.-]{3,32}") String username,
      @NotBlank @Size(max = 64) String displayName,
      @NotBlank String password,
      @NotNull Long roleId) {}

  public record AdminPatch(
      @Size(max = 64) String displayName,
      Long roleId,
      @Pattern(regexp = "active|disabled") String status) {}

  public record PasswordReset(@NotBlank String password) {}

  public record AdminView(
      Long id,
      String username,
      String displayName,
      Long roleId,
      String roleCode,
      String roleName,
      String status,
      Short failedAttempts,
      Instant lockedUntil,
      Integer tokenEpoch,
      Instant lastLoginAt,
      String lastLoginIp,
      Instant createdAt) {}

  public record SessionView(
      Long id,
      Long adminUserId,
      String adminUsername,
      Instant issuedAt,
      Instant expiresAt,
      String ip,
      String userAgent) {}

  public record RoleCreate(
      @NotBlank @Size(max = 32) String code,
      @NotBlank @Size(max = 64) String name,
      @Size(max = 255) String description,
      Integer rank,
      List<String> permissionCodes) {}

  public record RolePatch(
      @Size(max = 32) String code,
      @Size(max = 64) String name,
      @Size(max = 255) String description,
      Integer rank,
      List<String> permissionCodes) {}

  public record RoleView(
      Long id,
      String code,
      String name,
      String description,
      boolean builtin,
      Short rank,
      List<String> permissionCodes,
      long memberCount) {}

  private final AdminUserRepository adminUsers;
  private final AdminRoleRepository roles;
  private final AdminSessionRepository sessions;
  private final RbacService rbac;
  private final PasswordEncoder passwordEncoder;
  private final AuditService audit;

  public ConsoleRbacController(
      AdminUserRepository adminUsers,
      AdminRoleRepository roles,
      AdminSessionRepository sessions,
      RbacService rbac,
      PasswordEncoder passwordEncoder,
      AuditService audit) {
    this.adminUsers = adminUsers;
    this.roles = roles;
    this.sessions = sessions;
    this.rbac = rbac;
    this.passwordEncoder = passwordEncoder;
    this.audit = audit;
  }

  // ------------------------------------------------------------------ 管理员账号

  @GetMapping("/admins")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ADMIN_READ)
  public Envelope<PageView<AdminView>> listAdmins(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Size(max = 64) String q,
      @RequestParam(required = false) Long roleId,
      @RequestParam(required = false) @Pattern(regexp = "active|disabled") String status) {
    Page<AdminUserEntity> rows =
        adminUsers.search(
            blankToNull(q), roleId, blankToNull(status), PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(this::toView)));
  }

  @PostMapping("/admins")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ADMIN_WRITE)
  @Transactional
  public Envelope<AdminView> createAdmin(
      @CurrentAdmin ConsolePrincipal me, @Valid @RequestBody AdminCreate body) {
    String username = body.username().trim();
    if (adminUsers.countByUsernameIgnoreCase(username) > 0) {
      throw ConsoleException.of(ConsoleErrorCodes.USERNAME_TAKEN);
    }
    validatePassword(body.password(), username);
    AdminRoleEntity role =
        roles
            .findById(body.roleId())
            .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "roleId 不存在"));

    Instant now = Instant.now();
    AdminUserEntity e = new AdminUserEntity();
    e.setUsername(username);
    e.setDisplayName(body.displayName().trim());
    e.setPasswordHash(passwordEncoder.encode(body.password()));
    e.setRoleId(role.getId());
    e.setStatus(AdminUserEntity.STATUS_ACTIVE);
    e.setFailedAttempts((short) 0);
    e.setTokenEpoch(0);
    e.setCreatedBy(me.adminUserId());
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    AdminUserEntity saved = adminUsers.save(e);

    audit.record(
        me,
        "console.admin.create",
        "admin_user",
        String.valueOf(saved.getId()),
        "新建管理员账号：" + username,
        detail("roleCode", role.getCode(), "status", saved.getStatus(), "name", username));
    return Envelope.ok(toView(saved));
  }

  /**
   * 改 displayName / roleId / status（docs/50 §10.2 PATCH /admins/{id}）。
   *
   * <p>改角色或停用 → bump token_epoch + 吊销该账号全部会话（docs/50 §4.1 补偿项②）。
   *
   * <h2>反提权（docs/50 §4.2 的隐含前提，文档没写但必须实现）</h2>
   *
   * <p>两条规则，都是「不做就等于权限模型自破」的那种：
   *
   * <ol>
   *   <li><b>不能改自己的 roleId</b>：任何持有 {@code console:admin:write} 的角色都能给自己换成 {@code super} ——
   *       一次请求完成提权，权限矩阵瞬间失效。这条比「只有 super 能建 super」更根本， 因为「改自己」只需要对**自己**那一行的写权限；
   *   <li><b>{@code super} 角色的授予/回收只有 {@code super} 能做</b>（{@link #requireSuperForSuperGrant}）：
   *       否则一个自定义角色只要拿到 {@code console:admin:write}，就能给同伙（或自己的另一个账号）发 super。
   * </ol>
   *
   * <p>两条都返回 46007（入参非法）而不是 46002（缺权限码）：调用方**确实持有**所需的权限码， 被拒的原因是「这个动作本身不允许」，不是「你没这个权限」—— 用 46002
   * 会让前端的「申请权限」引导指错方向。
   */
  @PatchMapping("/admins/{id}")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ADMIN_WRITE)
  @Transactional
  public Envelope<AdminView> patchAdmin(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody AdminPatch body) {
    AdminUserEntity e = requireAdmin(id);
    String prevStatus = e.getStatus();
    Long prevRoleId = e.getRoleId();
    boolean needsInvalidate = false;
    Map<String, Object> detail = new LinkedHashMap<>();

    if (body.displayName() != null && !body.displayName().isBlank()) {
      e.setDisplayName(body.displayName().trim());
    }
    if (body.roleId() != null && !body.roleId().equals(e.getRoleId())) {
      // 反提权①：不能改自己的角色
      if (e.getId().equals(me.adminUserId())) {
        throw ConsoleException.of(
            ConsoleErrorCodes.INVALID_PARAM, "不能修改自己的角色（反提权：改自己一行即可自我提权）。请由其他管理员操作。");
      }
      AdminRoleEntity next =
          roles
              .findById(body.roleId())
              .orElseThrow(
                  () -> ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "roleId 不存在"));
      AdminRoleEntity current = roles.findById(e.getRoleId()).orElse(null);
      requireSuperForSuperGrant(me, current, next);
      e.setRoleId(next.getId());
      detail.put("roleCode", next.getCode());
      needsInvalidate = true;
    }
    if (body.status() != null && !body.status().equals(e.getStatus())) {
      // 不允许把自己停用：会把控制台锁死（无人能再启用）
      if (e.getId().equals(me.adminUserId())
          && AdminUserEntity.STATUS_DISABLED.equals(body.status())) {
        throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "不能停用当前登录的管理员账号");
      }
      e.setStatus(body.status());
      detail.put("status", body.status());
      needsInvalidate = true;
    }
    e.setUpdatedAt(Instant.now());
    adminUsers.save(e);
    if (needsInvalidate) {
      rbac.invalidateAdmin(id, AdminSessionEntity.REASON_ADMIN_REVOKED);
      e = requireAdmin(id); // epoch 已变，回读最新值
    }

    audit.record(
        me,
        "console.admin.update",
        "admin_user",
        String.valueOf(id),
        "更新管理员账号：" + e.getUsername(),
        detail(
            "prevStatus", prevStatus,
            "nextStatus", e.getStatus(),
            "roleId", e.getRoleId(),
            "before", String.valueOf(prevRoleId),
            "after", String.valueOf(e.getRoleId()),
            "fields", detail));
    return Envelope.ok(toView(e));
  }

  /** 重置口令（docs/50 §10.2）：改密后旧令牌与旧会话必须立刻失效。 */
  @PostMapping("/admins/{id}/password")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ADMIN_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> resetPassword(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody PasswordReset body) {
    AdminUserEntity e = requireAdmin(id);
    validatePassword(body.password(), e.getUsername());
    e.setPasswordHash(passwordEncoder.encode(body.password()));
    e.setFailedAttempts((short) 0);
    e.setLockedUntil(null);
    e.setUpdatedAt(Instant.now());
    adminUsers.save(e);
    rbac.invalidateAdmin(id, AdminSessionEntity.REASON_ADMIN_REVOKED);

    // 绝不把口令或哈希写进审计 detail（白名单也会拦，但这里连传都不传）
    audit.record(
        me,
        "console.admin.password_reset",
        "admin_user",
        String.valueOf(id),
        "重置管理员口令：" + e.getUsername(),
        detail("status", e.getStatus()));
    return Envelope.ok(
        Map.ofEntries(
            Map.entry("reset", true),
            Map.entry("adminUserId", id),
            Map.entry("self", e.getId().equals(me.adminUserId()))));
  }

  /** 强制下线（docs/50 §10.2 DELETE /admins/{id}/sessions）：吊销全部会话 + bump epoch。 */
  @DeleteMapping("/admins/{id}/sessions")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ADMIN_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> kickSessions(
      @CurrentAdmin ConsolePrincipal me, @PathVariable Long id) {
    AdminUserEntity e = requireAdmin(id);
    rbac.invalidateAdmin(id, AdminSessionEntity.REASON_ADMIN_REVOKED);
    audit.record(
        me,
        "console.admin.sessions_revoke",
        "admin_user",
        String.valueOf(id),
        "强制下线管理员：" + e.getUsername(),
        detail("status", e.getStatus()));
    return Envelope.ok(Map.of("revoked", true, "adminUserId", id));
  }

  /** 在线会话列表（docs/50 §10.2 GET /admins/sessions）。 */
  @GetMapping("/admins/sessions")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ADMIN_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<SessionView>> listSessions(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize) {
    Page<AdminSessionEntity> rows =
        sessions.findActive(Instant.now(), PageRequest.of(page - 1, pageSize));
    Map<Long, String> names = new LinkedHashMap<>();
    return Envelope.ok(
        PageView.of(
            rows.map(
                s -> {
                  String name =
                      names.computeIfAbsent(
                          s.getAdminUserId(),
                          uid ->
                              adminUsers
                                  .findById(uid)
                                  .map(AdminUserEntity::getUsername)
                                  .orElse(""));
                  return new SessionView(
                      s.getId(),
                      s.getAdminUserId(),
                      name,
                      s.getIssuedAt(),
                      s.getExpiresAt(),
                      s.getIp(),
                      // user_agent 可能很长且含个人化信息：只回传前 120 字符用于辨认设备
                      s.getUserAgent() == null
                          ? null
                          : s.getUserAgent()
                              .substring(0, Math.min(120, s.getUserAgent().length())));
                })));
  }

  // ------------------------------------------------------------------ 角色

  @GetMapping("/roles")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ROLE_READ)
  @Transactional(readOnly = true)
  public Envelope<List<RoleView>> listRoles() {
    List<RoleView> out = new ArrayList<>();
    for (AdminRoleEntity r : roles.findAllByOrderByRankAscIdAsc()) {
      out.add(toView(r));
    }
    return Envelope.ok(out);
  }

  @PostMapping("/roles")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ROLE_WRITE)
  @Transactional
  public Envelope<RoleView> createRole(
      @CurrentAdmin ConsolePrincipal me, @Valid @RequestBody RoleCreate body) {
    AdminRoleEntity r = rbac.createRole(body.code(), body.name(), body.description(), body.rank());
    if (body.permissionCodes() != null) {
      rbac.replacePermissions(r.getId(), body.permissionCodes());
    }
    audit.record(
        me,
        "console.role.create",
        "role",
        String.valueOf(r.getId()),
        "新建角色：" + r.getCode(),
        detail(
            "roleCode",
            r.getCode(),
            "permissionCodes",
            body.permissionCodes() == null ? List.of() : body.permissionCodes()));
    return Envelope.ok(toView(r));
  }

  @PatchMapping("/roles/{id}")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ROLE_WRITE)
  @Transactional
  public Envelope<RoleView> patchRole(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody RolePatch body) {
    AdminRoleEntity before = rbac.requireRole(id);
    AdminRoleEntity r =
        rbac.updateRole(
            id, body.code(), body.name(), body.description(), body.rank(), body.permissionCodes());
    audit.record(
        me,
        "console.role.update",
        "role",
        String.valueOf(id),
        "更新角色：" + r.getCode(),
        detail(
            "roleCode", r.getCode(),
            "before", before.getName(),
            "after", r.getName(),
            "permissionCodes", body.permissionCodes()));
    return Envelope.ok(toView(r));
  }

  @DeleteMapping("/roles/{id}")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ROLE_WRITE)
  @Transactional
  public Envelope<Map<String, Object>> deleteRole(
      @CurrentAdmin ConsolePrincipal me, @PathVariable Long id) {
    AdminRoleEntity r = rbac.requireRole(id);
    String code = r.getCode();
    rbac.deleteRole(id);
    audit.record(
        me,
        "console.role.delete",
        "role",
        String.valueOf(id),
        "删除角色：" + code,
        detail("roleCode", code));
    return Envelope.ok(Map.of("deleted", true, "roleId", id));
  }

  /** 权限目录（docs/50 §10.2 GET /permissions：按 module 分组返回）。 */
  @GetMapping("/permissions")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ROLE_READ)
  public Envelope<List<Map<String, Object>>> listPermissions() {
    List<Map<String, Object>> out = new ArrayList<>();
    PermissionCatalog.byModule()
        .forEach(
            (module, items) -> {
              Map<String, Object> group = new LinkedHashMap<>();
              group.put("module", module);
              List<Map<String, Object>> codes = new ArrayList<>();
              for (PermissionCatalog.Permission p : items) {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("code", p.code());
                m.put("name", p.name());
                m.put("description", p.description());
                m.put("sort", p.sort());
                codes.add(m);
              }
              group.put("permissions", codes);
              out.add(group);
            });
    return Envelope.ok(out);
  }

  /** 整体替换角色授权（docs/50 §10.2 PUT /roles/{id}/permissions）。 */
  @PutMapping("/roles/{id}/permissions")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_ROLE_WRITE)
  @Transactional
  public Envelope<RoleView> putPermissions(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @RequestBody Map<String, List<String>> body) {
    List<String> codes = body == null ? null : body.get("permissionCodes");
    if (codes == null) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "permissionCodes 不能为空");
    }
    AdminRoleEntity before = rbac.requireRole(id);
    rbac.replacePermissions(id, codes);
    rbac.invalidateRoleMembers(id, AdminSessionEntity.REASON_ROLE_CHANGED);
    audit.record(
        me,
        "console.role.permissions_update",
        "role",
        String.valueOf(id),
        "更新角色权限：" + before.getCode(),
        detail("roleCode", before.getCode(), "permissionCodes", codes));
    return Envelope.ok(toView(rbac.requireRole(id)));
  }

  // ------------------------------------------------------------------ 内部

  /**
   * 反提权②：授予或回收 {@code super} 角色只能由 {@code super} 执行。
   *
   * <p>为什么需要：{@code console:admin:write} 是「能改别人账号」的权限，而 {@code super} 是「全权限」。 若持有 {@code
   * console:admin:write} 的非 super 角色能给他人发 super，则一次请求即可绕过整个权限矩阵 —— 这时 {@code console:role:write} 与
   * {@code console:admin:write} 的区分就形同虚设。
   */
  private void requireSuperForSuperGrant(
      ConsolePrincipal me, AdminRoleEntity current, AdminRoleEntity next) {
    if (current != null && next != null && current.getCode().equals(next.getCode())) {
      return;
    }
    boolean touchesSuper =
        (current != null && BuiltinRoles.SUPER.equals(current.getCode()))
            || (next != null && BuiltinRoles.SUPER.equals(next.getCode()));
    if (!touchesSuper) {
      return;
    }
    if (!BuiltinRoles.SUPER.equals(me.roleCode())) {
      throw ConsoleException.of(
          ConsoleErrorCodes.INVALID_PARAM, "只有 super 角色可以授予或回收 super 角色（反提权）");
    }
  }

  private AdminUserEntity requireAdmin(Long id) {
    return adminUsers
        .findById(id)
        .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.ADMIN_NOT_FOUND, "管理员不存在"));
  }

  /**
   * 口令规则（docs/50 §4.1）：长度 10~64、不得与用户名相同。
   *
   * <p>不在这里做「大小写/数字/符号」复杂度校验：那类规则会把口令推向 `Passw0rd!` 式的可预测形态， 而真正的防线是 BCrypt + 锁定 + 限流。长度下限 10
   * 是与设计逐字对齐的部分。
   */
  private void validatePassword(String password, String username) {
    if (password == null || password.length() < PASSWORD_MIN || password.length() > PASSWORD_MAX) {
      throw ConsoleException.of(
          ConsoleErrorCodes.INVALID_PARAM, "口令长度需 " + PASSWORD_MIN + "~" + PASSWORD_MAX + " 位");
    }
    if (username != null && password.equalsIgnoreCase(username)) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "口令不得与用户名相同");
    }
  }

  private AdminView toView(AdminUserEntity e) {
    AdminRoleEntity role = roles.findById(e.getRoleId()).orElse(null);
    return new AdminView(
        e.getId(),
        e.getUsername(),
        e.getDisplayName(),
        e.getRoleId(),
        role == null ? null : role.getCode(),
        role == null ? null : role.getName(),
        e.getStatus(),
        e.getFailedAttempts(),
        e.getLockedUntil(),
        e.getTokenEpoch(),
        e.getLastLoginAt(),
        e.getLastLoginIp(),
        e.getCreatedAt());
  }

  private RoleView toView(AdminRoleEntity r) {
    return new RoleView(
        r.getId(),
        r.getCode(),
        r.getName(),
        r.getDescription(),
        r.isBuiltin(),
        r.getRank(),
        new ArrayList<>(rbac.roleCodes(r.getId())),
        adminUsers.countByRoleId(r.getId()));
  }

  private static String blankToNull(String s) {
    return s == null || s.isBlank() ? null : s;
  }

  private static Map<String, Object> detail(Object... kv) {
    Map<String, Object> m = new LinkedHashMap<>();
    for (int i = 0; i + 1 < kv.length; i += 2) {
      m.put(String.valueOf(kv[i]), kv[i + 1]);
    }
    return m.isEmpty() ? null : m;
  }
}
