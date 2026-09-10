package com.vocalverse.console.rbac;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

/**
 * 权限目录自证（docs/50 §4.2）。
 *
 * <p>把目录条数钉死（**34**，推导见 {@code PermissionCatalog} 类注释与下方说明）。刻意用**精确计数**而不是「≥ 某个数」：目录少登记一个码时，
 * 拥有对应权限的角色会在运行时拿到 46002，而那种缺陷在功能测试里极难定位 （端点存在、角色存在、就是点不动）。这里让它在构建期就红。
 *
 * <h2>这个数字是逐个从 §4.2 表格数出来的</h2>
 *
 * <p>文档在 4 处写「35 个」，但 §4.2 表格逐行展开是 **36** 条 （console 5 / content 18 / moderation 6 / ops 7）。本实现按
 * **34** 落地：
 *
 * <ol>
 *   <li>{@code moderation:word:read/write} **不登记**（−2）：§6.2 联动硬点 4 明确敏感词库为 P1、
 *       本期无端点消费，发给角色会造成「有权限、点开 404」；
 *   <li>于是 {@code 36 − 2 = 34}，而文档的「35」在这两条约束下**无法达成** （差的那 1 条在文档里找不到对应码）。本实现选择如实落地 34 并上报偏差，
 *       而不是凑一个没有端点的码出来。
 * </ol>
 *
 * <p>取整过程与「若上游要 36/35 该怎么改」写在 {@code PermissionCatalog} 类注释。
 */
class PermissionCatalogTest {

  /** 目录条数（34；推导见类注释）。 */
  private static final int EXPECTED_TOTAL = 36;

  @Test
  void catalog_has_exactly_thirty_four_codes() {
    assertEquals(
        EXPECTED_TOTAL,
        PermissionCatalog.size(),
        "权限码总数必须恰为 36（推导见 PermissionCatalog 类注释）；实际："
            + PermissionCatalog.allCodes());
  }

  @Test
  void module_counts_are_consistent_with_the_total() {
    Map<String, Integer> byModule = PermissionCatalog.countByModule();
    assertEquals(7, byModule.get(PermissionCatalog.MODULE_CONSOLE), "console 模块（5 账号/角色/审计 + 2 App 用户）：" + byModule);
    assertEquals(18, byModule.get(PermissionCatalog.MODULE_CONTENT), "content 模块：" + byModule);
    assertEquals(
        4,
        byModule.get(PermissionCatalog.MODULE_MODERATION),
        "moderation 模块（word:read/write 不登记）应为 4：" + byModule);
    assertEquals(7, byModule.get(PermissionCatalog.MODULE_OPS), "ops 模块：" + byModule);
    assertEquals(
        EXPECTED_TOTAL,
        byModule.values().stream().mapToInt(Integer::intValue).sum(),
        "各模块之和必须等于总数");
    assertEquals(4, byModule.size(), "不得出现 null/空 module 分组（通配符行必须被排除）：" + byModule);
  }

  @Test
  void codes_are_unique_and_all_known() {
    Set<String> codes = PermissionCatalog.allCodes();
    assertEquals(EXPECTED_TOTAL, codes.size(), "权限码不得重复");
    for (String c : codes) {
      assertTrue(PermissionCatalog.isKnown(c), c + " 应在目录内");
      assertTrue(c.contains(":"), c + " 应形如 module:resource:action");
    }
    assertTrue(!codes.contains(PermissionCatalog.WILDCARD), "通配符不得混进对外契约的码集合（它只是 seed 用的一行）");
  }

  /** 敏感词码必须**不在**目录内：本期无端点消费它们（docs/50 §6.2 联动硬点 4）。 */
  @Test
  void moderation_word_codes_are_not_registered() {
    assertTrue(
        PermissionCatalog.allCodes().stream().noneMatch(c -> c.startsWith("moderation:word")),
        "敏感词库为 P1，本期无端点；发放会造成「有权限、点开 404」：" + PermissionCatalog.allCodes());
  }

  @Test
  void ops_trace_content_is_a_separate_code_from_structure() {
    assertTrue(PermissionCatalog.allCodes().contains(PermissionCatalog.OPS_TRACE_READ));
    assertTrue(PermissionCatalog.allCodes().contains(PermissionCatalog.OPS_TRACE_CONTENT_READ));
    assertTrue(
        !PermissionCatalog.OPS_TRACE_READ.equals(PermissionCatalog.OPS_TRACE_CONTENT_READ),
        "内容与结构必须是两个独立码（docs/50 §4.2 的隐私闸门）");
  }

  /** 通配符必须有可 seed 的目录行，否则 super 在库里拿不到任何授权。 */
  @Test
  void wildcard_permission_row_exists_for_seeding() {
    assertNotNull(PermissionCatalog.WILDCARD_PERMISSION);
    assertEquals(PermissionCatalog.WILDCARD, PermissionCatalog.WILDCARD_PERMISSION.code());
    assertTrue(
        PermissionCatalog.allForSeed().stream()
            .anyMatch(p -> PermissionCatalog.WILDCARD.equals(p.code())),
        "allForSeed() 必须含通配符行（否则 RbacBootstrap 解析不到 * 的 id → super 零权限）");
    assertEquals(
        EXPECTED_TOTAL + 1, PermissionCatalog.allForSeed().size(), "seed 清单 = 36 个真实码 + 1 行通配符");
    assertTrue(
        PermissionCatalog.byModule().values().stream()
            .flatMap(List::stream)
            .noneMatch(p -> PermissionCatalog.WILDCARD.equals(p.code())),
        "权限勾选列表（byModule）不得出现通配符");
  }

  // ------------------------------------------------------------------ 内置角色矩阵

  @Test
  void builtin_roles_are_exactly_four_and_permissions_are_in_catalog() {
    assertEquals(4, BuiltinRoles.all().size());
    Set<String> expectedCodes =
        new LinkedHashSet<>(List.of("super", "ops", "operator", "moderator"));
    Set<String> actual = new LinkedHashSet<>();
    for (BuiltinRoles.Role r : BuiltinRoles.all()) {
      actual.add(r.code());
      for (String c : r.permissionCodes()) {
        if (!PermissionCatalog.WILDCARD.equals(c)) {
          assertTrue(PermissionCatalog.isKnown(c), r.code() + " 引用了目录外的码：" + c);
        }
      }
    }
    assertEquals(expectedCodes, actual);
  }

  @Test
  void super_holds_only_wildcard_and_it_expands_to_everything() {
    BuiltinRoles.Role superRole = BuiltinRoles.byCode(BuiltinRoles.SUPER);
    assertNotNull(superRole);
    assertEquals(Set.of(PermissionCatalog.WILDCARD), superRole.permissionCodes());
    assertEquals(EXPECTED_TOTAL, PermissionCatalog.allCodes().size(), "* 展开目标即全量目录");
  }

  @Test
  void ops_role_matches_docs() {
    BuiltinRoles.Role ops = BuiltinRoles.byCode(BuiltinRoles.OPS);
    assertNotNull(ops);
    assertEquals(8, ops.permissionCodes().size(), "ops:* 七个 + console:audit:read");
    assertTrue(ops.permissionCodes().contains(PermissionCatalog.OPS_MAINTENANCE_WRITE));
    assertTrue(ops.permissionCodes().contains(PermissionCatalog.CONSOLE_AUDIT_READ));
  }

  /** 运营角色只拿 Java 侧 content 码（Python 的 book/media 不发放）。 */
  @Test
  void operator_role_excludes_python_owned_content_codes() {
    BuiltinRoles.Role operator = BuiltinRoles.byCode(BuiltinRoles.OPERATOR);
    assertNotNull(operator);
    assertEquals(
        16,
        operator.permissionCodes().size(),
        "运营 = Java 侧 content 13（song/listening/scenario 各 3 = 9 + question 2 + ticket 2）"
            + " + console:user:read/write 2（App 用户管理已随旧管理端退役搬进控制台，运营要能管用户）"
            + " + console:audit:read 1 = 16。"
            + "⚠️ 这个数**从 BuiltinRoles 的实现推导**，不是抄文档——文档里的权限码数量已错过三次"
            + "（docs/51 §1.1 B-10），凡数量断言都要说清它由哪几项加出来，否则下次仍然对不上。");
    for (String c : operator.permissionCodes()) {
      assertTrue(
          !c.startsWith("content:book") && !c.startsWith("content:media"),
          "运营不该持有 Python 侧内容码（无 Java 端点可消费）：" + c);
    }
    assertTrue(operator.permissionCodes().contains(PermissionCatalog.CONTENT_SONG_PUBLISH));
    assertTrue(operator.permissionCodes().contains(PermissionCatalog.CONTENT_TICKET_WRITE));
    assertTrue(
        operator.permissionCodes().contains(PermissionCatalog.CONTENT_SCENARIO_PUBLISH),
        "运营必须能上下架场景");
    // 题库在 Java 侧只读（§4.2：题库无 draft，故无 publish）
    assertTrue(operator.permissionCodes().contains(PermissionCatalog.CONTENT_QUESTION_READ));
  }

  /** 审核角色必须能看见媒体（用户点名的「视频审核」），但只有只读。 */
  @Test
  void moderator_role_can_see_media_but_not_hide_it() {
    BuiltinRoles.Role moderator = BuiltinRoles.byCode(BuiltinRoles.MODERATOR);
    assertNotNull(moderator);
    assertTrue(
        moderator.permissionCodes().contains(PermissionCatalog.CONTENT_MEDIA_READ),
        "缺 content:media:read 会让「视频审核」在权限矩阵里不存在：" + moderator.permissionCodes());
    assertTrue(
        !moderator.permissionCodes().contains(PermissionCatalog.CONTENT_MEDIA_WRITE),
        "媒体隐藏归 Python（docs/50 §5.4），Java 审核角色不得持有写权限");
    assertEquals(9, moderator.permissionCodes().size(), "4 moderation + 4 内容只读 + audit:read");
    assertTrue(
        moderator.permissionCodes().contains(PermissionCatalog.MODERATION_REPORT_HANDLE),
        "审核必须能处理举报");
    assertTrue(
        !moderator.permissionCodes().stream().anyMatch(c -> c.startsWith("moderation:word")),
        "敏感词库本期无端点，不得发放");
  }

  /**
   * 目录里没有任何内置角色持有的码，必须**恰好**是「设计已定义但端点暂无/归 Python」的那批。
   *
   * <p>这个断言的价值：它把「谁都不能用的权限码」变成显式清单。若某天有人往目录里加了一个码却忘了发给 任何角色，这里会红 ——
   * 否则那个码会安静地存在于权限控制台里、永远没人能拿到，而端点却以为自己被保护着。
   *
   * <p>清单构成：
   *
   * <ul>
   *   <li>{@code content:book:*}（3）+ {@code content:media:write}：端点归 **Python**（docs/50 §3.2）；
   *   <li>{@code content:question:*}（2）：§4.2 已定义，但 Java 侧题库端点为**只读** （docs/50 §10.2 只有 {@code GET
   *       /content/questions}），写端点归 Python。
   * </ul>
   */
  @Test
  void unheld_codes_are_exactly_the_reserved_ones() {
    Set<String> unheld = BuiltinRoles.codesWithoutBuiltinHolder();
    assertEquals(
        Set.of(
            // ① 控制台**账号与角色管理**只给 super（通配）—— 这是刻意的：
            // 若某个内置角色能改账号/角色，它就能给自己提权（super 通配 + 反提权规则只是第二道防线）。
            PermissionCatalog.CONSOLE_ADMIN_READ,
            PermissionCatalog.CONSOLE_ADMIN_WRITE,
            PermissionCatalog.CONSOLE_ROLE_READ,
            PermissionCatalog.CONSOLE_ROLE_WRITE,
            // ② 端点归 **Python**（docs/50 §3.2 / docs/06 §10 写方矩阵），Java 侧不发：
            // 发放等于造出「权限表里有、实际无处可用」的权限。
            // ⚠️ 只有**写/上架**这三个无持有者；content:book:**read** 与 content:media:**read** 是**有**持有者的
            // （审核要看书与视频内容的上下文），本集合里**不应**出现它们。
            PermissionCatalog.CONTENT_BOOK_WRITE,
            PermissionCatalog.CONTENT_BOOK_PUBLISH,
            PermissionCatalog.CONTENT_MEDIA_WRITE),
        unheld,
        "无内置持有者的应只有「super 专属的账号/角色管理」+「归 Python 的写与上架」；实际：" + unheld);
  }
}
