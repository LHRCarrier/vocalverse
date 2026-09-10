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

  /** 管理端列表：q/roleId/status 三参可空过滤（docs/50 §10.2 GET /admins）。 */
  @Query(
      "select a from AdminUserEntity a "
          + "where (:q is null or lower(a.username) like lower(concat('%', :q, '%')) "
          + "       or lower(a.displayName) like lower(concat('%', :q, '%'))) "
          + "and (:roleId is null or a.roleId = :roleId) "
          + "and (:status is null or a.status = :status) "
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
