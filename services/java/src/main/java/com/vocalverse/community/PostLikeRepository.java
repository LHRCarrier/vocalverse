package com.vocalverse.community;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/** 点赞事实表（Java 写方；(post_id, liker_id) 唯一兜底幂等）。 */
public interface PostLikeRepository extends JpaRepository<PostLikeEntity, Long> {

  Optional<PostLikeEntity> findByPostIdAndLikerId(Long postId, Long likerId);

  List<PostLikeEntity> findByLikerIdAndPostIdIn(Long likerId, List<Long> postIds);

  void deleteByPostIdAndLikerId(Long postId, Long likerId);
}
