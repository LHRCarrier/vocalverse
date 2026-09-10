package com.vocalverse.console.rbac;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;

/**
 * 角色↔权限关联（docs/50 §5.3.4；Java 写方）。
 *
 * <p>复合主键 {@code (role_id, permission_id)}，无代理 id —— 表级 PK 名 {@code pk_admin_role_permissions}。 用
 * {@code @IdClass} 而非 {@code @EmbeddedId}：列本身就是两个外键 id，包装类只增加映射噪音。
 */
@Entity
@Table(name = "admin_role_permissions")
@IdClass(AdminRolePermissionEntity.Key.class)
public class AdminRolePermissionEntity {

  @Id
  @Column(name = "role_id", nullable = false)
  private Long roleId;

  @Id
  @Column(name = "permission_id", nullable = false)
  private Long permissionId;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public AdminRolePermissionEntity() {}

  public AdminRolePermissionEntity(Long roleId, Long permissionId, Instant createdAt) {
    this.roleId = roleId;
    this.permissionId = permissionId;
    this.createdAt = createdAt;
  }

  public Long getRoleId() {
    return roleId;
  }

  public void setRoleId(Long roleId) {
    this.roleId = roleId;
  }

  public Long getPermissionId() {
    return permissionId;
  }

  public void setPermissionId(Long permissionId) {
    this.permissionId = permissionId;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }

  /** 复合主键（必须 Serializable + equals/hashCode，JPA 规范要求）。 */
  public static class Key implements Serializable {

    private Long roleId;
    private Long permissionId;

    public Key() {}

    public Key(Long roleId, Long permissionId) {
      this.roleId = roleId;
      this.permissionId = permissionId;
    }

    @Override
    public boolean equals(Object o) {
      if (this == o) {
        return true;
      }
      if (!(o instanceof Key k)) {
        return false;
      }
      return Objects.equals(roleId, k.roleId) && Objects.equals(permissionId, k.permissionId);
    }

    @Override
    public int hashCode() {
      return Objects.hash(roleId, permissionId);
    }
  }
}
