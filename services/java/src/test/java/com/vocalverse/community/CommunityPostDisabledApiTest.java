package com.vocalverse.community;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/** 发帖开关关闭（VOICEVERSE_COMMUNITY_POST_ENABLED=false）→ POST /posts 40302（docs/37 A-15）。 */
@SpringBootTest(properties = "vocalverse.community.post-enabled=false")
class CommunityPostDisabledApiTest extends AbstractAdminApiTest {

  @Test
  void createPost_disabled_403WithCode() throws Exception {
    String token = registerUser("comm_off");
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", "Bearer " + token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"title\":\"T\",\"body\":\"Hello\",\"kind\":\"article\",\"domain\":\"news\"}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode root =
        objectMapper.readTree(r.getResponse().getContentAsString(StandardCharsets.UTF_8));
    assertEquals(40302, root.path("code").asInt());
    assertEquals(403, r.getResponse().getStatus());
    // feed 只读不受开关影响（仍 200）
    MvcResult feed =
        mockMvc
            .perform(get("/api/v1/community/posts").header("Authorization", "Bearer " + token))
            .andReturn();
    assertEquals(200, feed.getResponse().getStatus());
    assertEquals(
        0,
        objectMapper
            .readTree(feed.getResponse().getContentAsString(StandardCharsets.UTF_8))
            .path("code")
            .asInt());
  }
}
