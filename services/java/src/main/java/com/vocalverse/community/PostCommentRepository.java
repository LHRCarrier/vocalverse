package com.vocalverse.community;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * 评论仓库（Java 写方；展示过滤 status='visible'；keyset ASC 分页）。
 *
 * <p>同 PostRepository.feed：JPA Criteria 判空，避免 PG 未类型化 NULL 参数（42P18）。
 */
public interface PostCommentRepository
    extends JpaRepository<PostCommentEntity, Long>, JpaSpecificationExecutor<PostCommentEntity> {

  default List<PostCommentEntity> page(Long postId, Instant ts, Long id, Pageable pageable) {
    return findAll(
            (root, query, cb) -> {
              List<jakarta.persistence.criteria.Predicate> ps = new ArrayList<>();
              ps.add(cb.equal(root.get("postId"), postId));
              ps.add(cb.equal(root.get("status"), "visible"));
              if (ts != null) {
                ps.add(
                    cb.or(
                        cb.greaterThan(root.get("createdAt"), ts),
                        cb.and(
                            cb.equal(root.get("createdAt"), ts),
                            cb.greaterThan(root.get("id"), id))));
              }
              return cb.and(ps.toArray(new jakarta.persistence.criteria.Predicate[0]));
            },
            pageable)
        .getContent();
  }

  /** S2 通知：指向我（作者）可见帖子的**可见评论**，按时间倒序取近 window。
   *
   * <p>J-04（2026-09-08）：补 {@code c.status = 'visible'}——此前只过滤父帖状态，软删/隐藏评论
   * 仍会进入通知聚合（点击无法定位，软删约束被绕过）；与 comments() 展示路径 page() 的状态口径对齐。
   */
  @Query(
      "SELECT c FROM PostCommentEntity c "
          + "WHERE c.status = 'visible' AND c.postId IN (SELECT p.id FROM PostEntity p WHERE p.authorId = :authorId AND p.status = 'visible') "
          + "ORDER BY c.createdAt DESC")
  List<PostCommentEntity> findMine(@Param("authorId") Long authorId, Pageable pageable);
}
