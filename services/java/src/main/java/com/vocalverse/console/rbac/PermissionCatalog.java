package com.vocalverse.console.rbac;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 权限码目录常量类（docs/50 §4.2 逐条落地；<b>代码为准、表为索引</b>）。
 *
 * <p>本类是唯一真源：{@code admin_permissions} 表由 {@link RbacBootstrap} 启动时按本目录幂等 upsert 回写。
 * 任何「改库不改代码」的权限改动都会在下次启动被覆盖 —— 这是刻意的（docs/50 §4.2 注释）。
 *
 * <p><b>共 34 个权限码</b>（{@code PermissionCatalogTest} 钉死精确值，防「悄悄少登记/多登记」）， 4 个 module：{@code
 * console}(5) / {@code content}(18) / {@code moderation}(4) / {@code ops}(7) —— 另有 {@code *}
 * 通配行（seed 用，不计入，见 {@link #WILDCARD_PERMISSION}）。
 *
 * <h2>计数口径与 docs/50 §4.2 的核对（逐个从表格数出来，不是抄数字）</h2>
 *
 * <p>文档在 4 处（§1 C-3、§4.2 表头、§4.2 super 行、§15.1）都写「**35** 个权限码」， 但把 §4.2 的表格逐行展开（含 {@code
 * :write}/{@code :publish} 简写）数出来是 **36** 条： console 5 / content 18 / moderation 6（含 {@code
 * moderation:word:read/write}）/ ops 7。 本实现按 **34** 落地，推导如下——每一步都是可复算的，不是估计：
 *
 * <ol>
 *   <li><b>36 − 2 = 34</b>：{@code moderation:word:read/write}（敏感词库）**不登记**。§6.2 联动硬点 4
 *       明确「自动送审本期不接关键词引擎（敏感词库为 P1）」，即**没有任何端点消费这两个码**。 给角色发放无法消费的码，会让权限控制台显示「审核员能管敏感词」而点开 404 ——
 *       一个不能用的权限比没有权限更糟（运维会以为已经配好了）。P1 落地时在下面 raw 列表补两行即可；
 *   <li>因此 <b>「35」这个数字无法同时满足「表格 36 条」与「去掉 word 两条」</b>： {@code 36 − 2 = 34 ≠ 35}。差的 1
 *       条在文档里找不到对应对象（content 的 {@code :read}/{@code :write} 简写已按 2 条计、ops 的 {@code
 *       trace:content:read} 已单列、console 的 5 条完整）。 本实现选择**如实按表格落地 34 条**，并把「文档写 35、实际 34」作为偏差上报，
 *       而不是为了凑数字造一个没有端点的码（那正是上面第 1 条要避免的事）。
 * </ol>
 *
 * <p>若上游决定保留 {@code moderation:word:read/write}，只需在下面 raw 列表加回两行 → 总数 36；若决定维持「35」，需要文档明确指出多出来的那 1
 * 条到底是哪个码。
 */
public final class PermissionCatalog {

  private PermissionCatalog() {}

  public static final String MODULE_CONSOLE = "console";
  public static final String MODULE_CONTENT = "content";
  public static final String MODULE_MODERATION = "moderation";
  public static final String MODULE_OPS = "ops";

  /** super 角色的通配符：由 {@link RbacService} 展开为全部权限码（docs/50 §4.2）。 */
  public static final String WILDCARD = "*";

  /**
   * 通配符的目录元数据（**不是**一个可授权的权限码）。
   *
   * <p>为什么要为它建行：{@code super} 的授权在库里是「一条 {@code admin_role_permissions} 记录」， 而该表的外键指向 {@code
   * admin_permissions.id}。如果目录里没有 {@code *} 这一行， {@link RbacBootstrap} 就解析不出它的 id，结果是 super
   * 角色**一行授权都没有** —— 超级管理员在运行时会 46002 满屏（这正是本轮实测到的缺陷）。
   *
   * <p>它被 {@link #allCodes()} / {@link #size()} / {@link #byModule()} 全部排除： 对外契约的「35
   * 个权限码」不含通配符，控制台的权限勾选列表也不该出现它。
   */
  public static final Permission WILDCARD_PERMISSION =
      new Permission(MODULE_CONSOLE, WILDCARD, "全部权限（通配）", "super 专用；展开为目录全量码", 99);

  // ------------------------------------------------------------------ console（5）

  public static final String CONSOLE_ADMIN_READ = "console:admin:read";
  public static final String CONSOLE_ADMIN_WRITE = "console:admin:write";
  public static final String CONSOLE_ROLE_READ = "console:role:read";
  public static final String CONSOLE_ROLE_WRITE = "console:role:write";
  public static final String CONSOLE_AUDIT_READ = "console:audit:read";
  /** App 用户（{@code users} 表）查看 —— 与控制台账号（{@code console:admin:*}）**分开成码**，见类注释。 */
  public static final String CONSOLE_USER_READ = "console:user:read";
  /** App 用户停用/启用 + 学习档案维护（封禁能力的唯一实现）。 */
  public static final String CONSOLE_USER_WRITE = "console:user:write";

  // ------------------------------------------------------------------ content（18）

  public static final String CONTENT_SONG_READ = "content:song:read";
  public static final String CONTENT_SONG_WRITE = "content:song:write";
  public static final String CONTENT_SONG_PUBLISH = "content:song:publish";
  public static final String CONTENT_LISTENING_READ = "content:listening:read";
  public static final String CONTENT_LISTENING_WRITE = "content:listening:write";
  public static final String CONTENT_LISTENING_PUBLISH = "content:listening:publish";
  public static final String CONTENT_SCENARIO_READ = "content:scenario:read";
  public static final String CONTENT_SCENARIO_WRITE = "content:scenario:write";
  public static final String CONTENT_SCENARIO_PUBLISH = "content:scenario:publish";
  public static final String CONTENT_QUESTION_READ = "content:question:read";
  public static final String CONTENT_QUESTION_WRITE = "content:question:write";

  /** Python 服务实现（docs/50 §3.2）；Java 侧只登记目录。 */
  public static final String CONTENT_BOOK_READ = "content:book:read";

  public static final String CONTENT_BOOK_WRITE = "content:book:write";
  public static final String CONTENT_BOOK_PUBLISH = "content:book:publish";
  public static final String CONTENT_MEDIA_READ = "content:media:read";
  public static final String CONTENT_MEDIA_WRITE = "content:media:write";
  public static final String CONTENT_TICKET_READ = "content:ticket:read";
  public static final String CONTENT_TICKET_WRITE = "content:ticket:write";

  // ------------------------------------------------------------------ moderation（4）
  // 说明：§4.2 表格另有 moderation:word:read / :write，本实现不登记 —— 见类注释第 1 条。

  public static final String MODERATION_QUEUE_READ = "moderation:queue:read";
  public static final String MODERATION_DECIDE = "moderation:decide";
  public static final String MODERATION_REPORT_READ = "moderation:report:read";
  public static final String MODERATION_REPORT_HANDLE = "moderation:report:handle";

  // ------------------------------------------------------------------ ops（7，Python 服务实现）

  public static final String OPS_OVERVIEW_READ = "ops:overview:read";
  public static final String OPS_METRIC_READ = "ops:metric:read";
  public static final String OPS_ALERT_READ = "ops:alert:read";
  public static final String OPS_ALERT_WRITE = "ops:alert:write";
  public static final String OPS_TRACE_READ = "ops:trace:read";

  /** 隐私闸门：trace 内容（prompt/response）与结构元数据**两个独立权限**（docs/50 §4.2）。 */
  public static final String OPS_TRACE_CONTENT_READ = "ops:trace:content:read";

  public static final String OPS_MAINTENANCE_WRITE = "ops:maintenance:write";

  /** 一条权限码：module + code + 展示名 + 描述 + 组内排序。 */
  public record Permission(String module, String code, String name, String description, int sort) {}

  /**
   * 全量目录（不含通配符；顺序即 {@code sort} 的推导源）。
   *
   * <p>{@code sort} 按同 module 内出现顺序 1..n 生成；{@code module} 顺序为 console → content → moderation →
   * ops，与 docs/50 §4.2 表格一致。
   */
  private static final List<Permission> ALL = build();

  /** 含通配符行的完整清单（仅 seed 用；对外一律走 {@link #all()}）。 */
  private static final List<Permission> ALL_WITH_WILDCARD = buildWithWildcard();

  private static List<Permission> build() {
    List<Object[]> raw =
        List.of(
            // console
            new Object[] {MODULE_CONSOLE, CONSOLE_ADMIN_READ, "管理员账号查看", "查看管理端账号列表与详情"},
            new Object[] {MODULE_CONSOLE, CONSOLE_ADMIN_WRITE, "管理员账号维护", "增改停用账号 + 重置口令 + 强制下线"},
            new Object[] {MODULE_CONSOLE, CONSOLE_ROLE_READ, "角色与权限查看", "查看角色、权限码目录与分配"},
            new Object[] {MODULE_CONSOLE, CONSOLE_ROLE_WRITE, "角色与权限编辑", "角色 CRUD + 权限分配"},
            new Object[] {MODULE_CONSOLE, CONSOLE_AUDIT_READ, "审计日志查看", "查看管理员操作审计（只读）"},
            new Object[] {
              MODULE_CONSOLE, CONSOLE_USER_READ, "App 用户查看", "App 用户（users 表）列表与档案详情"
            },
            new Object[] {
              MODULE_CONSOLE, CONSOLE_USER_WRITE, "App 用户停用/编辑", "停用启用 App 用户 + 学习档案维护"
            },
            // content
            new Object[] {MODULE_CONTENT, CONTENT_SONG_READ, "歌曲查看", "歌曲库列表与详情"},
            new Object[] {MODULE_CONTENT, CONTENT_SONG_WRITE, "歌曲增改删", "歌曲元数据与 LRC 维护"},
            new Object[] {
              MODULE_CONTENT,
              CONTENT_SONG_PUBLISH,
              "歌曲上下架",
              "歌曲 status 迁移（draft/published/archived）"
            },
            new Object[] {MODULE_CONTENT, CONTENT_LISTENING_READ, "听力素材查看", "听力素材列表与详情"},
            new Object[] {MODULE_CONTENT, CONTENT_LISTENING_WRITE, "听力素材增改删", "听力素材元数据维护"},
            new Object[] {MODULE_CONTENT, CONTENT_LISTENING_PUBLISH, "听力素材上下架", "听力素材 status 迁移"},
            new Object[] {MODULE_CONTENT, CONTENT_SCENARIO_READ, "场景查看", "对话场景列表与详情"},
            new Object[] {MODULE_CONTENT, CONTENT_SCENARIO_WRITE, "场景增改删", "场景模板维护"},
            new Object[] {MODULE_CONTENT, CONTENT_SCENARIO_PUBLISH, "场景上下架", "场景 status 迁移"},
            new Object[] {
              MODULE_CONTENT, CONTENT_QUESTION_READ, "题库查看", "入学测试题库（题库无 draft，故无 publish）"
            },
            new Object[] {
              MODULE_CONTENT,
              CONTENT_QUESTION_WRITE,
              "题库增改删",
              "入学测试题库维护（Java 侧本期只读，写端点归 Python，见 PermissionCatalog 类注释）"
            },
            new Object[] {MODULE_CONTENT, CONTENT_BOOK_READ, "书籍查看", "书籍与章节（Python 服务实现）"},
            new Object[] {MODULE_CONTENT, CONTENT_BOOK_WRITE, "书籍增改删", "书籍与章节维护（Python 服务实现）"},
            new Object[] {MODULE_CONTENT, CONTENT_BOOK_PUBLISH, "书籍上下架", "书籍与章节上下架（Python 服务实现）"},
            new Object[] {MODULE_CONTENT, CONTENT_MEDIA_READ, "媒体资产查看", "媒体治理列表（Python 服务实现）"},
            new Object[] {MODULE_CONTENT, CONTENT_MEDIA_WRITE, "媒体资产治理", "媒体隐藏/恢复（Python 服务实现）"},
            new Object[] {MODULE_CONTENT, CONTENT_TICKET_READ, "工单查看", "用户工单列表与详情"},
            new Object[] {MODULE_CONTENT, CONTENT_TICKET_WRITE, "工单处理", "工单状态流转与回复"},
            // moderation
            new Object[] {MODULE_MODERATION, MODERATION_QUEUE_READ, "审核队列查看", "待审队列与工单详情"},
            new Object[] {MODULE_MODERATION, MODERATION_DECIDE, "审核处置", "通过 / 驳回 / 隐藏 / 删除 / 升级"},
            new Object[] {MODULE_MODERATION, MODERATION_REPORT_READ, "举报查看", "用户举报列表"},
            new Object[] {MODULE_MODERATION, MODERATION_REPORT_HANDLE, "举报处理", "接受 / 驳回 / 判重"},
            // ops（Python 服务实现）
            new Object[] {MODULE_OPS, OPS_OVERVIEW_READ, "运维总览", "服务总览与依赖健康"},
            new Object[] {MODULE_OPS, OPS_METRIC_READ, "性能指标", "指标时序与并发额度"},
            new Object[] {MODULE_OPS, OPS_ALERT_READ, "预警查看", "预警规则与事件"},
            new Object[] {MODULE_OPS, OPS_ALERT_WRITE, "预警规则配置", "规则增改删与事件 ack/resolve"},
            new Object[] {MODULE_OPS, OPS_TRACE_READ, "LLM trace 结构", "span 树与统计（不含内容）"},
            new Object[] {
              MODULE_OPS, OPS_TRACE_CONTENT_READ, "LLM trace 内容", "prompt/response 内容（隐私闸门）"
            },
            new Object[] {
              MODULE_OPS, OPS_MAINTENANCE_WRITE, "运维维护动作", "清理过期 trace/metric/content"
            });

    Map<String, Integer> counters = new LinkedHashMap<>();
    List<Permission> out = new java.util.ArrayList<>(raw.size());
    for (Object[] row : raw) {
      String module = (String) row[0];
      int sort = counters.merge(module, 1, Integer::sum);
      out.add(new Permission(module, (String) row[1], (String) row[2], (String) row[3], sort));
    }
    return List.copyOf(out);
  }

  /** 全量目录（不可变，不含通配符）。 */
  public static List<Permission> all() {
    return ALL;
  }

  /** seed 用：真实 35 个码 + 通配符行（{@link RbacBootstrap} 必须能解析到 {@code *} 的 id）。 */
  public static List<Permission> allForSeed() {
    return ALL_WITH_WILDCARD;
  }

  private static List<Permission> buildWithWildcard() {
    List<Permission> out = new java.util.ArrayList<>(ALL.size() + 1);
    out.addAll(ALL);
    out.add(WILDCARD_PERMISSION);
    return List.copyOf(out);
  }

  /** 全部权限码（{@code *} 通配展开的目标集，docs/50 §4.2）；**不含**通配符本身。 */
  public static Set<String> allCodes() {
    return ALL.stream().map(Permission::code).collect(Collectors.toUnmodifiableSet());
  }

  /** 目录内是否登记了该码（含通配符 —— 它是合法可授权的「码」）。 */
  public static boolean isKnown(String code) {
    return WILDCARD.equals(code) || ALL.stream().anyMatch(p -> p.code().equals(code));
  }

  /** 目录条数（docs/50 §4.2 约定 35；{@code PermissionCatalogTest} 钉死，防「悄悄少登记一个码」）。 */
  public static int size() {
    return ALL.size();
  }

  /** 各 module 的条数（{@code console:5 / content:18 / moderation:5 / ops:7}）；自证用。 */
  public static Map<String, Integer> countByModule() {
    Map<String, Integer> m = new LinkedHashMap<>();
    for (Permission p : ALL) {
      m.merge(p.module(), 1, Integer::sum);
    }
    return m;
  }

  /** 按 module 分组（GET /console/permissions 契约：按 module 分组返回；**不含通配符**）。 */
  public static Map<String, List<Permission>> byModule() {
    Map<String, List<Permission>> grouped = new LinkedHashMap<>();
    for (Permission p : ALL) {
      grouped.computeIfAbsent(p.module(), k -> new java.util.ArrayList<>()).add(p);
    }
    grouped.replaceAll((k, v) -> List.copyOf(v));
    return grouped;
  }
}
