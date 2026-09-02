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

  /** 管理端搜索：username 子串（大小写不敏感）+ status 过滤；条件为空即不筛。 */
  @Query(
      "select u from UserEntity u "
          + "where (:status is null or u.status = :status) "
          + "and (:q is null or lower(u.username) like lower(concat('%', :q, '%'))) "
          + "order by u.id")
  Page<UserEntity> search(@Param("status") String status, @Param("q") String q, Pageable pageable);
}
