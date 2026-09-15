package com.vocalverse.console.rbac;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 权限码目录（docs/50 §5.3.3；Java 写方）。
 *
 * <p><b>代码为准、表为索引</b>（docs/50 §4.2）：{@link PermissionCatalog} 是唯一真源，本表由启动 seed 幂等 upsert
 * 回写；任何「改库不改代码」的改动会在下次启动被覆盖 —— 这是刻意的，避免权限码在库里漂移。
 */
@Entity
@Table(name = "admin_permissions")
public class AdminPermissionEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "code", nullable = false, length = 64)
  private String code;

  @Column(name = "module", nullable = false, length = 24)
  private String module;

  @Column(name = "name", nullable = false, length = 64)
  private String name;

  @Column(name = "description", length = 255)
  private String description;

  @Column(name = "sort", nullable = false)
  private short sort;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public Long getId() {
    return id;
  }

  public String getCode() {
    return code;
  }

  public void setCode(String code) {
    this.code = code;
  }

  public String getModule() {
    return module;
  }

  public void setModule(String module) {
    this.module = module;
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

  public short getSort() {
    return sort;
  }

  public void setSort(short sort) {
    this.sort = sort;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
