package com.vocalverse.community;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/** 私信已读水位仓库（Java 写 · docs/49 §1.2）：一会话一行，读改写走悲观锁外的「读 → max → 存」。 */
public interface DmReadStateRepository extends JpaRepository<DmReadStateEntity, Long> {

  Optional<DmReadStateEntity> findByUserIdAndPeerId(Long userId, Long peerId);
}
