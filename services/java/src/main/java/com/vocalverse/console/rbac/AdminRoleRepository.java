package com.vocalverse.console.rbac;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/** 角色仓库（docs/50 §5.3.2）。 */
public interface AdminRoleRepository extends JpaRepository<AdminRoleEntity, Long> {

  Optional<AdminRoleEntity> findByCode(String code);

  List<AdminRoleEntity> findAllByOrderByRankAscIdAsc();

  boolean existsByCode(String code);
}
