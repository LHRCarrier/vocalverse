package com.vocalverse.console.auth;

import java.util.Set;

/**
 * 控制台请求的登录主体（docs/50 §4.1）。
 *
 * <p>刻意做成不可变 record 而非复用 {@code Spring Security Authentication}：controller 与审计服务都需要 「adminUserId +
 * username + roleCode + perms」这四项，且 {@code perms} 是 JWT 内快照 （docs/50 §4.1：perms 进 JWT 换读取性能，代价是最长
 * 15 分钟权限滞后，由 token_epoch 补偿）。 直接携带快照，避免每次审计都回查权限表。
 */
public record ConsolePrincipal(
    Long adminUserId, String username, String roleCode, Set<String> permissions, Long sessionId) {

  /** 校验入参（过滤器构造时用；空白串一律视为非法，避免「空主体」被当登录态）。 */
  public ConsolePrincipal {
    if (adminUserId == null) {
      throw new IllegalArgumentException("adminUserId 不能为空");
    }
    permissions = permissions == null ? Set.of() : Set.copyOf(permissions);
  }

  public boolean has(String code) {
    return permissions.contains(code);
  }
}
