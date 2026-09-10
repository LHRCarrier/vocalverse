package com.vocalverse.console.rbac;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.common.dto.PageView;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.console.audit.AuditService;
import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.auth.CurrentAdmin;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import com.vocalverse.user.UserRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * **App 用户**管理端点（{@code /api/v1/console/users/**}）。
 *
 * <h2>为什么控制台要管 App 用户（这不在 docs/50 §10.2 的原始列表里）</h2>
 *
 * <p>旧管理端的 {@code AdminUserController}（{@code /api/v1/admin/users/**}）随退役整体删除。
 * 逐条核对能力矩阵后发现：它管的是 **App 侧 {@code users} 表**（列表 / 详情 / 停用启用 / 改学习档案），
 * 而控制台的 {@code /admins/**} 管的是**控制台身份 {@code admin_users}**
 * —— 两者是两张表、两套身份（docs/50 §4.1）。删掉 {@code AdminUserController} 就等于
 * **全仓再没有任何接口能停用一个 App 用户**（封禁能力消失）。
 *
 * <p>所以按「退役 = 入口消失 + 权限词汇统一，而不是产品能力消失」的口径，
 * 把它搬到控制台：{@code console:admin:write}（既有的「管理员账号维护」码，
 * 语义就是「管账号」，App 用户停用同属账号治理），每次写落审计。
 *
 * <p><b>与 docs/50 §5.4 的关系</b>：那一行写「{@code users}/{@code user_profiles} … **只读**（不提供用户禁用
 * —— 那是既有 {@code /api/v1/admin/users} 的职责）」。该设计的**前提**是那个既有端点还在；
 * 全仓退役后前提消失，若继续只读则「封禁用户」没有任何实现方。这是需要上报的偏差，
 * 本类的注释即为记录。
 *
 * <p><b>不改 {@code users.role}</b>：role 的 CHECK 与语义属用户域迁移，不在本次范围
 * （docs/50 §4.1 明确管理端角色不复用 {@code users.role}）。本类只读写 {@code status} 与档案字段。
 */
@RestController
@RequestMapping("/api/v1/console/users")
public class ConsoleUserController {

  public record StatusUpdate(
      @Pattern(regexp = "active|disabled") String status, @Size(max = 255) String reason) {}

  public record ProfileUpdate(
      @Size(max = 16) @Pattern(regexp = "teen|adult") String ageGroup,
      @Size(max = 8) String cefrLevel,
      @Size(max = 255) String learningGoal,
      @Size(max = 64) String handle,
      @Size(max = 512) String avatarUrl) {}

  public record UserRow(
      Long id,
      String username,
      String nickname,
      String role,
      String status,
      String email,
      Instant createdAt,
      Instant updatedAt) {}

  public record UserDetail(UserRow user, Map<String, Object> profile) {}

  private final UserRepository users;
  private final UserProfileRepository profiles;
  private final AuditService audit;

  public ConsoleUserController(
      UserRepository users, UserProfileRepository profiles, AuditService audit) {
    this.users = users;
    this.profiles = profiles;
    this.audit = audit;
  }

  // ------------------------------------------------------------------ 读

  @GetMapping
  @RequireConsolePermission(PermissionCatalog.CONSOLE_USER_READ)
  @Transactional(readOnly = true)
  public Envelope<PageView<UserRow>> list(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Size(max = 64) String q,
      @RequestParam(required = false) @Pattern(regexp = "active|disabled") String status) {
    Page<UserEntity> rows =
        users.search(blankToNull(status), blankToNull(q), PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(ConsoleUserController::toRow)));
  }

  @GetMapping("/{id}")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_USER_READ)
  @Transactional(readOnly = true)
  public Envelope<UserDetail> detail(@PathVariable Long id) {
    UserEntity u = requireUser(id);
    Map<String, Object> profile = new LinkedHashMap<>();
    profiles
        .findByUserId(id)
        .ifPresent(
            p -> {
              profile.put("ageGroup", p.getAgeGroup());
              profile.put("cefrLevel", p.getCefrLevel());
              profile.put("cefrLevelSource", p.getCefrLevelSource());
              profile.put("learningGoal", p.getLearningGoal());
              profile.put("handle", p.getHandle());
              profile.put("avatarUrl", p.getAvatarUrl());
              profile.put("interestTags", p.getInterestTags());
              profile.put("voiceRate", p.getVoiceRate());
              profile.put("updatedAt", p.getUpdatedAt());
            });
    return Envelope.ok(new UserDetail(toRow(u), profile));
  }

  // ------------------------------------------------------------------ 写

  /**
   * 停用 / 启用 App 用户（封禁能力的唯一实现）。
   *
   * <p>停用后**下一个请求即 401**：{@code JwtAuthFilter} 每请求回读 {@code users.status}
   * （J-02，2026-09-08），所以无需等 access token 过期。这一点由
   * {@code DisabledUserAccessTest} 端到端验证。
   */
  @PatchMapping("/{id}/status")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_USER_WRITE)
  @Transactional
  public Envelope<UserRow> setStatus(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody StatusUpdate body) {
    if (body.status() == null) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "status 不能为空");
    }
    UserEntity u = requireUser(id);
    String prev = u.getStatus();
    if (!body.status().equals(prev)) {
      u.setStatus(body.status());
      u.setUpdatedAt(Instant.now());
      users.save(u);
      audit.record(
          me,
          "console.user.status",
          "app_user",
          String.valueOf(id),
          "App 用户 " + u.getUsername() + "：" + prev + " → " + body.status(),
          detail(
              "prevStatus", prev,
              "nextStatus", body.status(),
              // reason 在白名单里叫 reasonCode（「为什么封」是合规要留存的信息）
              "reasonCode", body.reason()));
    }
    return Envelope.ok(toRow(requireUser(id)));
  }

  /** 改学习档案（旧管理端能力，docs/50 §5.4 表格里 user_profiles 原本只读，见类注释的偏差说明）。 */
  @PatchMapping("/{id}/profile")
  @RequireConsolePermission(PermissionCatalog.CONSOLE_USER_WRITE)
  @Transactional
  public Envelope<UserDetail> updateProfile(
      @CurrentAdmin ConsolePrincipal me,
      @PathVariable Long id,
      @Valid @RequestBody ProfileUpdate body) {
    UserEntity u = requireUser(id);
    UserProfileEntity p =
        profiles.findByUserId(id).orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "学习档案不存在"));
    Map<String, Object> before = new LinkedHashMap<>();
    before.put("ageGroup", p.getAgeGroup());
    before.put("cefrLevel", p.getCefrLevel());
    before.put("handle", p.getHandle());

    if (body.ageGroup() != null) {
      p.setAgeGroup(body.ageGroup());
    }
    if (body.cefrLevel() != null && !body.cefrLevel().isBlank()) {
      p.setCefrLevel(body.cefrLevel());
      // 人工校正要留来源，否则入学测试的自动结果与人工改动无法区分
      p.setCefrLevelSource("manual");
      p.setCefrLevelAt(Instant.now());
    }
    if (body.learningGoal() != null) {
      p.setLearningGoal(body.learningGoal());
    }
    if (body.handle() != null) {
      p.setHandle(body.handle());
    }
    if (body.avatarUrl() != null) {
      p.setAvatarUrl(body.avatarUrl());
    }
    p.setUpdatedAt(Instant.now());
    profiles.save(p);

    audit.record(
        me,
        "console.user.profile_update",
        "app_user",
        String.valueOf(id),
        "更新用户学习档案：" + u.getUsername(),
        detail("before", String.valueOf(before), "after", String.valueOf(before.keySet())));
    return detail(id);
  }

  // ------------------------------------------------------------------ 内部

  private UserEntity requireUser(Long id) {
    return users
        .findById(id)
        .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "用户不存在"));
  }

  private static UserRow toRow(UserEntity u) {
    return new UserRow(
        u.getId(),
        u.getUsername(),
        u.getNickname(),
        u.getRole(),
        u.getStatus(),
        u.getEmail(),
        u.getCreatedAt(),
        u.getUpdatedAt());
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
