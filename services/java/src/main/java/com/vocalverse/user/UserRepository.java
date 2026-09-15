package com.vocalverse.user;

import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserRepository extends JpaRepository<UserEntity, Long> {

  Optional<UserEntity> findByUsernameIgnoreCase(String username);

  Optional<UserEntity> findByEmailIgnoreCase(String email);

  /**
   * 管理端搜索：username 子串（大小写不敏感）+ status 过滤；条件为空即不筛。
   *
   * <p><b>⚠️ {@code cast} 是必须的</b>（2026-09-10 真 PG 实测）：{@code concat('%', :q, '%')} 被 Hibernate 翻译成
   * {@code ('%'||?||'%')}，而那个 {@code ?} 在 PG 里没有类型线索 → PG 把 {@code ||} 解析成 **bytea** 版本 → 报 {@code
   * function lower(bytea) does not exist}（{@code GET /api/v1/console/users} 清空筛选必然 500）。同一个仓库在 H2
   * 上完全正常 —— 现有 Java 测试跑 H2，结构上抓不到。 详见 {@code AdminAuditLogRepository#search} 的说明。
   */
  @Query(
      "select u from UserEntity u "
          + "where (cast(:status as string) is null or u.status = :status) "
          + "and (cast(:q as string) is null or lower(u.username) like lower(concat('%', cast(:q as string), '%'))) "
          + "order by u.id")
  Page<UserEntity> search(@Param("status") String status, @Param("q") String q, Pageable pageable);
}
