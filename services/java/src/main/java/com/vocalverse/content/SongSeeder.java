package com.vocalverse.content;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * 演示曲目种子（M3 唱歌 P0 · D-G2 素材物化 · 2026-09-09）。
 *
 * <p>读 {@code data/seed/songs.json}（由 {@code scripts/setup-assets.py} 确定性生成： 旋律/歌词公有领域童谣，演奏为脚本合成音色
 * → {@code source=original}），播种 songs + lrc。 音频文件本体不入库（{@code data/audio/} gitignored），{@code
 * audio_url} 存共享卷路径， Python 侧 pyin 提取按 basename 归一读取（docs/06 §9.4 D1）。
 *
 * <p>单写方纪律：songs/lrc 属 Java 独占写（docs/10 §3），故种子在 Java 侧（与 CommunitySeeder/DemoSeeder 同型）；幂等策略 = 按
 * title 查重跳过（只增不改， 不覆盖管理员后续编辑）；{@code vocalverse.song.seed=false} 关闭（测试环境关闭）。
 *
 * <p>播种后 pitch_ref_status=missing → Python 离线提取扫描自动接手（→ building → ready）。
 */
@Component
@Order(3)
public class SongSeeder implements CommandLineRunner {

  private static final Logger logger = LoggerFactory.getLogger(SongSeeder.class);

  /** 本地：services/java（cwd）→ 仓库根；容器：/app（WORKDIR）→ /app/data/seed。 */
  private static final List<Path> CANDIDATES =
      List.of(
          Path.of("..", "..", "data", "seed", "songs.json"), Path.of("/app/data/seed/songs.json"));

  private final SongRepository songs;
  private final LrcRepository lrcs;
  private final ObjectMapper mapper;
  private final boolean seedEnabled;

  public SongSeeder(
      SongRepository songs,
      LrcRepository lrcs,
      ObjectMapper mapper,
      @Value("${vocalverse.song.seed:true}") boolean seedEnabled) {
    this.songs = songs;
    this.lrcs = lrcs;
    this.mapper = mapper;
    this.seedEnabled = seedEnabled;
  }

  @Override
  public void run(String... args) {
    if (!seedEnabled) {
      return;
    }
    Path seedFile = resolveSeedFile();
    if (seedFile == null) {
      logger.info("song seed 跳过：未找到 data/seed/songs.json（先跑 scripts/setup-assets.py）");
      return;
    }
    try {
      JsonNode root = mapper.readTree(Files.readString(seedFile));
      int inserted = 0;
      for (JsonNode item : root.path("songs")) {
        if (seedOne(item)) {
          inserted++;
        }
      }
      logger.info("song seed 完成：新增 {} 首（已存在则跳过）", inserted);
    } catch (IOException e) {
      logger.warn("song seed 读取失败（跳过，不阻塞启动）：{}", e.getMessage());
    }
  }

  private Path resolveSeedFile() {
    for (Path candidate : CANDIDATES) {
      if (Files.exists(candidate)) {
        return candidate;
      }
    }
    return null;
  }

  /** 单首播种：按 title 查重（只增不改）；返回是否新增。 */
  private boolean seedOne(JsonNode item) {
    String title = item.path("title").asText();
    Optional<SongEntity> exists = songs.findByTitle(title);
    if (exists.isPresent()) {
      return false;
    }
    Instant now = Instant.now();
    SongEntity song = new SongEntity();
    song.setTitle(title);
    song.setArtist(item.path("artist").asText(null));
    song.setLevel(item.path("level").asInt(1));
    song.setDurationS(item.hasNonNull("duration_s") ? item.get("duration_s").asLong() : null);
    song.setBpm(
        item.hasNonNull("bpm") ? java.math.BigDecimal.valueOf(item.get("bpm").asDouble()) : null);
    song.setMusicalKey(item.path("musicalKey").asText(null));
    song.setAudioUrl(item.path("audio_url").asText());
    song.setVocalRefUrl(item.path("vocal_ref_url").asText(null));
    song.setLrcUrl(item.path("lrc_url").asText(null));
    song.setCoverUrl(item.path("cover_url").asText(null));
    song.setInterestTags(item.path("interest_tags").asText("[]"));
    song.setSource(item.path("source").asText("original"));
    song.setStatus(item.path("status").asText("published"));
    song.setPitchRefStatus("missing"); // 就绪由 Python 提取后经内部 REST 翻转（D2）
    song.setCreatedAt(now);
    song.setUpdatedAt(now);
    SongEntity saved = songs.save(song);

    List<LrcEntity> lines = new ArrayList<>();
    int seq = 1;
    for (JsonNode line : item.path("lines")) {
      LrcEntity e = new LrcEntity();
      e.setSongId(saved.getId());
      e.setSeq(seq++);
      e.setOffsetMs(line.path("offset_ms").asLong());
      e.setEndOffsetMs(
          line.hasNonNull("end_offset_ms") ? line.get("end_offset_ms").asLong() : null);
      e.setLineText(line.path("text").asText());
      e.setSource(saved.getSource());
      e.setCreatedAt(now);
      lines.add(lrcs.save(e));
    }
    logger.info("song seed: {} 播种完成（{} 句）", title, lines.size());
    return true;
  }
}
