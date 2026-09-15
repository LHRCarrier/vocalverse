package com.vocalverse.console.rbac;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

/** 权限码目录仓库（docs/50 §5.3.3）。目录按 module 分组返回，供前端权限控制台渲染。 */
public interface AdminPermissionRepository extends JpaRepository<AdminPermissionEntity, Long> {

  Optional<AdminPermissionEntity> findByCode(String code);

  List<AdminPermissionEntity> findAllByOrderByModuleAscSortAscCodeAsc();

  @Query("select count(p) from AdminPermissionEntity p")
  long countAll();
}
