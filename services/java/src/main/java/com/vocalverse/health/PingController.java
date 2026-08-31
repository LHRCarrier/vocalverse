package com.vocalverse.health;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 骨架探活接口（与 Spring Actuator /actuator/health 并存）。 */
@RestController
@RequestMapping("/api/v1")
public class PingController {

  @GetMapping("/ping")
  public Map<String, String> ping() {
    return Map.of("service", "vocalverse-java-api", "status", "alive");
  }
}
