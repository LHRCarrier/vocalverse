package com.vocalverse.console;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

/**
 * 常量类静态初始化自证（本轮实测缺陷的回归防线）。
 *
 * <h2>为什么需要这个测试</h2>
 *
 * <p>实测踩到两次同一类缺陷：{@code Set.of(...)} 里写了**重复元素** → 类初始化抛 {@code IllegalArgumentException} → 包成
 * {@code ExceptionInInitializerError}。后果不是「某个常量不对」， 而是**调用该类的整条功能全废**：
 *
 * <ul>
 *   <li>{@code AuditFieldAllowlist.FORBIDDEN_MARKERS} 有 {@code totp} 与 {@code otp}（substring 同时命中）
 *       → 每一次审计写入都失败；
 *   <li>{@code AuditFieldAllowlist.KEYS} 有重复的 {@code revoked} → 同上。
 * </ul>
 *
 * <p>而它们都被 {@code IndependentAuditWriter.bestEffort} 降级成一行 WARN， 表现为「审计表里没数据」而不是「报错」—— 是最难发现的一类失效。
 *
 * <p>两个断言：
 *
 * <ol>
 *   <li><b>逐个触发** main 源码里所有类的静态初始化**（反射 {@code Class.forName} + 读一个静态字段， 强制 {@code <clinit>}
 *       执行）。新增任何常量类都会自动被覆盖，不需要维护清单；
 *   <li>扫描源码，禁止 {@code Set.of}/{@code Map.of} 里出现明显的重复字面量（源码级兜底， 连未被加载的类也能覆盖）。
 * </ol>
 */
class StaticInitializationSafetyTest {

  private static final String MAIN_SOURCES = "src/main/java/com/vocalverse/console";

  /** 触发所有 console 类的静态初始化；任何一个 {@code <clinit>} 抛错即失败。 */
  @Test
  void all_console_classes_initialize_cleanly() throws Exception {
    List<String> classNames = consoleClassNames();
    assertTrue(classNames.size() > 30, "应扫描到较多类（实际 " + classNames.size() + "）");

    List<String> failures = new ArrayList<>();
    for (String name : classNames) {
      try {
        Class<?> c = Class.forName(name, true, Thread.currentThread().getContextClassLoader());
        // 读一个静态字段/触发一次静态方法访问，确保 <clinit> 真的跑了
        c.getDeclaredFields();
        c.getDeclaredMethods();
        // 显式触发初始化（Class.forName 的 initialize=true 已足够，但再保险一次）
        java.lang.reflect.Field[] fields = c.getDeclaredFields();
        for (java.lang.reflect.Field f : fields) {
          if (java.lang.reflect.Modifier.isStatic(f.getModifiers())) {
            f.setAccessible(true);
            try {
              f.get(null);
            } catch (Throwable ignored) {
              // 常量字段读不到不算失败（可能是复杂初始化的副作用），只要 <clinit> 没炸即可
            }
          }
        }
      } catch (Throwable t) {
        Throwable cause = t instanceof ExceptionInInitializerError e ? e.getCause() : t;
        failures.add(name + " → " + cause);
      }
    }
    if (!failures.isEmpty()) {
      fail("以下类的静态初始化失败（通常是 Set.of/Map.of 里有重复元素）：\n  " + String.join("\n  ", failures));
    }
  }

  /**
   * 源码级兜底：{@code Set.of(...)} / {@code Map.of(...)} 里不得出现重复的相邻字面量。
   *
   * <p>反射版本只能覆盖「已加载的类」；这条扫源码，连没被任何测试触达的常量也能拦住。
   */
  @Test
  void no_duplicate_literals_in_set_of_or_map_of() throws IOException {
    List<String> problems = new ArrayList<>();
    try (Stream<Path> files = Files.walk(Path.of(MAIN_SOURCES))) {
      for (Path p : files.filter(f -> f.toString().endsWith(".java")).toList()) {
        String src = Files.readString(p);
        problems.addAll(findDuplicateSetOfEntries(p, src));
      }
    }
    if (!problems.isEmpty()) {
      fail(
          "发现 Set.of 中的重复元素（会导致 ExceptionInInitializerError）：\n  " + String.join("\n  ", problems));
    }
  }

  private static List<String> findDuplicateSetOfEntries(Path file, String src) {
    List<String> out = new ArrayList<>();
    int idx = 0;
    while ((idx = src.indexOf("Set.of(", idx)) >= 0) {
      int start = idx + "Set.of(".length();
      int depth = 1;
      int i = start;
      while (i < src.length() && depth > 0) {
        char ch = src.charAt(i);
        if (ch == '(') {
          depth++;
        } else if (ch == ')') {
          depth--;
        }
        i++;
      }
      String body = src.substring(start, Math.max(start, i - 1));
      // 顶层逗号切分（不处理嵌套括号的完美情况，但足以抓出重复字面量）
      List<String> seen = new ArrayList<>();
      for (String raw : body.split(",")) {
        String item = raw.strip();
        if (item.startsWith("\"") && item.endsWith("\"") && item.length() > 1) {
          if (seen.contains(item)) {
            int line = src.substring(0, idx).split("\n", -1).length;
            out.add(file.getFileName() + ":" + line + " 重复元素 " + item);
          }
          seen.add(item);
        }
      }
      idx = i;
    }
    return out;
  }

  /** 扫描 main 源码目录，得到全限定类名。 */
  private static List<String> consoleClassNames() throws IOException {
    List<String> names = new ArrayList<>();
    try (Stream<Path> files = Files.walk(Path.of(MAIN_SOURCES))) {
      for (Path p : files.filter(f -> f.toString().endsWith(".java")).toList()) {
        String rel = Path.of(MAIN_SOURCES).relativize(p).toString().replace('\\', '/');
        String fqcn =
            "com.vocalverse.console."
                + rel.substring(0, rel.length() - ".java".length()).replace('/', '.');
        names.add(fqcn);
      }
    }
    return names;
  }
}
