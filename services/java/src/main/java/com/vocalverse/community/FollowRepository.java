package com.vocalverse.community;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/** 关注关系仓库（Java 写方；(follower, followee) 唯一键幂等）。 */
public interface FollowRepository extends JpaRepository<FollowEntity, Long> {

  Optional<FollowEntity> findByFollowerIdAndFolloweeId(Long followerId, Long followeeId);

  List<FollowEntity> findByFollowerIdOrderByCreatedAtDesc(Long followerId);

  /** 互关判定：目标人群里有多少人也关注了我。 */
  List<FollowEntity> findByFolloweeIdAndFollowerIdIn(Long followeeId, List<Long> followerIds);

  /** J-06：我是否关注了这批目标（一次集合查询替代逐个判定的 1 查询/人）。 */
  List<FollowEntity> findByFollowerIdAndFolloweeIdIn(Long followerId, List<Long> followeeIds);

  /** J-06：空关注快检（followingFeed 无关注时不跑 EXISTS 查询）。 */
  long countByFollowerId(Long followerId);

  void deleteByFollowerIdAndFolloweeId(Long followerId, Long followeeId);
}
