package com.vocalverse.console.rbac;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import org.junit.jupiter.api.Test;

/**
 * 首个管理员 bootstrap 的**弱口令拒绝**逻辑（docs/50 §8）。
 *
 * <p>这里只测纯函数 {@link ConsoleAdminBootstrap#weakPasswordReason}：Runner 的完整行为依赖
 * 「表为空」这一一次性前提，跨测试类不可重复（第一个类跑完表就非空了）， 所以端到端断言不可靠。弱口令判定是其中最要紧、也最容易写错的一条，单独钉死。
 */
class ConsoleAdminBootstrapTest {

  @Test
  void accepts_reasonably_strong_password() {
    assertEquals(null, ConsoleAdminBootstrap.weakPasswordReason("ops-admin", "Str0ng-Console-Pw!"));
    assertEquals(
        null, ConsoleAdminBootstrap.weakPasswordReason("ops-admin", "a-very-long-passphrase"));
  }

  @Test
  void rejects_short_password() {
    String reason = ConsoleAdminBootstrap.weakPasswordReason("ops-admin", "short1!");
    assertNotNull(reason);
    assertTrue(reason.contains("10"), "应说明长度下限：" + reason);
  }

  @Test
  void rejects_known_weak_passwords_even_when_long_enough() {
    for (String weak :
        new String[] {"password123", "changeme123", "vocalverse", "administrator", "qwertyuiop"}) {
      String reason = ConsoleAdminBootstrap.weakPasswordReason("ops-admin", weak);
      assertNotNull(reason, weak + " 必须被拒（长度够但众所周知）");
      assertTrue(reason.contains("弱口令"), weak + " 的拒绝原因应指明弱口令：" + reason);
    }
  }

  @Test
  void rejects_password_equal_to_username() {
    String reason = ConsoleAdminBootstrap.weakPasswordReason("longusername", "longusername");
    assertNotNull(reason);
    assertTrue(reason.contains("用户名"), reason);
  }

  @Test
  void rejects_case_insensitive_username_match() {
    assertNotNull(ConsoleAdminBootstrap.weakPasswordReason("LongUserName", "longusername"));
  }

  /** 弱口令清单里绝不该出现「默认管理员口令」这类会被顺手套用的值。 */
  @Test
  void weak_list_contains_no_default_admin_credentials_that_might_be_reused() {
    assertFalse(
        ConsoleAdminBootstrap.weakPasswordReason("x", "console-fixture-pw-1") != null,
        "测试夹具口令本身应是强口令（避免夹具成为事实上的默认口令）");
    Set<String> shouldNotAccept = Set.of("admin", "admin123", "root", "123456");
    for (String s : shouldNotAccept) {
      assertNotNull(ConsoleAdminBootstrap.weakPasswordReason("someone", s), s + " 必须被拒（长度不足或过于常见）");
    }
  }
}
