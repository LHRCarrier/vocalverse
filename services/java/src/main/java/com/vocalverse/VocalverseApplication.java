package com.vocalverse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * VocalVerse 管理端入口（薄管理端）。
 *
 * <p>职责边界（docs/06 第 1 章）：用户管理、场景/歌曲库 CRUD、工单、JWT 签发。 <b>严禁</b>进入语音/SSE/LLM 热路径；DDL 一律交给
 * Alembic（{@code ddl-auto=none}）。
 */
@SpringBootApplication
public class VocalverseApplication {

  public static void main(String[] args) {
    SpringApplication.run(VocalverseApplication.class, args);
  }
}
