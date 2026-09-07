package com.vocalverse.user;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RefreshTokenRepository extends JpaRepository<RefreshTokenEntity, Long> {

  Optional<RefreshTokenEntity> findByTokenHash(String tokenHash);

  /** 该用户未撤销的 refresh token（/auth/logout 批量吊销，2026-09-07）。 */
  List<RefreshTokenEntity> findByUserIdAndRevokedAtIsNull(Long userId);
}
