package com.vocalverse.health;

import com.vocalverse.common.dto.Envelope;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 骨架探活接口（与 Spring Actuator /actuator/health 并存）。返回统一 envelope（docs/06 §7）。 */
@RestController
@RequestMapping("/api/v1")
public class PingController {

  /** 探测数据（前端类型由契约生成，见 apps/web/src/api/generated/java-api.d.ts）。 */
  public record PingData(String status, String service) {}

  @GetMapping("/ping")
  public Envelope<PingData> ping() {
    return Envelope.ok(new PingData("alive", "vocalverse-java-api"));
  }
}
