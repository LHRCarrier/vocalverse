package com.vocalverse.console.rbac;

import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * RBAC 解析与守卫（docs/50 §4）。
 *
 * <p>三条不变量：
 *
 * <ol>
 *   <li><b>{@code *} 通配展开</b>：{@code super} 角色在 {@code admin_role_permissions} 里只落一行通配符， {@link
 *       #expandRoleCodes} 把它展开成 {@link PermissionCatalog} 的当前全量码 —— 新增权限码时 super 自动获得， 不需要改
 *       seed（否则每次加码都要回填历史角色，迟早漏）；
 *   <li><b>角色变更即时生效</b>：改角色权限时 bump 该角色全部成员的 {@code token_epoch} 并吊销其会话 （docs/50 §4.1 补偿项②）；本服务提供
 *       {@link #invalidateRoleMembers}，由调用方**在同一事务内**执行；
 *   <li><b>内置角色守卫</b>：{@code builtin=true} 不可删除、{@code code} 不可改（删掉 super 会让权限控制台自锁）； 仍有成员的角色删除 →
 *       46006（docs/50 §10.2 DELETE /roles/{id} 注释）。
 * </ol>
 *
 * <p>权限码缓存：{@code roleId → codes} 是**读多写极少**的数据（只有角色编辑会写），但权限变更必须即时生效 ——所以缓存只在变更路径显式失效（{@link
 * #invalidate(boolean)}），不设 TTL。这是「快且正确」而非 「快但可能过期」，与 token_epoch 的即时性口径一致。
 */
@Service
public class RbacService {

  /** 角色权限码全集；key=roleId。改角色/权限后由本服务清空。 */
  private final Map<Long, Set<String>> roleCodesCache = new ConcurrentHashMap<>();

  /** code → permissionId 映射（seed 后填充；避免每次授权都查库）。 */
  private final Map<String, Long> permissionIdByCode = new ConcurrentHashMap<>();

  private final AdminUserRepository adminUsers;
  private final AdminRoleRepository roles;
  private final AdminPermissionRepository permissions;
  private final AdminRolePermissionRepository rolePermissions;
  private final AdminSessionRepository sessions;

  public RbacService(
      AdminUserRepository adminUsers,
      AdminRoleRepository roles,
      AdminPermissionRepository permissions,
      AdminRolePermissionRepository rolePermissions,
      AdminSessionRepository sessions) {
    this.adminUsers = adminUsers;
    this.roles = roles;
    this.permissions = permissions;
    this.rolePermissions = rolePermissions;
    this.sessions = sessions;
  }

  // ------------------------------------------------------------------ 权限解析

  /**
   * 角色的权限码（含 {@code *} 展开）。
   *
   * <p>展开规则：若角色持有 {@code *}，返回目录全量码；否则返回目录里**存在**的授权码（表里的码若已从 {@link PermissionCatalog} 移除，会被静默忽略
   * —— 目录是唯一真源）。
   */
  @Transactional(readOnly = true)
  public Set<String> roleCodes(Long roleId) {
    if (roleId == null) {
      return Set.of();
    }
    Set<String> cached = roleCodesCache.get(roleId);
    if (cached != null) {
      return cached;
    }
    Set<String> computed = expandRoleCodes(rolePermissions.findPermissionIdsByRoleId(roleId));
    roleCodesCache.put(roleId, computed);
    return computed;
  }

  /** 把 {@code admin_role_permissions} 的 permissionId 集合展开为权限码（含 {@code *} 通配）。 */
  private Set<String> expandRoleCodes(List<Long> permissionIds) {
    if (permissionIds == null || permissionIds.isEmpty()) {
      return Set.of();
    }
    Map<Long, String> codeById = new LinkedHashMap<>();
    for (AdminPermissionEntity p : permissions.findAll()) {
      codeById.put(p.getId(), p.getCode());
    }
    Set<String> raw = new LinkedHashSet<>();
    for (Long pid : permissionIds) {
      String code = codeById.get(pid);
      if (code != null) {
        raw.add(code);
      }
    }
    if (raw.contains(PermissionCatalog.WILDCARD)) {
      return PermissionCatalog.allCodes();
    }
    // 目录为准：库里残留的、已从常量目录下线的码不参与授权
    Set<String> known = PermissionCatalog.allCodes();
    raw.retainAll(known);
    return Set.copyOf(raw);
  }

  /** 账号的有效权限码（经 roleId → 角色码）。 */
  @Transactional(readOnly = true)
  public Set<String> adminCodes(Long adminUserId) {
    return adminUsers.findById(adminUserId).map(u -> roleCodes(u.getRoleId())).orElseGet(Set::of);
  }

  /** 账号是否持有该权限码（{@code *} 已在 roleCodes 展开，此处不再特判）。 */
  @Transactional(readOnly = true)
  public boolean hasPermission(Long adminUserId, String code) {
    return adminCodes(adminUserId).contains(code);
  }

  /** 权限校验（缺码 → 46002，{@code data.required} 回传所需码）。 */
  public void require(Long adminUserId, String code) {
    if (!hasPermission(adminUserId, code)) {
      throw ConsoleException.of(
          ConsoleErrorCodes.PERMISSION_DENIED, "管理端权限不足：需要 " + code, Map.of("required", code));
    }
  }

  /** 角色 code（审计/展示）。 */
  @Transactional(readOnly = true)
  public String roleCode(Long roleId) {
    return roles.findById(roleId).map(AdminRoleEntity::getCode).orElse("");
  }

  public Optional<AdminRoleEntity> roleById(Long roleId) {
    return roles.findById(roleId);
  }

  // ------------------------------------------------------------------ 角色 CRUD 守卫

  /** 码 → permissionId（不存在则 46007：码不在目录内）。 */
  @Transactional(readOnly = true)
  public Long requirePermissionId(String code) {
    Long id = permissionIdByCode.get(code);
    if (id != null) {
      return id;
    }
    return permissions
        .findByCode(code)
        .map(
            p -> {
              permissionIdByCode.put(p.getCode(), p.getId());
              return p.getId();
            })
        .orElseThrow(
            () -> ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "权限码不在目录内：" + code));
  }

  /**
   * 创建角色（码唯一；码必须是小写字母数字与冒号的短标识）。
   *
   * <p>自定义角色 {@code builtin=false}，可删可改 —— 但**不得冒用内置码**（46005 语义上属于「用户名已存在」， 复用到角色码冲突会串味，故这里用 46007
   * 入参非法 + 明确文案）。
   */
  @Transactional
  public AdminRoleEntity createRole(String code, String name, String description, Integer rank) {
    if (code == null || !code.matches("[a-z][a-z0-9_]{1,31}")) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "角色 code 仅允许小写字母/数字/下划线，2~32 位");
    }
    if (name == null || name.isBlank() || name.length() > 64) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "角色名称需 1~64 字");
    }
    if (roles.existsByCode(code)) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "角色 code 已存在：" + code);
    }
    Instant now = Instant.now();
    AdminRoleEntity e = new AdminRoleEntity();
    e.setCode(code);
    e.setName(name);
    e.setDescription(description);
    e.setBuiltin(false);
    e.setRank(rank == null ? (short) 100 : rank.shortValue());
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return roles.save(e);
  }

  /**
   * 更新角色：内置角色的 {@code code} 不可改（其余字段可改）。
   *
   * <p>权限集合非空时**整体替换**授权（PUT 语义，docs/50 §10.2），并 bump 角色成员 token_epoch + 吊销其会话。
   */
  @Transactional
  public AdminRoleEntity updateRole(
      Long roleId,
      String code,
      String name,
      String description,
      Integer rank,
      List<String> permissionCodes) {
    AdminRoleEntity role = requireRole(roleId);
    if (code != null && !code.equals(role.getCode())) {
      if (role.isBuiltin()) {
        throw ConsoleException.of(
            ConsoleErrorCodes.INVALID_PARAM, "内置角色的 code 不可修改：" + role.getCode());
      }
      if (!code.matches("[a-z][a-z0-9_]{1,31}")) {
        throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "角色 code 仅允许小写字母/数字/下划线，2~32 位");
      }
      if (roles.existsByCode(code)) {
        throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "角色 code 已存在：" + code);
      }
      role.setCode(code);
    }
    if (name != null) {
      if (name.isBlank() || name.length() > 64) {
        throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "角色名称需 1~64 字");
      }
      role.setName(name);
    }
    if (description != null) {
      role.setDescription(description);
    }
    if (rank != null) {
      role.setRank(rank.shortValue());
    }
    role.setUpdatedAt(Instant.now());
    AdminRoleEntity saved = roles.save(role);

    if (permissionCodes != null) {
      replacePermissions(roleId, permissionCodes);
      invalidateRoleMembers(roleId, AdminSessionEntity.REASON_ROLE_CHANGED);
    }
    invalidate(true);
    return saved;
  }

  /** 整体替换角色授权（PUT /roles/{id}/permissions）。 */
  @Transactional
  public void replacePermissions(Long roleId, List<String> codes) {
    requireRole(roleId);
    List<Long> ids = new ArrayList<>();
    for (String code : new LinkedHashSet<>(codes)) {
      ids.add(requirePermissionId(code));
    }
    rolePermissions.deleteByRoleId(roleId);
    Instant now = Instant.now();
    for (Long pid : ids) {
      rolePermissions.save(new AdminRolePermissionEntity(roleId, pid, now));
    }
    invalidate(true);
  }

  /**
   * 删除角色（docs/50 §10.2）：内置角色、或仍有成员 → 46006。
   *
   * <p>「仍被引用」= {@code admin_users.role_id} 还有行。这是 FK {@code ON DELETE RESTRICT} 的业务侧前置检查 ——把 DB
   * 约束错误（500/40904）提前成可读的 46006。
   */
  @Transactional
  public void deleteRole(Long roleId) {
    AdminRoleEntity role = requireRole(roleId);
    if (role.isBuiltin()) {
      throw ConsoleException.of(ConsoleErrorCodes.ROLE_NOT_DELETABLE, "内置角色不可删除：" + role.getCode());
    }
    if (adminUsers.countByRoleId(roleId) > 0) {
      throw ConsoleException.of(
          ConsoleErrorCodes.ROLE_NOT_DELETABLE, "角色仍有成员，无法删除：" + role.getCode());
    }
    rolePermissions.deleteByRoleId(roleId);
    roles.delete(role);
    invalidate(true);
  }

  /**
   * 角色变更后让成员令牌即刻失效（docs/50 §4.1 补偿项②）：bump token_epoch + 吊销全部会话。
   *
   * <p>只 bump epoch 不吊销会话是不够的：access token 靠 epo 失效，但 refresh token 若仍有效， 成员可立刻换回一个带**新权限**的 access
   * token —— 而那正是攻击者想要的「降权后仍以旧权续命」反例。
   */
  @Transactional
  public void invalidateRoleMembers(Long roleId, String revokeReason) {
    Instant now = Instant.now();
    for (AdminUserEntity u : adminUsers.findByRoleId(roleId)) {
      adminUsers.bumpTokenEpoch(u.getId());
      sessions.revokeAllForUser(u.getId(), revokeReason, now);
    }
  }

  /** 账号级失效（停用/改密/强制下线）：bump epoch + 吊销会话。 */
  @Transactional
  public void invalidateAdmin(Long adminUserId, String revokeReason) {
    adminUsers.bumpTokenEpoch(adminUserId);
    sessions.revokeAllForUser(adminUserId, revokeReason, Instant.now());
  }

  /** 清缓存（{@code seed} 后或任意权限写操作后调用）。 */
  public void invalidate(boolean alsoPermissionIndex) {
    roleCodesCache.clear();
    if (alsoPermissionIndex) {
      permissionIdByCode.clear();
    }
  }

  /** seed 完成后回填 code→id 索引。 */
  public void indexPermissions(List<AdminPermissionEntity> rows) {
    permissionIdByCode.clear();
    for (AdminPermissionEntity p : rows) {
      permissionIdByCode.put(p.getCode(), p.getId());
    }
  }

  public AdminRoleEntity requireRole(Long roleId) {
    return roles
        .findById(roleId)
        .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "角色不存在"));
  }
}
