package com.vocalverse.ticket;

import java.time.Instant;

/** 工单视图（用户侧与管理侧共用）。 */
public record TicketView(
    Long id,
    Long userId,
    String kind,
    String targetType,
    Long targetId,
    String title,
    String content,
    String status,
    Long adminId,
    String adminReply,
    Instant resolvedAt,
    Instant createdAt,
    Instant updatedAt) {

  public static TicketView of(TicketEntity e) {
    return new TicketView(
        e.getId(),
        e.getUserId(),
        e.getKind(),
        e.getTargetType(),
        e.getTargetId(),
        e.getTitle(),
        e.getContent(),
        e.getStatus(),
        e.getAdminId(),
        e.getAdminReply(),
        e.getResolvedAt(),
        e.getCreatedAt(),
        e.getUpdatedAt());
  }
}
