package com.vocalverse.contract;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Java 契约快照对账（docs/06 §7，2026-08-31）：springdoc 实时渲染的 /v3/api-docs 必须与入库
 * 快照（apps/web/src/api/specs/java-openapi.json）一致，防"改了接口不刷新契约"。
 *
 * <p>刷新方式：本地起 Java 后跑 {@code scripts\refresh-openapi.ps1}；或临时设环境变量 {@code
 * CONTRACT_SNAPSHOT_GENERATE=1} 跑本测试重写快照（仅限本地，勿带上 CI）。
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ContractSnapshotTest {

  /** 相对本模块 basedir（surefire fork 的 cwd）。 */
  private static final Path SNAPSHOT = Path.of("../../apps/web/src/api/specs/java-openapi.json");

  @Autowired private MockMvc mockMvc;

  @Test
  void apiDocumentMatchesCommittedSnapshot() throws Exception {
    String liveJson =
        mockMvc.perform(get("/v3/api-docs")).andReturn().getResponse().getContentAsString();
    ObjectMapper mapper = new ObjectMapper();
    JsonNode live = normalize(mapper.readTree(liveJson));

    if (System.getenv("CONTRACT_SNAPSHOT_GENERATE") != null) {
      Files.createDirectories(SNAPSHOT.getParent());
      Files.writeString(SNAPSHOT, mapper.writerWithDefaultPrettyPrinter().writeValueAsString(live));
      return;
    }

    assertTrue(Files.exists(SNAPSHOT), "契约快照缺失：" + SNAPSHOT.toAbsolutePath());
    JsonNode committed = normalize(mapper.readTree(Files.readString(SNAPSHOT)));
    assertEquals(committed, live, "Java OpenAPI 契约与快照不一致：接口已改但未刷新快照（scripts/refresh-openapi.ps1）");
  }

  /** 去掉 servers（测试上下文 base url 随环境变化，不纳入对账）。 */
  private static JsonNode normalize(JsonNode node) {
    ((ObjectNode) node).remove("servers");
    return node;
  }
}
