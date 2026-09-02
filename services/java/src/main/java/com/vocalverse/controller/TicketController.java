package com.vocalverse.controller;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.ticket.TicketEntity;
import com.vocalverse.ticket.TicketRepository;
import com.vocalverse.ticket.TicketView;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 工单用户侧（docs/06 §9.6：用户提交反馈/报错/纠误 + 查看自己工单状态）。网关路径
 * /manage/api/v1/tickets（anyRequest().authenticated()，无需 admin）。
 */
@RestController
@RequestMapping("/api/v1/tickets")
public class TicketController {

  public record CreateTicket(
      @NotBlank @Pattern(regexp = "feedback|bug|content_correction") String kind,
      @Pattern(regexp = "scene|song|attempt|none") String targetType,
      Long targetId,
      @Size(max = 128) String title,
      @NotBlank @Size(max = 5000) String content) {}

  private final TicketRepository tickets;

  public TicketController(TicketRepository tickets) {
    this.tickets = tickets;
  }

  @PostMapping
  public Envelope<TicketView> create(
      @RequestAttribute("userId") Long userId, @Valid @RequestBody CreateTicket body) {
    Instant now = Instant.now();
    TicketEntity e = new TicketEntity();
    e.setUserId(userId);
    e.setKind(body.kind());
    e.setTargetType(body.targetType());
    e.setTargetId(body.targetId());
    e.setTitle(body.title());
    e.setContent(body.content());
    e.setStatus("open");
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return Envelope.ok(TicketView.of(tickets.save(e)));
  }

  @GetMapping("/mine")
  public Envelope<List<TicketView>> mine(@RequestAttribute("userId") Long userId) {
    return Envelope.ok(
        tickets.findByUserIdOrderByIdDesc(userId).stream().map(TicketView::of).toList());
  }
}
