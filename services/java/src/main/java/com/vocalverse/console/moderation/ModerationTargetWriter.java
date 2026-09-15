package com.vocalverse.console.moderation;

import com.vocalverse.community.PostCommentEntity;
import com.vocalverse.community.PostCommentRepository;
import com.vocalverse.community.PostEntity;
import com.vocalverse.community.PostRepository;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import java.time.Instant;
import java.util.Optional;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 审核目标读写（docs/50 §5.4：控制台对既有表「只读 + 最小写」）。
 *
 * <p><b>写什么</b>：{@code posts.status} / {@code post_comments.status} → {@code hidden} | {@code
 * deleted}。 只有 status 一列 —— 不改 {@code like_count}/{@code comment_count}（docs/50 §6.2 联动硬点 2： 隐藏 ≠
 * 删除，恢复后计数不得漂移）。
 *
 * <h2>为什么 media / direct_message 明确拒绝处置（而不是「以后再说」）</h2>
 *
 * <p>docs/50 §5.3.8 的决策表把 {@code media_assets.status='hidden'} 挂在 Java 的控制台决定端点上 （§5.4 只补了一句「media
 * 用 NOT VALID + VALIDATE 扩 CHECK」）。这与**写方矩阵直接冲突**：
 *
 * <ul>
 *   <li>{@code media_assets} 的写方是 **Python**（docs/50 §5.4 表格「Python 写（既有写方=Python ✔）」）；
 *   <li>docs/06 §10 的写方矩阵与 docs/20「Java→Python 写探针已废弃」都明确：跨服务写别人的表会破坏
 *       单一写方不变量（两个服务各自的事务里改同一行，冲突与审计归属都无法收敛）。
 * </ul>
 *
 * <p>所以本实现**拒绝**对 media 目标做 hide/delete（46009 + 明确指向 Python 侧端点），而不是照文档 跨边界写表。{@code
 * direct_message} 同样只读（docs/50 §5.4：「本期只读列表、不提供处置」）。
 *
 * <p>为什么是「明确报错」而不是「静默成功」：决定性的一条 —— 静默成功会让审核员看到「已隐藏」的 UI 反馈，
 * 而媒体其实仍然可见。<b>一个会说谎的审核动作比一个失败的审核动作危险得多。</b>
 */
@Component
public class ModerationTargetWriter {

  public static final String STATUS_HIDDEN = "hidden";
  public static final String STATUS_DELETED = "deleted";

  private final PostRepository posts;
  private final PostCommentRepository comments;

  public ModerationTargetWriter(PostRepository posts, PostCommentRepository comments) {
    this.posts = posts;
    this.comments = comments;
  }

  /** 目标是否存在（docs/50 §10.4 46009：审核对象不存在，内容已物理消失）。 */
  @Transactional(readOnly = true)
  public boolean exists(String targetType, Long targetId) {
    return switch (targetType) {
      case ModerationCaseEntity.TARGET_POST -> posts.findById(targetId).isPresent();
      case ModerationCaseEntity.TARGET_COMMENT -> comments.findById(targetId).isPresent();
      default -> false;
    };
  }

  /** 目标当前 status（做快照 / 幂等判定用）；不可读的目标返回 null。 */
  @Transactional(readOnly = true)
  public String currentStatus(String targetType, Long targetId) {
    if (ModerationCaseEntity.TARGET_POST.equals(targetType)) {
      return posts.findById(targetId).map(PostEntity::getStatus).orElse(null);
    }
    if (ModerationCaseEntity.TARGET_COMMENT.equals(targetType)) {
      return comments.findById(targetId).map(PostCommentEntity::getStatus).orElse(null);
    }
    return null;
  }

  /** 送审内容快照（≤500；**不存全文**，避免二次留存，docs/50 §5.3.8）。 */
  @Transactional(readOnly = true)
  public String snippet(String targetType, Long targetId) {
    String raw = null;
    if (ModerationCaseEntity.TARGET_POST.equals(targetType)) {
      raw = posts.findById(targetId).map(PostEntity::getBody).orElse(null);
    } else if (ModerationCaseEntity.TARGET_COMMENT.equals(targetType)) {
      raw = comments.findById(targetId).map(PostCommentEntity::getBody).orElse(null);
    }
    if (raw == null) {
      return null;
    }
    String trimmed = raw.strip();
    return trimmed.length() <= 500 ? trimmed : trimmed.substring(0, 500);
  }

  /** 目标的作者用户 id（快照的 authorId；跨域弱引用，不加 FK）。 */
  @Transactional(readOnly = true)
  public Long authorId(String targetType, Long targetId) {
    if (ModerationCaseEntity.TARGET_POST.equals(targetType)) {
      return posts.findById(targetId).map(PostEntity::getAuthorId).orElse(null);
    }
    if (ModerationCaseEntity.TARGET_COMMENT.equals(targetType)) {
      return comments.findById(targetId).map(PostCommentEntity::getAuthorId).orElse(null);
    }
    return null;
  }

  /**
   * 施加处置（与决定同一事务）。
   *
   * <p><b>幂等</b>：目标已是 hidden/deleted 时直接成功（docs/50 §6.2 表格「目标已 hidden → 幂等成功」）——
   * 重复决定不该因为「已经隐藏了」而报错。
   */
  @Transactional
  public void applyStatus(String targetType, Long targetId, String status) {
    Instant now = Instant.now();
    if (ModerationCaseEntity.TARGET_POST.equals(targetType)) {
      PostEntity e =
          posts
              .findById(targetId)
              .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND));
      if (status.equals(e.getStatus())) {
        return; // 幂等
      }
      e.setStatus(status);
      e.setUpdatedAt(now);
      posts.save(e);
      return;
    }
    if (ModerationCaseEntity.TARGET_COMMENT.equals(targetType)) {
      PostCommentEntity e =
          comments
              .findById(targetId)
              .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND));
      if (status.equals(e.getStatus())) {
        return; // 幂等
      }
      e.setStatus(status);
      e.setUpdatedAt(now);
      comments.save(e);
      return;
    }
    // media / direct_message：Java 不是写方（见类注释）→ 明确拒绝，绝不静默成功
    throw new ConsoleException(
        ConsoleErrorCodes.TARGET_NOT_FOUND,
        "目标类型暂不支持 Java 侧处置："
            + targetType
            + "。媒体（视频/图片）的隐藏与恢复请在控制台「媒体库」页面操作"
            + "（该端点由 Python 服务提供，content:media:write）；私信本期只读。",
        ConsoleErrorCodes.status(ConsoleErrorCodes.TARGET_NOT_FOUND));
  }

  /** 目标是否可被 Java 侧处置（建单前置校验用）。 */
  public boolean javaWritable(String targetType) {
    return ModerationCaseEntity.TARGET_POST.equals(targetType)
        || ModerationCaseEntity.TARGET_COMMENT.equals(targetType);
  }

  /**
   * 该目标类型是否支持「隐藏/删除」处置（docs/50 §6.2 决策表的可执行子集）。
   *
   * <p>用于在**决定之前**给出可理解的错误，而不是让 {@link #applyStatus} 在事务中途抛错 （虽然两者最终都回滚，但提前判断能让错误消息更贴近用户意图）。
   */
  public boolean supportsHideDelete(String targetType) {
    return ModerationCaseEntity.TARGET_POST.equals(targetType)
        || ModerationCaseEntity.TARGET_COMMENT.equals(targetType);
  }

  public Optional<PostEntity> post(Long id) {
    return posts.findById(id);
  }

  public Optional<PostCommentEntity> comment(Long id) {
    return comments.findById(id);
  }
}
