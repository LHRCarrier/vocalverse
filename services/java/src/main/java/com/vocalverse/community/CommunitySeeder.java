package com.vocalverse.community;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import com.vocalverse.user.UserRepository;
import java.time.Instant;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * 社区演示内容种子（docs/37 §7 · C-07：作者/标题/摘要**全部虚构原创**，禁用真实媒体品牌与原文）。
 *
 * <p>幂等：作者按 username、帖子按 slug 查重跳过（只增不改）；`vocalverse.community.seed=false` 关闭（测试环境
 * application-test.yml 关闭，单测库保持干净）；演示计数为静态展示（互动行 不逐条物化，当前用户的真实操作即时生效）。
 *
 * <p>执行顺序：@Order(2) 待 DemoSeeder(@Order(1)) 之后——历史打卡卡挂 demoadult，不存在则跳过。
 */
@Component
@Order(2)
public class CommunitySeeder implements CommandLineRunner {

  private static final Logger logger = LoggerFactory.getLogger(CommunitySeeder.class);

  private final UserRepository users;
  private final UserProfileRepository profiles;
  private final PostRepository posts;
  private final PasswordEncoder encoder;
  private final ObjectMapper mapper;
  private final boolean seedEnabled;

  public CommunitySeeder(
      UserRepository users,
      UserProfileRepository profiles,
      PostRepository posts,
      PasswordEncoder encoder,
      ObjectMapper mapper,
      @Value("${vocalverse.community.seed:true}") boolean seedEnabled) {
    this.users = users;
    this.profiles = profiles;
    this.posts = posts;
    this.encoder = encoder;
    this.mapper = mapper;
    this.seedEnabled = seedEnabled;
  }

  @Override
  public void run(String... args) {
    if (!seedEnabled) {
      return;
    }
    Long vvNews = seedAuthor("seed_vvnews", "VocalVerse News", "vocalverse", "#37546e", "L4");
    Long teacherAmy = seedAuthor("seed_teacher_amy", "Teacher Amy", "amyteach", "#3a2440", "L3");
    Long emma = seedAuthor("seed_emma_english", "Emma English", "emmaenglish", "#1e2b26", "L3");
    Long teacherLee = seedAuthor("seed_teacher_lee", "Teacher Lee", "leeenglish", "#232044", "L4");
    Long liz = seedAuthor("seed_liz_london", "Liz in London", "lizlondon", "#0f3a44", "L3");
    Long mia = seedAuthor("seed_mia_boston", "Mia in Boston", "miaboston", "#2b4a3a", "L2");
    Long saki = seedAuthor("seed_saki_kyoto", "Saki in Kyoto", "sakikyoto", "#4a3320", "L2");

    Instant now = Instant.now();
    // 内容帖（标题/摘要原创，领域三覆盖；created_at 错位复现演示帧时间感）
    seedPost(
        vvNews,
        "vv-news-ai-classroom",
        "article",
        "news",
        "Inside China's English learning boom: AI partners meet human teachers",
        "Education experts say AI speaking partners are changing how students practice, while teachers remain the gold standard for feedback.",
        null,
        now.minus(12, ChronoUnit.MINUTES),
        328,
        46,
        37,
        15);
    seedPost(
        teacherAmy,
        "vv-amy-small-talk",
        "video",
        "teaching",
        "Three words that make small talk easy at work",
        "A 4-minute practice: listen, shadow, compare. Vocabulary you can use the same day.",
        Map.of("type", "video", "durationS", 240),
        now.minus(32, ChronoUnit.MINUTES),
        1240,
        189,
        210,
        96);
    seedPost(
        emma,
        "vv-emma-phrasal-coffee",
        "article",
        "teaching",
        "5 phrasal verbs for your next coffee order, with dialogues",
        "1) pick up 2) sit down 3) pour out 4) hand over 5) run out of — with an example dialogue for each. Save this before your next role-play!",
        null,
        now.minus(1, ChronoUnit.HOURS),
        86,
        12,
        25,
        8);
    seedPost(
        teacherLee,
        "vv-lee-shadowing",
        "video",
        "teaching",
        "How I memorize 20 new words a week — the shadowing method",
        "My 10-minute daily routine: listen, shadow, record, compare. Full breakdown inside.",
        Map.of("type", "video", "durationS", 492),
        now.minus(2, ChronoUnit.HOURS),
        512,
        77,
        130,
        41);
    seedPost(
        liz,
        "vv-liz-bonfire",
        "article",
        "overseas",
        "My first Bonfire Night in London — what I learned",
        "A failed plot, a bonfire tradition, and my first 'penny for the guy'. Tonight we watched sparks over the Thames.",
        null,
        now.minus(3, ChronoUnit.HOURS),
        150,
        23,
        18,
        12);
    seedPost(
        mia,
        "vv-mia-dorm-morning",
        "video",
        "overseas",
        "Dorm life in Boston: my morning in 60 seconds",
        "Kitchen talk, roommate practices, and the shortest walk to class I could find.",
        Map.of("type", "video", "durationS", 62),
        now.minus(1, ChronoUnit.DAYS).plus(2, ChronoUnit.HOURS),
        73,
        9,
        22,
        5);
    seedPost(
        saki,
        "vv-saki-lunch",
        "article",
        "overseas",
        "Japanese school lunch culture — 25 minutes of mindful eating",
        "Students serve each other, eat together, and never waste. The 'kyushoku' system teaches more than nutrition.",
        null,
        now.minus(1, ChronoUnit.DAYS).minus(4, ChronoUnit.HOURS),
        201,
        34,
        41,
        19);
    seedPost(
        vvNews,
        "vv-news-slow-travel",
        "article",
        "news",
        "Slow travel is reshaping small-town Europe",
        "As borders ease, quiet villages are betting on longer stays, fewer tourists, and richer culture.",
        null,
        now.minus(2, ChronoUnit.DAYS),
        468,
        55,
        63,
        27);

    // 历史打卡卡（演示混排；挂 demoadult——演示账号存在才插，否则跳过）
    users
        .findByUsernameIgnoreCase("demoadult")
        .ifPresent(
            demo -> {
              seedCheckin(
                  demo.getId(),
                  LocalDate.now().minusDays(1),
                  81.5,
                  83.0,
                  79.0,
                  82.0,
                  8,
                  264,
                  6,
                  2,
                  1);
              seedCheckin(
                  demo.getId(),
                  LocalDate.now().minusDays(2),
                  76.0,
                  78.0,
                  72.0,
                  75.0,
                  7,
                  231,
                  3,
                  1,
                  0);
            });

    logger.info("社区演示种子就绪：7 位虚构作者 + 8 条内容帖 + 2 条历史打卡卡");
  }

  private Long seedAuthor(
      String username, String nickname, String handle, String tint, String level) {
    if (users.findByUsernameIgnoreCase(username).isPresent()) {
      return users.findByUsernameIgnoreCase(username).get().getId();
    }
    Instant now = Instant.now();
    UserEntity u = new UserEntity();
    u.setUsername(username);
    u.setEmail(null);
    u.setPasswordHash(encoder.encode("demo123456"));
    u.setNickname(nickname);
    u.setRole("user");
    u.setStatus("active");
    u.setCreatedAt(now);
    u.setUpdatedAt(now);
    u = users.save(u);

    UserProfileEntity p = new UserProfileEntity();
    p.setUserId(u.getId());
    p.setAgeGroup("adult");
    p.setCefrLevel(level);
    p.setInterestTags("[]");
    p.setVoiceRate("normal");
    p.setCefrLevelSource("manual");
    p.setHandle(handle);
    p.setTint(tint);
    p.setCreatedAt(now);
    p.setUpdatedAt(now);
    profiles.save(p);
    return u.getId();
  }

  private void seedPost(
      Long authorId,
      String slug,
      String kind,
      String domain,
      String title,
      String body,
      Map<String, Object> media,
      Instant createdAt,
      int likes,
      int comments,
      int coins,
      int shares) {
    if (posts.findFirstBySlug(slug).isPresent()) {
      return;
    }
    PostEntity e = new PostEntity();
    e.setAuthorId(authorId);
    e.setSlug(slug);
    e.setKind(kind);
    e.setDomain(domain);
    e.setTitle(title);
    e.setBody(body);
    if (media != null) {
      e.setMedia(writeJson(media));
    }
    e.setStatus("visible");
    e.setLikeCount(likes);
    e.setCommentCount(comments);
    e.setCoinCount(coins);
    e.setShareCount(shares);
    e.setCreatedAt(createdAt);
    e.setUpdatedAt(createdAt);
    posts.save(e);
  }

  private void seedCheckin(
      Long authorId,
      LocalDate date,
      double overall,
      double pron,
      double gram,
      double fluency,
      int turns,
      int durationS,
      int likes,
      int comments,
      int coins) {
    // (author_id, checkin_date) 幂等（kind='checkin' 部分唯一）
    if (posts.findFirstByAuthorIdAndCheckinDate(authorId, date).isPresent()) {
      return;
    }
    PostEntity e = new PostEntity();
    e.setAuthorId(authorId);
    e.setKind("checkin");
    e.setTitle("今日打卡");
    e.setStatus("visible");
    e.setCheckinDate(date);
    e.setCheckinSnapshot(
        writeJson(
            Map.of(
                "overall", overall,
                "pron", pron,
                "gram", gram,
                "fluency", fluency,
                "turns", turns,
                "duration_s", durationS,
                "practice_count", 1)));
    e.setLikeCount(likes);
    e.setCommentCount(comments);
    e.setCoinCount(coins);
    e.setCreatedAt(date.atTime(18, 0).toInstant(java.time.ZoneOffset.UTC));
    e.setUpdatedAt(e.getCreatedAt());
    posts.save(e);
  }

  private String writeJson(Map<String, Object> value) {
    try {
      return mapper.writeValueAsString(value);
    } catch (Exception ex) {
      throw new IllegalStateException("种子 JSON 序列化失败", ex);
    }
  }
}
