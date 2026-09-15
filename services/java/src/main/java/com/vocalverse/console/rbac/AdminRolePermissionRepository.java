package com.vocalverse.console.rbac;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 角色↔权限仓库（docs/50 §5.3.4）。授权为「整体替换」语义（PUT /roles/{id}/permissions）。 */
public interface AdminRolePermissionRepository
    extends JpaRepository<AdminRolePermissionEntity, AdminRolePermissionEntity.Key> {

  @Query("select rp.permissionId from AdminRolePermissionEntity rp where rp.roleId = :roleId")
  List<Long> findPermissionIdsByRoleId(@Param("roleId") Long roleId);

  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query("delete from AdminRolePermissionEntity rp where rp.roleId = :roleId")
  int deleteByRoleId(@Param("roleId") Long roleId);

  long countByPermissionId(Long permissionId);
}
