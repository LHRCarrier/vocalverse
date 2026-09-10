package com.vocalverse.ticket;

import java.time.Instant;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * 工单状态机（docs/06 §9.6：open → processing → resolved → closed，禁回退，closed 终态）。
 *
 * <p>2026-09-10 从 {@code AdminTicketController.update} 原样抽出，供控制台端点 （{@code PATCH
 * /api/v1/console/content/tickets/{id}}）复用。随后旧管理端被**整体退役**， 所以本服务现在是全仓**唯一**的工单写路径 —— 两份实现漂移的风险消失了，
 * 但它也是唯一需要被测试覆盖的地方。
 *
 * <p>抽出时行为逐字保持：非法回退 → 400 + {@code ResponseStatusException}（既有 {@code GlobalExceptionHandler} 映射
 * 40001）；{@code resolved} 时落 {@code resolved_at}； 首次填 {@code admin_reply} 时把 {@code admin_id}
 * 认领为当前管理员。
 *
 * <h2>admin_id 装的是哪套身份（重要，别做错 join）</h2>
 *
 * <p>{@code tickets.admin_id} **无外键**。历史值与新值的归属不同：
 *
 * <ul>
 *   <li>旧值（退役前的 {@code AdminTicketController} 写入）→ App 侧 {@code users.id}；
 *   <li>新值（控制台端点写入）→ 控制台 {@code admin_users.id}（与 {@code users} 无任何关联，docs/50 §4.1）。
 * </ul>
 *
 * <p>本服务对 {@code adminId} 参数**不做任何来源假设**（调用方传什么就存什么）， 这是有意的：状态机是纯业务规则，身份来源是 HTTP 层的关注点。 「谁处理的」权威记录在
 * {@code admin_audit_logs}（含 {@code admin_username} 快照）， {@code admin_id} 仅用于列表展示。
 */
@Service
public class TicketWorkflowService {

  /** open→processing→resolved→closed（禁回退）。 */
  private static final Map<String, Integer> FLOW_ORDER =
      Map.of("open", 0, "processing", 1, "resolved", 2, "closed", 3);

  private final TicketRepository tickets;

  public TicketWorkflowService(TicketRepository tickets) {
    this.tickets = tickets;
  }

  @Transactional
  public TicketEntity update(Long id, Long adminId, String status, String adminReply) {
    TicketEntity e =
        tickets
            .findById(id)
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.NOT_FOUND, "ticket not found"));
    if (status != null && !status.equals(e.getStatus())) {
      Integer current = FLOW_ORDER.get(e.getStatus());
      Integer next = FLOW_ORDER.get(status);
      if (current == null || next == null || next <= current) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "invalid transition: " + e.getStatus() + " → " + status);
      }
      e.setStatus(status);
      if ("resolved".equals(status)) {
        e.setResolvedAt(Instant.now());
      }
    }
    if (adminReply != null) {
      e.setAdminReply(adminReply);
      if (e.getAdminId() == null) {
        e.setAdminId(adminId); // 认领：处理人=当前 admin
      }
    }
    e.setUpdatedAt(Instant.now());
    return tickets.save(e);
  }
}
