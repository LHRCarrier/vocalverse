package com.vocalverse.content.controller;

import com.vocalverse.common.dto.Envelope;
import com.vocalverse.content.SongEntity;
import com.vocalverse.content.SongRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * 参考旋律状态内部委托（docs/21 §4 第三条 · 2026-09-09 唱歌 P0 D2 拍板）。
 *
 * <p>Python 离线提取任务完成 → 本端点翻转 songs.pitch_ref_status（songs 属 Java 独占写 + M-1 DB 角色只授 vv_python
 * SELECT——Python 物理无法 UPDATE，故状态翻转唯一通道 = 本内部 REST 委托）。
 *
 * <p>契约：请求体 camelCase 全键名（Jackson 默认；snake_case 反序列化为 null → @Valid 400， P0-6
 * 教训）；幂等（同值重复投递无害，Python 扫描补偿可放心重发）；禁止经网关（R-12）。
 */
@RestController
@RequestMapping("/internal/song")
public class InternalSongStatusController {

  public record PitchStatusRequest(
      @NotNull Long songId,
      @NotBlank @Pattern(regexp = "missing|building|ready|invalid") String status,
      @Size(max = 16) String version) {}

  private final SongRepository songs;

  public InternalSongStatusController(SongRepository songs) {
    this.songs = songs;
  }

  @PostMapping("/{songId}/pitch-status")
  public Envelope<Long> setPitchStatus(
      @PathVariable Long songId, @Valid @RequestBody PitchStatusRequest body) {
    SongEntity song =
        songs
            .findById(songId)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "song not found"));
    song.setPitchRefStatus(body.status());
    song.setUpdatedAt(Instant.now());
    // version 目前不落 songs（无列）；提取世代由 song_pitch_refs.version 承载（docs/10 迁移 0010）
    songs.save(song);
    return Envelope.ok(songId);
  }
}
