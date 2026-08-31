package com.vocalverse.common.trace;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class RequestIdFilterTest {

  @Autowired private MockMvc mockMvc;

  @Test
  void propagatesProvidedRequestId() throws Exception {
    mockMvc
        .perform(get("/api/v1/ping").header(RequestIdFilter.HEADER, "trace-test-01"))
        .andExpect(status().isOk())
        .andExpect(header().string(RequestIdFilter.HEADER, "trace-test-01"));
  }

  @Test
  void generatesRequestIdWhenMissing() throws Exception {
    mockMvc
        .perform(get("/api/v1/ping"))
        .andExpect(status().isOk())
        .andExpect(header().exists(RequestIdFilter.HEADER));
  }
}
