package com.vocalverse.common.dto;

/**
 * 统一响应 envelope（docs/06 §7）：{code, message, data}，成功 code=0。
 *
 * <p>前端类型由契约生成（apps/web/src/api/generated/java-api.d.ts）——Java 侧任何接口 返回必须经本类包装，不得裸返回对象（2026-09-01 修
 * M1 遗留：ping 裸返回导致前端误判）。
 */
public record Envelope<T>(int code, String message, T data) {

  public static <T> Envelope<T> ok(T data) {
    return new Envelope<>(0, "ok", data);
  }

  public static <T> Envelope<T> error(int code, String message) {
    return new Envelope<>(code, message, null);
  }
}
