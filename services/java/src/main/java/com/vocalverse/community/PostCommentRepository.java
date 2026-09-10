package com.vocalverse.community;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

/**
 * 评论仓库（Java 写方；展示过滤统一可见谓词；keyset ASC 分页）。
 *
 * <p>同 PostRepository.feed：JPA Criteria 判空，避免 PG 未类型化 NULL 参数（42P18）。
 *
 * <p>J-04/J-03 注记（2026-09-10）：通知的评论流原为本类的 {@code findMine}（近 50 条窗口 + 内存重筛，J-04 补过 {@code
 * status='visible'}）；J-03 起并入 {@link PostInteractionRepository#notificationComments} 的 DB 层 keyset
 * 分页（同口径含可见性谓词），旧方法已删除。
 *
 * <p><b>2026-09-10 管理端隐藏</b>：可见谓词从 {@code status='visible'} 放宽为 {@code status NOT IN
 * ('hidden','deleted')}（docs/50 §6.2 联动硬点 1）。评论列表是隐藏评论最容易 泄漏的地方 —— 帖子被隐藏后如果评论还能读到，等于隐藏没生效。
 */
public interface PostCommentRepository
    extends JpaRepository<PostCommentEntity, Long>, JpaSpecificationExecutor<PostCommentEntity> {

  default List<PostCommentEntity> page(Long postId, Instant ts, Long id, Pageable pageable) {
    return findAll(
            (root, query, cb) -> {
              List<jakarta.persistence.criteria.Predicate> ps = new ArrayList<>();
              ps.add(cb.equal(root.get("postId"), postId));
              ps.add(cb.not(root.get("status").in("hidden", "deleted")));
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
}
