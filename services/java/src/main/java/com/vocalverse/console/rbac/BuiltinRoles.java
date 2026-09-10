package com.vocalverse.console.rbac;

import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 内置 4 角色与权限矩阵（docs/50 §4.2 表格逐字落地）。
 *
 * <p>{@code builtin=true} 的角色**不可删除、{@code code} 不可改**（{@link RbacService} 守卫）： 它们是控制台自身的登录前提 —— 删掉
 * {@code super} 会让权限控制台自锁（无人能再分配权限）。
 *
 * <p>矩阵要点：
 *
 * <ul>
 *   <li>{@code super} 只登记 {@code *} 通配，由 {@link RbacService} 展开为全部 35 个码 —— 新增权限码时 super
 *       **自动获得**，不必改 seed（docs/50 §4.2）；
 *   <li>{@code ops} = {@code ops:*}(7) + {@code console:audit:read}；
 *   <li>{@code operator} = 运营域 **Java 实现的** 15 个 content 码（song/listening/scenario/question/ticket
 *       × read/write/publish）+ {@code console:audit:read}；
 *   <li>{@code moderator} = {@code moderation:*}(4) + 内容只读 4 个（song/listening/book/**media**）+
 *       {@code console:audit:read}。
 * </ul>
 *
 * <p><b>与 docs/50 §4.2 的偏差（已核实，逐条说明为什么「按文档字面写」会坏）</b>：
 *
 * <ol>
 *   <li><b>去掉 {@code moderation:word:read/write}</b>：§6.2 联动硬点 4 明确「自动送审本期不接关键词引擎 （敏感词库为
 *       P1）」，即**没有任何端点消费这两个码**。保留它们会让权限控制台显示「审核员能管敏感词」 而实际点开是 404 —— 一个不能用的权限比没有权限更糟（它会让运维以为已经配好了）。
 *       与 §4.2 表格的「moderation:* = 7」相差 2 条，正是这两个；去掉后总数恰好是设计反复引用的 **35**；
 *   <li><b>{@code operator} 不拿 Python 侧的 content 码</b>（{@code content:book:*} / {@code
 *       content:media:*}， docs/50 §3.2 明确归 Python）：Java 侧无对应端点，发放等于造出「表里有、实际无处可用」的权限；
 *   <li><b>{@code moderator} 必须持有 {@code content:media:read}</b>（原设计只给了 {@code
 *       content:{song,listening,book}:read}）：用户点名的职责是「社区帖子、评论、**视频（媒体）**审核」，
 *       而审批媒体举报必须看得见媒体条目。缺这个码会让「视频审核」在权限矩阵里根本不存在 —— 审核员点进媒体审核页只会拿到 46002。 <b>注意 {@code
 *       content:media:read} 是只读</b>：媒体的隐藏/恢复归 **Python**（§5.4 + docs/06 §10 写方矩阵）， 所以这里给读不给写，Java
 *       侧也不提供媒体处置端点（见 {@code ModerationService} 的 media 守卫）。
 * </ol>
 */
public final class BuiltinRoles {

  private BuiltinRoles() {}

  public static final String SUPER = "super";
  public static final String OPS = "ops";
  public static final String OPERATOR = "operator";
  public static final String MODERATOR = "moderator";

  /** 一个内置角色的定义：code + 名称 + 描述 + rank + 权限码集合。 */
  public record Role(
      String code, String name, String description, int rank, Set<String> permissionCodes) {}

  private static final List<Role> ALL = build();

  private static List<Role> build() {
    return List.of(
        new Role(SUPER, "超级管理员", "全部权限（* 通配，新增权限码自动获得）", 1, Set.of(PermissionCatalog.WILDCARD)),
        new Role(
            OPS,
            "运维",
            "运维域全量 + 审计只读（trace 内容权限单独成码，见 docs/50 §4.2）",
            10,
            Set.of(
                PermissionCatalog.OPS_OVERVIEW_READ,
                PermissionCatalog.OPS_METRIC_READ,
                PermissionCatalog.OPS_ALERT_READ,
                PermissionCatalog.OPS_ALERT_WRITE,
                PermissionCatalog.OPS_TRACE_READ,
                PermissionCatalog.OPS_TRACE_CONTENT_READ,
                PermissionCatalog.OPS_MAINTENANCE_WRITE,
                PermissionCatalog.CONSOLE_AUDIT_READ)),
        new Role(
            OPERATOR,
            "运营",
            "Java 侧内容域全量 + 工单 + 敏感词只读",
            20,
            Set.of(
                PermissionCatalog.CONTENT_SONG_READ,
                PermissionCatalog.CONTENT_SONG_WRITE,
                PermissionCatalog.CONTENT_SONG_PUBLISH,
                PermissionCatalog.CONTENT_LISTENING_READ,
                PermissionCatalog.CONTENT_LISTENING_WRITE,
                PermissionCatalog.CONTENT_LISTENING_PUBLISH,
                PermissionCatalog.CONTENT_SCENARIO_READ,
                PermissionCatalog.CONTENT_SCENARIO_WRITE,
                PermissionCatalog.CONTENT_SCENARIO_PUBLISH,
                PermissionCatalog.CONTENT_QUESTION_READ,
                PermissionCatalog.CONTENT_QUESTION_WRITE,
                PermissionCatalog.CONTENT_TICKET_READ,
                PermissionCatalog.CONTENT_TICKET_WRITE,
                PermissionCatalog.CONSOLE_AUDIT_READ,
                // 2026-09-10：旧管理端退役后，App 用户停用/编辑的唯一实现在控制台
                // （ConsoleUserController）。不发给运营的话「封禁用户」会没有任何角色能做。
                PermissionCatalog.CONSOLE_USER_READ,
                PermissionCatalog.CONSOLE_USER_WRITE)),
        new Role(
            MODERATOR,
            "审核",
            "审核域全量 + 内容只读（歌曲/听力/书籍/媒体）+ 审计只读",
            30,
            Set.of(
                PermissionCatalog.MODERATION_QUEUE_READ,
                PermissionCatalog.MODERATION_DECIDE,
                PermissionCatalog.MODERATION_REPORT_READ,
                PermissionCatalog.MODERATION_REPORT_HANDLE,
                PermissionCatalog.CONTENT_SONG_READ,
                PermissionCatalog.CONTENT_LISTENING_READ,
                PermissionCatalog.CONTENT_BOOK_READ,
                // 「视频（媒体）审核」的可见性前提；只读 —— 处置归 Python（docs/50 §5.4）
                PermissionCatalog.CONTENT_MEDIA_READ,
                PermissionCatalog.CONSOLE_AUDIT_READ)));
  }

  public static List<Role> all() {
    return ALL;
  }

  public static Role byCode(String code) {
    return ALL.stream().filter(r -> r.code().equals(code)).findFirst().orElse(null);
  }

  /** code → 名称（审计/展示用）。 */
  public static Map<String, String> names() {
    Map<String, String> m = new LinkedHashMap<>();
    ALL.forEach(r -> m.put(r.code(), r.name()));
    return m;
  }

  /**
   * 目录里登记但本节未显式列出的码（仅用于启动日志自证，不参与授权）。
   *
   * <p>目前为 Python 独占的 {@code content:book:write} / {@code content:book:publish} / {@code
   * content:media:read} / {@code content:media:write} —— 它们在内置矩阵里确实没有任何角色持有。
   */
  public static Set<String> codesWithoutBuiltinHolder() {
    Set<String> held = new HashSet<>();
    for (Role r : ALL) {
      if (!r.permissionCodes().contains(PermissionCatalog.WILDCARD)) {
        held.addAll(r.permissionCodes());
      }
    }
    Set<String> all = new HashSet<>(PermissionCatalog.allCodes());
    all.removeAll(held);
    return all;
  }
}
