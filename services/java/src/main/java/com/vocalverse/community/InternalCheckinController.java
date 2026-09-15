package com.vocalverse.community;

import com.vocalverse.common.dto.Envelope;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 打卡卡物化内部委托（docs/21 §4 第二条：Python → Java，**严禁经网关**；ServiceTokenFilter 匹配 /internal/** 校验
 * Authorization: Bearer &lt;service-token&gt;）。
 *
 * <p>契约：请求 camelCase 全键名（Jackson 默认；snake_case 会反序列化为 null——P0-6 教训）； 幂等键 (userId,
 * practiceDate)，重试无害（practice_count 递增语义以 Java 侧为准）。
 */
@RestController
@RequestMapping("/internal/checkin")
public class InternalCheckinController {

  public record Snapshot(
      Double overall, Double pron, Double gram, Double fluency, Integer turns, Integer durationS) {}

  public record CheckinRequest(
      @NotNull Long userId,
      @NotBlank String practiceDate,
      Long sessionId,
      @NotNull @Valid Snapshot snapshot) {}

  private final CommunityService service;

  public InternalCheckinController(CommunityService service) {
    this.service = service;
  }

  @PostMapping
  public Envelope<Long> checkin(@Valid @RequestBody CheckinRequest body) {
    Snapshot s = body.snapshot();
    long postId =
        service.upsertCheckin(
            body.userId(),
            body.practiceDate(),
            body.sessionId(),
            s.overall(),
            s.pron(),
            s.gram(),
            s.fluency(),
            s.turns(),
            s.durationS());
    return Envelope.ok(postId);
  }
}
