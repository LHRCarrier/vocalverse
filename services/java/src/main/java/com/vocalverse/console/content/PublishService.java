package com.vocalverse.console.content;

import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.content.ListeningMaterialEntity;
import com.vocalverse.content.ListeningMaterialRepository;
import com.vocalverse.content.LrcEntity;
import com.vocalverse.content.LrcRepository;
import com.vocalverse.content.ScenarioEntity;
import com.vocalverse.content.ScenarioRepository;
import com.vocalverse.content.SongEntity;
import com.vocalverse.content.SongRepository;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 上架前置校验 + 上下架（docs/50 §6.1）。
 *
 * <h2>校验规则与列的存在性（逐条核实；不发明不存在的列）</h2>
 *
 * <p>docs/50 §6.1 给了 5 条规则。写代码前逐条对照了真实实体，<b>发现 3 处与真实 schema 不符</b>， 处理方式见下：
 *
 * <table border="1">
 *   <tr><th>文档规则</th><th>真实列 / 数据</th><th>本实现</th></tr>
 *   <tr><td>歌曲：必须有 {@code lrc} 行（≥1）且 {@code audio_url}/{@code ref_melody} 至少一个非空</td>
 *       <td>{@code songs} **没有 {@code ref_melody} 列**。真实列：{@code audio_url}（varchar **NOT NULL**
 *           → 「非空」检查恒真，是空校验）、{@code pitch_ref_status}
 *           ∈ {@code missing|building|ready|invalid}；参考旋律在**独立的 {@code song_pitch_refs} 表**，
 *           按 {@code lrc_id} 挂、由 Python 离线任务写</td>
 *       <td><b>偏离并上报</b>：改为「{@code lrc} 行 ≥1 且 {@code pitch_ref_status='ready'}」。
 *           为什么不用 {@code audio_url}：该列 NOT NULL，检查它等于没检查（写成校验会给人「音频已就位」的
 *           错觉）；而 {@code pitch_ref_status='ready'} 恰好是「参考旋律已提取完成」的**真实可读**信号，
 *           也正是跟唱打分的前置条件（{@code SongEntity} 注释：status != ready 返回「生成中」）。
 *           {@code audio_url} 仍做一道「长度 > 0」的兜底（防人为写入空串），但不再声称这是音频校验</td></tr>
 *   <tr><td>听力素材：{@code audio_url} + {@code transcript} 非空</td>
 *       <td>{@code audio_url} 是 varchar **NOT NULL**（同样恒真）；{@code transcript} 可为 NULL ✔</td>
 *       <td>{@code transcript} 非空为**真校验**（保留）；{@code audio_url} 只做非空串兜底并注释说明
 *           「该列 NOT NULL，此处仅防空串」——不假装它是一道有意义的闸门</td></tr>
 *   <tr><td>场景：{@code opening_line} + 目标语料（语言点）≥3 条</td>
 *       <td>{@code opening_line} 存在 ✔；「语言点」**没有独立表/集列**，只有 {@code target_corpus}
 *           一个 text 列。**权威解析格式**：每行 {@code English phrase|中文释义}
 *           （{@code app/practice/corpus.py} 的 {@code parse_target_corpus}：
 *           {@code for line in raw.splitlines()} + {@code if "|" in line: phrase, gloss = line.split("|", 1)}），
 *           实际种子数据 {@code app/db/seed_recommend.py} 也是这个格式</td>
 *       <td>{@code opening_line} 非空（阻断）+ {@code target_corpus} 中**含 {@code |} 的语料行 ≥3**
 *           （阻断）。按 {@code |} 计数而不是按行计数：先前的「按换行/分号切分」会与 Python 的解析口径
 *           不一致（一行里塞多个分号会被算成多条，而 Python 只认 {@code |}）—— 校验器与消费者必须同口径</td></tr>
 *   <tr><td>书籍：{@code book_chapters} ≥1 章且每章 {@code status='published'}</td>
 *       <td>{@code books}/{@code book_chapters} **归 Python 写**（docs/50 §5.4），
 *           且 {@code book_chapters.status} 目前在 Java 侧**没有任何读取方**</td>
 *       <td><b>不在 Java 实现</b>：Java 读 Python 的表会破坏 docs/06 §10 写方矩阵（§3.2 明确禁止）。
 *           Java 侧不提供书籍端点，避免造出一个「看起来能用、实际读不到数据」的上架接口</td></tr>
 *   <tr><td>媒体：{@code status='ready'} 才允许被引用</td>
 *       <td>{@code media_assets} 归 Python 写（同上）</td>
 *       <td>同上，不在 Java 实现（媒体处置走 Python 的「媒体库」端点）</td></tr>
 * </table>
 *
 * <p>失败形态：46011 + {@code data.violations[]}，每项 {@code {field, code, message}} —— 字段级原因，
 * 让运营一次看到「缺什么」而不是逐个试（docs/50 §6.1 尾注）。
 *
 * <p>校验放在**服务层**而非 controller（docs/50 §6.1 明确要求）：这样控制台端点、将来的批量上架、 Python 侧内部调用可以共用同一套规则。
 */
@Service
public class PublishService {

  /** 一种内容域的取值（docs/50 §6.1 语义拍板：draft/published/archived）。 */
  public static final String STATUS_DRAFT = "draft";

  public static final String STATUS_PUBLISHED = "published";
  public static final String STATUS_ARCHIVED = "archived";

  public static final String DOMAIN_SONG = "song";
  public static final String DOMAIN_LISTENING = "listening";
  public static final String DOMAIN_SCENARIO = "scenario";

  /** 字段级违规项（docs/50 §10.4 46011 {@code data.violations[]}）。 */
  public record Violation(String field, String code, String message) {}

  private final SongRepository songs;
  private final LrcRepository lrcs;
  private final ListeningMaterialRepository materials;
  private final ScenarioRepository scenarios;

  public PublishService(
      SongRepository songs,
      LrcRepository lrcs,
      ListeningMaterialRepository materials,
      ScenarioRepository scenarios) {
    this.songs = songs;
    this.lrcs = lrcs;
    this.materials = materials;
    this.scenarios = scenarios;
  }

  // ------------------------------------------------------------------ 上架

  /**
   * 变更内容域 status（docs/50 §6.1）。
   *
   * <p>仅 {@code published} 触发前置校验：{@code draft}/{@code archived} 是「撤回」方向， 卡校验会让运营连下架都做不到（下架永远该是允许的
   * —— 它是安全动作）。
   */
  @Transactional
  public PublishResult publish(String domain, Long id, String status) {
    String next = requireStatus(status);
    List<Violation> violations = new ArrayList<>();
    String prev;
    switch (domain) {
      case DOMAIN_SONG -> {
        SongEntity e =
            songs
                .findById(id)
                .orElseThrow(
                    () -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "歌曲不存在"));
        prev = e.getStatus();
        if (STATUS_PUBLISHED.equals(next)) {
          violations.addAll(validateSong(id, e));
        }
        if (violations.isEmpty()) {
          e.setStatus(next);
          e.setUpdatedAt(Instant.now());
          songs.save(e);
        }
      }
      case DOMAIN_LISTENING -> {
        ListeningMaterialEntity e =
            materials
                .findById(id)
                .orElseThrow(
                    () -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "听力素材不存在"));
        prev = e.getStatus();
        if (STATUS_PUBLISHED.equals(next)) {
          violations.addAll(validateMaterial(e));
        }
        if (violations.isEmpty()) {
          e.setStatus(next);
          e.setUpdatedAt(Instant.now());
          materials.save(e);
        }
      }
      case DOMAIN_SCENARIO -> {
        ScenarioEntity e =
            scenarios
                .findById(id)
                .orElseThrow(
                    () -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "场景不存在"));
        prev = e.getStatus();
        if (STATUS_PUBLISHED.equals(next)) {
          violations.addAll(validateScenario(e));
        }
        if (violations.isEmpty()) {
          e.setStatus(next);
          e.setUpdatedAt(Instant.now());
          scenarios.save(e);
        }
      }
      default ->
          throw ConsoleException.of(
              ConsoleErrorCodes.INVALID_PARAM, "内容域仅支持 song|listening|scenario");
    }

    if (!violations.isEmpty()) {
      throw new ConsoleException(
          ConsoleErrorCodes.PUBLISH_VALIDATION_FAILED,
          "上架校验失败：" + violations.size() + " 项不满足",
          ConsoleErrorCodes.status(ConsoleErrorCodes.PUBLISH_VALIDATION_FAILED),
          Map.of(
              "violations",
              serializeViolations(violations),
              "prevStatus",
              prev,
              "nextStatus",
              next));
    }
    return new PublishResult(domain, id, prev, next);
  }

  public record PublishResult(String domain, Long id, String prevStatus, String nextStatus) {}

  // ------------------------------------------------------------------ 规则

  /**
   * 歌曲上架：{@code lrc} 行 ≥1 + {@code pitch_ref_status='ready'}（见类注释的 {@code ref_melody} 偏离说明）。
   *
   * <p>{@code audio_url} 只做「非空串」兜底 —— 该列在 Alembic 侧是 {@code NOT NULL}， 检查「非 NULL」是恒真的，写进 violations
   * 只会给人「音频已校验」的错觉。
   */
  private List<Violation> validateSong(Long songId, SongEntity e) {
    List<Violation> out = new ArrayList<>();
    List<LrcEntity> lrcRows = lrcs.findBySongIdOrderBySeqAsc(songId);
    if (lrcRows.isEmpty()) {
      out.add(new Violation("lrc", "lrc_missing", "歌曲必须至少有 1 段 LRC 歌词（逐句评分依赖 LRC，docs/50 §6.1-1）"));
    }
    // 参考旋律就绪是跟唱打分的前置条件；song_pitch_refs 归 Python 写，Java 只能读这个状态位
    if (!"ready".equals(e.getPitchRefStatus())) {
      out.add(
          new Violation(
              "pitchRefStatus",
              "pitch_ref_not_ready",
              "参考旋律未就绪（pitch_ref_status="
                  + (e.getPitchRefStatus() == null ? "null" : e.getPitchRefStatus())
                  + "，需为 ready）：请先完成 LRC 并等待离线旋律提取任务"));
    }
    // 兜底：列为 NOT NULL，但空串在业务上等同「无音频」
    if (e.getAudioUrl() == null || e.getAudioUrl().isBlank()) {
      out.add(new Violation("audioUrl", "required", "歌曲 audioUrl 为空串（该列 NOT NULL，此处防脏数据）"));
    }
    return out;
  }

  /**
   * 听力素材上架：{@code transcript} 非空（docs/50 §6.1-2）。
   *
   * <p>{@code audio_url} 是 {@code NOT NULL} 列，同样只做空串兜底（见类注释）。
   */
  private List<Violation> validateMaterial(ListeningMaterialEntity e) {
    List<Violation> out = new ArrayList<>();
    if (isBlank(e.getTranscript())) {
      out.add(new Violation("transcript", "required", "听力素材必须填写 transcript（无文本无法做听力训练）"));
    }
    if (e.getAudioUrl() == null || e.getAudioUrl().isBlank()) {
      out.add(new Violation("audioUrl", "required", "听力素材 audioUrl 为空串（该列 NOT NULL，此处防脏数据）"));
    }
    return out;
  }

  /**
   * 场景上架：{@code opening_line} 非空 + 目标语料 ≥3 条（docs/50 §6.1-3）。
   *
   * <p>「≥3 条」的载体是 {@code scenarios.target_corpus}（单个 text 列，库里无独立语言点表）， 按**权威格式** {@code
   * English|中文} 逐行计数 —— 与 {@code app/practice/corpus.py} 的解析口径一致。
   */
  private List<Violation> validateScenario(ScenarioEntity e) {
    List<Violation> out = new ArrayList<>();
    if (isBlank(e.getOpeningLine())) {
      out.add(new Violation("openingLine", "required", "场景必须填写开场白 openingLine"));
    }
    int corpusItems = countCorpusItems(e.getTargetCorpus());
    if (corpusItems < 3) {
      out.add(
          new Violation(
              "targetCorpus",
              "too_few_items",
              "目标语料至少 3 条语言点（每行一条，格式 `English phrase|中文释义`，与 Python 解析口径一致），当前 "
                  + corpusItems
                  + " 条"));
    }
    return out;
  }

  /**
   * 目标语料条目数：按 {@code app/practice/corpus.py} 的权威格式逐行计数 —— 只统计**含 {@code |} 且 {@code |}
   * 前有实际短语**的行（Python 端 {@code parse_target_corpus} 同口径： {@code splitlines()} → 跳过空行 → {@code "|"
   * in line} 时拆 phrase/gloss → phrase 为空则跳过）。
   *
   * <p>为什么不按换行/分号切分：那样会把一行内带分号的中文释义算成多条，与真实消费方（Python）的解析结果 不一致。校验器与消费者同口径是硬要求 —— 否则会出现「Java 说够 3
   * 条、Python 只解析出 2 条」。
   */
  static int countCorpusItems(String targetCorpus) {
    if (isBlank(targetCorpus)) {
      return 0;
    }
    int count = 0;
    for (String line : targetCorpus.split("\\r?\\n")) {
      String trimmed = line.strip();
      if (trimmed.isEmpty()) {
        continue;
      }
      int bar = trimmed.indexOf('|');
      if (bar <= 0) {
        continue;
      }
      if (!trimmed.substring(0, bar).strip().isEmpty()) {
        count++;
      }
    }
    return count;
  }

  static String requireStatus(String raw) {
    String s = raw == null ? "" : raw.trim();
    if (!List.of(STATUS_DRAFT, STATUS_PUBLISHED, STATUS_ARCHIVED).contains(s)) {
      throw ConsoleException.of(
          ConsoleErrorCodes.INVALID_PARAM, "status 仅支持 draft|published|archived");
    }
    return s;
  }

  private static boolean isBlank(String s) {
    return s == null || s.isBlank();
  }

  /** 违规项转可序列化结构（写进 {@code data.violations[]}）。 */
  private List<Map<String, Object>> serializeViolations(List<Violation> violations) {
    List<Map<String, Object>> out = new ArrayList<>(violations.size());
    for (Violation v : violations) {
      Map<String, Object> m = new LinkedHashMap<>();
      m.put("field", v.field());
      m.put("code", v.code());
      m.put("message", v.message());
      out.add(m);
    }
    return out;
  }
}
