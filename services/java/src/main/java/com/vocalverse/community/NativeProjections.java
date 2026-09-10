package com.vocalverse.community;

import java.sql.Timestamp;
import java.time.Instant;
import java.time.OffsetDateTime;

/**
 * 原生查询（`nativeQuery = true`）结果列的类型归一（2026-09-10 真 PG 联调踩坑落点）。
 *
 * <p>背景：同一份接口投影（Spring Data interface projection）在**两种方言下时间列类型不同**—— PostgreSQL 的 timestamptz 列给
 * {@link Instant}，H2（MODE=PostgreSQL）给 {@link OffsetDateTime}；Spring Data 不做跨类型 转换，写死任一类型都会在另一端报
 * `Cannot project java.time.X to java.time.Y`（H2 单测绿、真 PG 500 或反之）。
 *
 * <p>用法：投影接口把时间列声明为 {@link Object}，服务层用 {@link #toInstant(Object)} 归一后再进 DTO / 游标。 涉及点：J-03
 * 通知聚合（PostInteractionRepository）、私信会话/通知（DirectMessageRepository）。
 */
final class NativeProjections {

  private NativeProjections() {}

  /** 把原生投影的时间列归一为 {@link Instant}（null 透传）。 */
  static Instant toInstant(Object raw) {
    if (raw == null) {
      return null;
    }
    if (raw instanceof Instant i) {
      return i;
    }
    if (raw instanceof OffsetDateTime odt) {
      return odt.toInstant();
    }
    if (raw instanceof Timestamp ts) {
      return ts.toInstant();
    }
    throw new IllegalStateException("无法归一的时间列类型：" + raw.getClass().getName());
  }
}
