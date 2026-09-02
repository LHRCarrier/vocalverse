package com.vocalverse.controller;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.common.dto.PageView;
import com.vocalverse.ticket.TicketEntity;
import com.vocalverse.ticket.TicketRepository;
import com.vocalverse.ticket.TicketView;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 工单管理侧（docs/06 §9.6：处理中/已解决/关闭）。状态机前向流转 open → processing → resolved → closed（禁回退、closed
 * 终态）；处理人取当前 admin， resolved 时落 resolved_at。网关路径 /manage/api/v1/admin/tickets（ADMIN 守门）。
 */
@RestController
@RequestMapping("/api/v1/admin/tickets")
public class AdminTicketController {

  /** open→processing→resolved→closed（禁回退）。 */
  private static final Map<String, Integer> FLOW_ORDER =
      Map.of("open", 0, "processing", 1, "resolved", 2, "closed", 3);

  public record TicketPatch(
      @Pattern(regexp = "open|processing|resolved|closed") String status,
      @Size(max = 2000) String adminReply) {}

  private final TicketRepository tickets;

  public AdminTicketController(TicketRepository tickets) {
    this.tickets = tickets;
  }

  @GetMapping
  public Envelope<PageView<TicketView>> list(
      @RequestParam(defaultValue = "1") @Min(1) int page,
      @RequestParam(name = "page_size", defaultValue = "20") @Min(1) @Max(100) int pageSize,
      @RequestParam(required = false) @Pattern(regexp = "open|processing|resolved|closed")
          String status) {
    Page<TicketEntity> rows = tickets.search(status, PageRequest.of(page - 1, pageSize));
    return Envelope.ok(PageView.of(rows.map(TicketView::of)));
  }

  @PatchMapping("/{id}")
  public Envelope<TicketView> update(
      @PathVariable Long id,
      @RequestAttribute("userId") Long adminId,
      @Valid @RequestBody TicketPatch body) {
    TicketEntity e =
        tickets
            .findById(id)
            .orElseThrow(
                () -> new ResponseStatusException(HttpStatus.NOT_FOUND, "ticket not found"));
    if (body.status() != null && !body.status().equals(e.getStatus())) {
      int current = FLOW_ORDER.get(e.getStatus());
      int next = FLOW_ORDER.get(body.status());
      if (next <= current) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "invalid transition: " + e.getStatus() + " → " + body.status());
      }
      e.setStatus(body.status());
      if ("resolved".equals(body.status())) {
        e.setResolvedAt(Instant.now());
      }
    }
    if (body.adminReply() != null) {
      e.setAdminReply(body.adminReply());
      if (e.getAdminId() == null) {
        e.setAdminId(adminId); // 认领：处理人=当前 admin
      }
    }
    e.setUpdatedAt(Instant.now());
    return Envelope.ok(TicketView.of(tickets.save(e)));
  }
}
