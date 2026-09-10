package com.vocalverse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * VocalVerse 管理端入口（薄管理端）。
 *
 * <p>职责边界（docs/06 第 1 章）：用户管理、场景/歌曲库 CRUD、工单、JWT 签发、社区内容 C 端（含 <b>社区域单向 SSE 推送</b>，2026-09-10 收窄登记
 * · docs/49 §3.3）。<b>严禁</b>进入语音/LLM 热路径（ASR/评分/TTS/LLM 及其 SSE）； DDL 一律交给 Alembic（{@code
 * ddl-auto=none}）。
 *
 * <p>{@code @EnableScheduling}：私信 SSE 心跳（{@link com.vocalverse.community.DmHeartbeat}）需要调度支持；此前全仓 无
 * {@code @Scheduled} 使用点，故在此显式开启（2026-09-10，切换点唯一）。
 *
 * <p>exclude UserDetailsServiceAutoConfiguration：本项目登录为自定义 JWT 过滤器 + BCrypt（AuthController）， 从不创建
 * {@code UserDetailsService} 实例；不排除它会在启动日志里兜底生成随机密码并打 「Using generated security
 * password」WARN（误导排查），且默认 InMemoryUserDetailsManager 无任何作用。
 */
@SpringBootApplication(exclude = UserDetailsServiceAutoConfiguration.class)
@EnableScheduling
public class VocalverseApplication {

  public static void main(String[] args) {
    SpringApplication.run(VocalverseApplication.class, args);
  }
}
