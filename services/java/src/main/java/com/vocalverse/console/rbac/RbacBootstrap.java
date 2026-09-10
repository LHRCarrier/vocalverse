package com.vocalverse.console.rbac;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 权限目录 + 内置角色 + 角色授权的**幂等** seed（docs/50 §4.2：「迁移时 upsert 进 admin_permissions， 代码为准、表为索引」）。
 *
 * <p>启动时三步，全部按 code/唯一键 upsert，可重复执行：
 *
 * <ol>
 *   <li>{@code admin_permissions} ← {@link PermissionCatalog}（新增码插入、已有码回写 module/name/sort ——
 *       名字改了要跟着变，否则控制台会显示上一次的名称）；
 *   <li>{@code admin_roles} ← {@link BuiltinRoles}（{@code builtin=true} 的 4 条，按 code upsert）；
 *   <li>{@code admin_role_permissions} ← 内置矩阵，**整体替换**内置角色的授权 （内置角色的权限是代码常量，库里的手工改动会被覆盖 —— 这是刻意的，见
 *       {@link PermissionCatalog} 注释； 要自定义权限请建自定义角色）。
 * </ol>
 *
 * <p>顺序：本 Runner 用 {@code @Order(10)}，跑在 {@link ConsoleAdminBootstrap}（{@code @Order(20)}）之前 ——
 * 先有角色，才能建带 roleId 的第一个管理员账号。
 */
@Component
@Order(10)
public class RbacBootstrap implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(RbacBootstrap.class);

  private final AdminPermissionRepository permissions;
  private final AdminRoleRepository roles;
  private final AdminRolePermissionRepository rolePermissions;
  private final RbacService rbac;

  public RbacBootstrap(
      AdminPermissionRepository permissions,
      AdminRoleRepository roles,
      AdminRolePermissionRepository rolePermissions,
      RbacService rbac) {
    this.permissions = permissions;
    this.roles = roles;
    this.rolePermissions = rolePermissions;
    this.rbac = rbac;
  }

  @Override
  @Transactional
  public void run(ApplicationArguments args) {
    int inserted = seedPermissions();
    int refreshed = seedRoles();
    rbac.indexPermissions(permissions.findAllByOrderByModuleAscSortAscCodeAsc());
    rbac.invalidate(false);
    Set<String> unheld = BuiltinRoles.codesWithoutBuiltinHolder();
    log.info(
        "控制台 RBAC seed 完成：权限码 {} 个（新增 {}）、内置角色 {} 个（新增/回写 {}）",
        PermissionCatalog.size(),
        inserted,
        BuiltinRoles.all().size(),
        refreshed);
    if (!unheld.isEmpty()) {
      log.info("以下权限码无任何内置角色持有（归 Python 服务实现，docs/50 §3.2）：{}", unheld);
    }
  }

  /** upsert 权限目录（含通配符行）；返回新增条数。 */
  private int seedPermissions() {
    Instant now = Instant.now();
    int inserted = 0;
    Map<String, AdminPermissionEntity> existing = new LinkedHashMap<>();
    for (AdminPermissionEntity p : permissions.findAll()) {
      existing.put(p.getCode(), p);
    }
    // allForSeed() 而不是 all()：super 的授权是「一条指向 * 行的记录」，
    // 目录里没有 * 行就解析不出 id → super 会拿到零权限（实测缺陷，见 PermissionCatalog 注释）。
    for (PermissionCatalog.Permission def : PermissionCatalog.allForSeed()) {
      AdminPermissionEntity e = existing.get(def.code());
      if (e == null) {
        e = new AdminPermissionEntity();
        e.setCode(def.code());
        e.setCreatedAt(now);
        inserted++;
      }
      e.setModule(def.module());
      e.setName(def.name());
      e.setDescription(def.description());
      e.setSort((short) def.sort());
      permissions.save(e);
    }
    permissions.flush();
    return inserted;
  }

  /** upsert 内置角色 + 授权；返回新增/回写条数。 */
  private int seedRoles() {
    Instant now = Instant.now();
    int touched = 0;
    List<AdminPermissionEntity> all = permissions.findAllByOrderByModuleAscSortAscCodeAsc();
    Map<String, Long> idByCode = new LinkedHashMap<>();
    for (AdminPermissionEntity p : all) {
      idByCode.put(p.getCode(), p.getId());
    }
    for (BuiltinRoles.Role def : BuiltinRoles.all()) {
      Optional<AdminRoleEntity> found = roles.findByCode(def.code());
      AdminRoleEntity role;
      if (found.isPresent()) {
        role = found.get();
      } else {
        role = new AdminRoleEntity();
        role.setCode(def.code());
        role.setCreatedAt(now);
        touched++;
      }
      // builtin 角色恒为 builtin=true、rank 取常量（防有人改库把 super 变成普通角色）
      role.setName(def.name());
      role.setDescription(def.description());
      role.setBuiltin(true);
      role.setRank((short) def.rank());
      role.setUpdatedAt(now);
      role = roles.save(role);

      // 授权整体替换（幂等）
      Set<Long> targetIds = new LinkedHashSet<>();
      for (String code : def.permissionCodes()) {
        Long pid = idByCode.get(code);
        if (pid == null) {
          log.warn("内置角色 {} 引用了目录中不存在的权限码：{}（已跳过）", def.code(), code);
          continue;
        }
        targetIds.add(pid);
      }
      List<Long> currentIds =
          new ArrayList<>(rolePermissions.findPermissionIdsByRoleId(role.getId()));
      if (!new LinkedHashSet<>(currentIds).equals(targetIds)) {
        rolePermissions.deleteByRoleId(role.getId());
        for (Long pid : targetIds) {
          rolePermissions.save(new AdminRolePermissionEntity(role.getId(), pid, now));
        }
        rolePermissions.flush();
      }
    }
    return touched;
  }
}
