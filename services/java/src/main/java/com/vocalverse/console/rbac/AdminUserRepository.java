package com.vocalverse.console.rbac;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/** 管理端账号仓库（docs/50 §5.3.1）。{@code uq_admin_users_username_lower} 为表达式唯一索引 → 查询一律 lower()。 */
public interface AdminUserRepository extends JpaRepository<AdminUserEntity, Long> {

  @Query("select a from AdminUserEntity a where lower(a.username) = lower(:username)")
  Optional<AdminUserEntity> findByUsernameIgnoreCase(@Param("username") String username);

  @Query("select count(a) from AdminUserEntity a where lower(a.username) = lower(:username)")
  long countByUsernameIgnoreCase(@Param("username") String username);

  long countByRoleId(Long roleId);

  /**
   * 管理端列表：q/roleId/status 三参可空过滤（docs/50 §10.2 GET /admins）。
   *
   * <p><b>⚠️ 每个空值判断都写了 {@code cast(:p as …)}，不是冗余</b>（2026-09-10 真 PG 实测）： PostgreSQL 在 **Parse
   * 阶段**就要求确定每个 {@code $n} 的类型，而 `{@code ? is null}` 这个用法 本身不提供任何类型线索 —— 参数为 NULL 时驱动也不会补类型 OID（非
   * NULL 时会补，所以**带筛选反而正常**）。 结果是 {@code GET /api/v1/console/users?page_size=1}（不带任何筛选）**必然 500**
   * （{@code could not determine data type of parameter $1}），而 H2 上一切正常 —— 现有 Java 测试跑在
   * H2，**结构上抓不到这一类缺陷**（同类已出现三次：审核单 CAS 的 {@code coalesce}、 审计 {@code from/to}、本处）。加显式 cast 后 PG 拿到
   * `{@code cast(? as varchar) is null}`， 类型确定，语义与原来逐字相同。
   */
  @Query(
      "select a from AdminUserEntity a "
          + "where (cast(:q as string) is null or lower(a.username) like lower(concat('%', cast(:q as string), '%')) "
          + "       or lower(a.displayName) like lower(concat('%', cast(:q as string), '%'))) "
          + "and (cast(:roleId as long) is null or a.roleId = :roleId) "
          + "and (cast(:status as string) is null or a.status = :status) "
          + "order by a.id desc")
  Page<AdminUserEntity> search(
      @Param("q") String q,
      @Param("roleId") Long roleId,
      @Param("status") String status,
      Pageable pageable);

  /** 停用/改权/改密时 bump token_epoch：已有 access token 的 epo claim 立即不匹配 → 下一请求 46001。 */
  @Modifying(clearAutomatically = true, flushAutomatically = true)
  @Query("update AdminUserEntity a set a.tokenEpoch = a.tokenEpoch + 1 where a.id = :id")
  int bumpTokenEpoch(@Param("id") Long id);

  List<AdminUserEntity> findByRoleId(Long roleId);
}
