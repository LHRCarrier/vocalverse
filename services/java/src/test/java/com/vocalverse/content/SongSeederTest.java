package com.vocalverse.content;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

/**
 * 曲目种子测试（M3 唱歌 P0 · D-G2；H2 + 真实 data/seed/songs.json）。
 *
 * <p>覆盖：播种字段契约（audio_url 共享卷路径/pitch_ref_status=missing/source=original）、 逐句 LRC（seq 重排 +
 * 时间戳）、幂等（二次跑不新增）、开关关闭不播种。 注：测试库 application-test.yml 默认 {@code vocalverse.song.seed=false}，
 * 本测试手动构造 Seeder 实例（不依赖启动顺序）。
 */
@SpringBootTest
@ActiveProfiles("test")
class SongSeederTest {

  @Autowired private SongRepository songs;
  @Autowired private LrcRepository lrcs;
  @Autowired private ObjectMapper mapper;

  private SongSeeder seeder(boolean enabled) {
    return new SongSeeder(songs, lrcs, mapper, enabled);
  }

  @Test
  void seeds_songs_with_lrc_and_is_idempotent() {
    long before = songs.count();
    seeder(true).run();
    long after = songs.count();
    assertTrue(after >= before + 3, "应播种 3 首演示曲目（实际 " + (after - before) + "）");

    SongEntity twinkle = songs.findByTitle("Twinkle Twinkle Little Star").orElseThrow();
    assertEquals("/data/audio/song_twinkle.wav", twinkle.getAudioUrl());
    assertEquals("missing", twinkle.getPitchRefStatus(), "就绪由 Python 提取后经内部 REST 翻转");
    assertEquals("original", twinkle.getSource(), "合成演奏=自研录音（旋律公有领域）");
    assertEquals("published", twinkle.getStatus());
    assertEquals(1, twinkle.getLevel());
    assertTrue(twinkle.getDurationS() != null && twinkle.getDurationS() > 10);

    List<LrcEntity> lines = lrcs.findBySongIdOrderBySeqAsc(twinkle.getId());
    assertEquals(6, lines.size(), "Twinkle 6 句");
    assertEquals(1, lines.get(0).getSeq());
    assertEquals(0, lines.get(0).getOffsetMs());
    assertTrue(lines.get(0).getEndOffsetMs() > 0);
    assertTrue(lines.get(1).getOffsetMs() >= lines.get(0).getEndOffsetMs(), "逐句时间轴单调");
    assertEquals(twinkle.getSource(), lines.get(0).getSource(), "逐句 source 继承 songs.source");

    // 幂等：二次跑不新增
    seeder(true).run();
    assertEquals(after, songs.count(), "按 title 查重（只增不改）");
  }

  @Test
  void disabled_seeder_does_nothing() {
    long before = songs.count();
    seeder(false).run();
    assertEquals(before, songs.count());
  }

  @Test
  void seed_json_is_present_and_wellformed() {
    // 素材物化脚本产物存在性（缺失时 SongSeeder 只告警不阻塞——此处显式断言便于排障）
    var path = java.nio.file.Path.of("..", "..", "data", "seed", "songs.json");
    assertTrue(java.nio.file.Files.exists(path), "先跑 scripts/setup-assets.py 生成 " + path);
  }
}
