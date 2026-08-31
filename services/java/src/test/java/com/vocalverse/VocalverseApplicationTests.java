package com.vocalverse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

/** M1 骨架冒烟：上下文加载（H2 内存库，CI 无需 Docker）。 */
@SpringBootTest
@ActiveProfiles("test")
class VocalverseApplicationTests {

  @Test
  void contextLoads() {}
}
