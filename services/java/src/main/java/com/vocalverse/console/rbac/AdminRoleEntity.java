package com.vocalverse.console.rbac;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 管理端角色（docs/50 §5.3.2；Java 写方，schema 真源 = Alembic 0013，ddl-auto=none）。
 *
 * <p>{@code builtin=true} 的四条内置角色（super/ops/operator/moderator）不可删除、{@code code} 不可改 ——
 * 内置角色的权限矩阵是代码常量 {@link BuiltinRoles}，改库不改代码会在下次启动被 seed 回写覆盖。
 */
@Entity
@Table(name = "admin_roles")
public class AdminRoleEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "code", nullable = false, length = 32)
  private String code;

  @Column(name = "name", nullable = false, length = 64)
  private String name;

  @Column(name = "description", length = 255)
  private String description;

  @Column(name = "builtin", nullable = false)
  private boolean builtin;

  /** 数值越小权限越高（能力排序用；本期仅展示，不做层级穿透判定）。 */
  @Column(name = "rank", nullable = false)
  private short rank;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  @Column(name = "updated_at", nullable = false)
  private Instant updatedAt;

  public Long getId() {
    return id;
  }

  public String getCode() {
    return code;
  }

  public void setCode(String code) {
    this.code = code;
  }

  public String getName() {
    return name;
  }

  public void setName(String name) {
    this.name = name;
  }

  public String getDescription() {
    return description;
  }

  public void setDescription(String description) {
    this.description = description;
  }

  public boolean isBuiltin() {
    return builtin;
  }

  public void setBuiltin(boolean builtin) {
    this.builtin = builtin;
  }

  public short getRank() {
    return rank;
  }

  public void setRank(short rank) {
    this.rank = rank;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }

  public Instant getUpdatedAt() {
    return updatedAt;
  }

  public void setUpdatedAt(Instant updatedAt) {
    this.updatedAt = updatedAt;
  }
}
