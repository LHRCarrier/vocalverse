package com.vocalverse.community;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;

/**
 * J-07 真 PG 集成（@Tag("integration") · CI 默认跳过，本地必跑：{@code mvn verify -Pintegration}）。
 *
 * <p>覆盖 H2（MODE=PostgreSQL）验证不到的方言边界（docs/37 §9 B-14/C-14 落地）：
 *
 * <ul>
 *   <li>{@code uq_posts_checkin} 部分唯一索引（每日一卡：仅 kind='checkin' 唯一约束）；
 *   <li>JSONB 列（posts.media）读写与 jsonb 相等语义；
 *   <li>timestamptz(6) 微秒精度（keyset 游标口径，CommunityService.micro 对齐依据）；
 *   <li>GREATEST 自减护底 / ON CONFLICT DO NOTHING（J-01 依赖的 PG 原生语义）；
 *   <li>EXPLAIN：feed 混排/领域查询反向扫描命中 ix_posts_feed_time / ix_posts_domain_time（J-11 证据）。
 * </ul>
 *
 * <p>schema 真源 = Alembic（services/python/alembic）——跳过 Hibernate create-drop 的「假绿」： 容器启动后用 {@code uv
 * run alembic upgrade head}（env APP_DATABASE_URL 指向容器）建真实 schema， 需本机 uv 环境；Docker 不可用自动
 * skip（不破坏默认门禁）。
 */
@Tag("integration")
class CommunityPgIntegrationTest {

  private static final String IMAGE = "postgres:16-alpine";
  private static PostgreSQLContainer<?> PG;
  private static Connection conn;

  static {
    try {
      PG = new PostgreSQLContainer<>(IMAGE);
      PG.start();
    } catch (Throwable t) {
      PG = null; // Docker daemon 不可用/镜像拉取失败 → @BeforeAll assumption skip
    }
  }

  @BeforeAll
  static void bootstrap() throws Exception {
    Assumptions.assumeTrue(PG != null, "Docker 不可用，PG 集成测试跳过");
    runAlembicUpgrade(PG);
    conn = DriverManager.getConnection(PG.getJdbcUrl(), PG.getUsername(), PG.getPassword());
  }

  @AfterAll
  static void tearDown() throws Exception {
    if (conn != null) {
      conn.close();
    }
    if (PG != null) {
      PG.stop();
    }
  }

  @BeforeEach
  void cleanTables() throws Exception {
    try (Statement st = conn.createStatement()) {
      st.execute(
          "TRUNCATE TABLE post_likes, post_interactions, post_comments, follows, posts, user_profiles, users,"
              + " direct_messages, dm_read_state CASCADE");
    }
  }

  // ------------------------------------------------------------------ 测试

  @Test
  void partialUniqueIndex_uqPostsCheckin_dailyOnePerAuthor() throws Exception {
    long uid = insertUser("j07_pgcheckin");
    insertPost(uid, "checkin", "news", LocalDate.of(2026, 9, 8));

    // 同日第二张打卡卡 → 部分唯一索引拒绝（仅 kind='checkin'）
    SQLException dup =
        assertThrows(
            SQLException.class, () -> insertPost(uid, "checkin", "news", LocalDate.of(2026, 9, 8)));
    assertTrue(dup.getSQLState().startsWith("23"), "应为完整性约束违例（23xxx）而非其他：" + dup.getSQLState());

    // 同日 article 不受约束（部分索引按 kind 过滤）
    long articleId = insertPost(uid, "article", "news", LocalDate.of(2026, 9, 8));
    assertTrue(articleId > 0, "非 checkin 同 author+日期应可插入");

    // 另一作者同日打卡卡：不受该约束（部分索引按 author 过滤）
    long other = insertUser("j07_pgcheckin2");
    insertPost(other, "checkin", "news", LocalDate.of(2026, 9, 8));
  }

  @Test
  void greatestDecrement_neverNegative() throws Exception {
    long uid = insertUser("j07_pggreatest");
    long pid = insertPost(uid, "article", "news", null);
    // 0 - 1 → 0（对 J-01 unlike 同款 SQL：GREATEST 护底）
    exec("UPDATE posts SET like_count = GREATEST(like_count - 1, 0) WHERE id = " + pid);
    assertEquals(0, queryInt("SELECT like_count FROM posts WHERE id = " + pid));
    // 3 - 1 → 2（正常递减）
    exec("UPDATE posts SET like_count = 3 WHERE id = " + pid);
    exec("UPDATE posts SET like_count = GREATEST(like_count - 1, 0) WHERE id = " + pid);
    assertEquals(2, queryInt("SELECT like_count FROM posts WHERE id = " + pid));
  }

  @Test
  void onConflictDoNothing_idempotentInsertLikeRow() throws Exception {
    long uid = insertUser("j07_pgconflict");
    long pid = insertPost(uid, "article", "news", null);
    String sql =
        "INSERT INTO post_likes (post_id, liker_id, created_at) VALUES ("
            + pid
            + ", "
            + uid
            + ", now()) ON CONFLICT DO NOTHING";
    // J-01 依赖：首次插入 1 行；重复/并发 → 0 行不报错（服务端无 500 根因）
    assertEquals(1, execUpdate(sql));
    assertEquals(0, execUpdate(sql));
    assertEquals(1, queryInt("SELECT count(*) FROM post_likes WHERE post_id = " + pid));
  }

  @Test
  void jsonbColumn_roundtrip_withJsonbEquality() throws Exception {
    long uid = insertUser("j07_pgjsonb");
    long pid = insertPost(uid, "article", "news", null);
    exec(
        "UPDATE posts SET media = '{\"url\":\"https://example.com/a.mp4\",\"k\":[1,2]}'::jsonb WHERE id = "
            + pid);
    // 读取：jsonb::text 规范化输出（键序/空白不保证），用 jsonb 相等断言语义
    String text = queryText("SELECT media::text FROM posts WHERE id = " + pid);
    assertTrue(text.contains("a.mp4"), "JSONB 往返内容应保留：" + text);
    assertEquals(
        1,
        queryInt(
            "SELECT (media = '{\"k\":[1,2],\"url\":\"https://example.com/a.mp4\"}'::jsonb)::int FROM posts WHERE id = "
                + pid),
        "jsonb 相等（键序无关）");
  }

  @Test
  void timestamptz_microsecondPrecision() throws Exception {
    long uid = insertUser("j07_pgmicro");
    long pid = insertPost(uid, "article", "news", null);
    // 纳秒输入 → timestamptz(6)：PG **四舍五入**到微秒（.123456789 → .123457，本机实测 2026-09-08；
    // 注意非截断——CommunityService.micro() 是「%1000 截断」。读路径实体值已 6 位（DB 读回）无碰撞，
    // 若未来直接以写入期 Instant（9 位）做游标才会差 1µs，登记 docs/37 §9）
    exec(
        "UPDATE posts SET created_at = '2026-09-08T01:02:03.123456789Z'::timestamptz WHERE id = "
            + pid);
    String text = queryText("SELECT created_at::text FROM posts WHERE id = " + pid);
    assertTrue(
        text.contains(".123457"), "timestamptz(6) 应四舍五入到微秒 .123457（而非截断 .123456/保留纳秒）：" + text);
    // 与「四舍五入后的微秒键」相等（keyset 阈值比较口径：数据库内值 == 6 位归一值）
    assertEquals(
        1,
        queryInt(
            "SELECT count(*) FROM posts WHERE created_at = '2026-09-08T01:02:03.123457Z'::timestamptz"),
        "DB 值应与四舍五入后的微秒键相等");
    // 向下舍入边界（.123456499 → .123456）——证明舍入（而非恒向上/截断）
    exec(
        "UPDATE posts SET created_at = '2026-09-08T01:02:03.123456499Z'::timestamptz WHERE id = "
            + pid);
    text = queryText("SELECT created_at::text FROM posts WHERE id = " + pid);
    assertTrue(text.contains(".123456"), "四舍五入边界（.123456499 → .123456）：" + text);
  }

  @Test
  void explain_feed_uses_index_backward_scan() throws Exception {
    long uid = insertUser("j07_pgexplain");
    for (int i = 0; i < 8; i++) {
      insertPost(uid, "article", i % 2 == 0 ? "news" : "teaching", null);
    }
    // 小表 planner 默认 seqscan；关闭后验证「该查询形状可命中索引反向扫描」这一事实（B-05/J-11 证据）
    exec("SET enable_seqscan = off");
    // 混排 feed（domain=null）：WHERE status ORDER BY created_at DESC, id DESC → ix_posts_feed_time 反向
    String planAll =
        queryText(
            "EXPLAIN (FORMAT TEXT) SELECT id FROM posts WHERE status = 'visible' ORDER BY created_at DESC, id DESC LIMIT 11");
    assertTrue(
        planAll.contains("ix_posts_feed_time"), "混排 feed 应反向扫描 ix_posts_feed_time：\n" + planAll);
    assertTrue(planAll.contains("Backward"), "应为 Backward（DESC 序）扫描：\n" + planAll);
    // 领域过滤：ix_posts_domain_time（status, domain, created_at, id）正好覆盖
    String planDomain =
        queryText(
            "EXPLAIN (FORMAT TEXT) SELECT id FROM posts WHERE status = 'visible' AND domain = 'news' ORDER BY created_at DESC, id DESC LIMIT 11");
    assertTrue(
        planDomain.contains("ix_posts_domain_time"),
        "领域 feed 应反向扫描 ix_posts_domain_time：\n" + planDomain);
    exec("SET enable_seqscan = on");
  }

  /**
   * J-03（2026-09-10）：通知分页改为 DB 层聚合后，证据链补齐——互动组聚合查询命中 {@code
   * ix_post_interactions_post_action}（(post_id, action, created_at) 前两列等值 + 第三列可反向）、评论流命中 {@code
   * ix_post_comments_status_post}（(status, post_id, created_at, id) 等值 + 反向）。
   *
   * <p>小表 planner 默认 seqscan → {@code SET enable_seqscan=off} 验证「该查询形状可命中索引」这一事实（同 J-07 feed 口径）。
   */
  @Test
  void explain_notification_queries_use_indexes() throws Exception {
    long author = insertUser("j03_pgexplain");
    long post = insertPost(author, "article", "news", null);
    // 互动唯一键 (actor, post, action) → 每天用不同 actor
    for (int i = 0; i < 6; i++) {
      long actor = insertUser("j03_pgexplain_a" + i);
      exec(
          "INSERT INTO post_interactions (actor_id, post_id, action, created_at) VALUES ("
              + actor
              + ", "
              + post
              + ", 'like', now() - interval '"
              + i
              + " day')");
      exec(
          "INSERT INTO post_comments (post_id, author_id, body, status, created_at, updated_at) VALUES ("
              + post
              + ", "
              + actor
              + ", 'c"
              + i
              + "', 'visible', now() - interval '"
              + i
              + " hour', now())");
    }
    exec("SET enable_seqscan = off");
    String planInteractions =
        queryText(
            "EXPLAIN (FORMAT TEXT) SELECT post_id || '|' || action || '|' || CAST(created_at AS date) AS merge_key, "
                + "COUNT(*) FROM post_interactions WHERE action = 'like' AND actor_id <> "
                + author
                + " AND post_id IN (SELECT id FROM posts WHERE author_id = "
                + author
                + " AND status = 'visible') GROUP BY post_id, action, CAST(created_at AS date)");
    assertTrue(
        planInteractions.contains("ix_post_interactions_post_action"),
        "互动组聚合应命中 ix_post_interactions_post_action：\n" + planInteractions);
    String planComments =
        queryText(
            "EXPLAIN (FORMAT TEXT) SELECT id, post_id, author_id, body, created_at FROM post_comments "
                + "WHERE status = 'visible' AND post_id IN (SELECT id FROM posts WHERE author_id = "
                + author
                + " AND status = 'visible') ORDER BY created_at DESC, id DESC LIMIT 11");
    assertTrue(
        planComments.contains("ix_post_comments_status_post"),
        "评论流应命中 ix_post_comments_status_post：\n" + planComments);
    // 注：本查询 ORDER BY (created_at DESC, id DESC) 走「Index Scan + Sort」而非 Backward——断言只锁「命中索引」
    // （索引键序为 (status, post_id, created_at, id)，等值列前缀命中即可；Backward 只在键序与排序完全一致时出现，
    //  feed 侧 J-11 即此形态）。断言索引名可复现、不因 planner 选择排序策略而脆断。
    exec("SET enable_seqscan = on");
  }

  /**
   * 2026-09-10 联调教训：**H2 放过的写法 PG 会拒**，单测全绿但真机 500。本用例在真 PG 上以 PreparedStatement 复刻服务层实发
   * SQL（含首页哨兵游标），锁住两处修复：
   *
   * <ol>
   *   <li>首页游标 **不能用 NULL 参数**——`(:cursorTs IS NULL OR … :cursorKey)` 在 IS NULL 分支下 PG 报 `could not
   *       determine data type of parameter $4`；服务层改传哨兵值（9999-12-31 + 空串）；
   *   <li>哨兵 **不能用 {@link Instant#MAX}**——驱动渲染为 `169104627-12-11 … BC`，PG 报 `timestamp out of
   *       range`。
   * </ol>
   *
   * <p>SQL 与 {@code PostInteractionRepository} / {@code DirectMessageRepository} 的字符串常量同步维护 （Java
   * 无共享常量机制；改动仓库查询时同步本用例，否则本用例退化为「假绿」）。
   */
  @Test
  void notifications_paging_queries_on_real_pg() throws Exception {
    Instant cursorMax = Instant.parse("9999-12-31T23:59:59Z");
    long author = insertUser("j03_dialect_a");
    long actor = insertUser("j03_dialect_b");
    long actor2 = insertUser("j03_dialect_c");
    long post = insertPost(author, "article", "news", null);
    exec(
        "INSERT INTO post_interactions (actor_id, post_id, action, created_at) VALUES ("
            + actor
            + ", "
            + post
            + ", 'like', now())");
    exec(
        "INSERT INTO post_interactions (actor_id, post_id, action, created_at) VALUES ("
            + actor2
            + ", "
            + post
            + ", 'like', now())");
    exec(
        "INSERT INTO post_comments (post_id, author_id, body, status, created_at, updated_at) VALUES ("
            + post
            + ", "
            + actor
            + ", 'c1', 'visible', now(), now())");

    String sqlGroups =
        "SELECT merge_key AS \"mergeKey\", post_id AS \"postId\", action AS \"action\", "
            + "item_count AS \"itemCount\", latest_at AS \"latestAt\", latest_id AS \"latestId\" FROM ("
            + " SELECT g.merge_key AS merge_key, g.post_id AS post_id, g.action AS action,"
            + " COUNT(*) AS item_count, MAX(g.created_at) AS latest_at, MAX(g.id) AS latest_id FROM ("
            + "  SELECT p.post_id || '|' || p.action || '|' || CAST(p.created_at AS date) AS merge_key,"
            + "  p.post_id AS post_id, p.action AS action, p.created_at AS created_at, p.id AS id"
            + "  FROM post_interactions p WHERE p.action = ? AND p.actor_id <> ?"
            + "  AND p.post_id IN (SELECT po.id FROM posts po WHERE po.author_id = ? AND po.status = 'visible')"
            + " ) g GROUP BY g.merge_key, g.post_id, g.action"
            + ") a WHERE (a.latest_at < ? OR (a.latest_at = ? AND a.merge_key > ?))"
            + " ORDER BY a.latest_at DESC, a.merge_key ASC LIMIT ?";
    try (PreparedStatement ps = conn.prepareStatement(sqlGroups)) {
      ps.setString(1, "like");
      ps.setLong(2, author);
      ps.setLong(3, author);
      ps.setTimestamp(4, Timestamp.from(cursorMax));
      ps.setTimestamp(5, Timestamp.from(cursorMax));
      ps.setString(6, "");
      ps.setInt(7, 11);
      try (ResultSet rs = ps.executeQuery()) {
        assertTrue(rs.next(), "首页（哨兵游标）应返回互动组");
        assertEquals(2, rs.getInt("itemCount"), "同帖同动作当日应聚合为 1 组 count=2");
      }
    }
    // 带真实游标（早于该组）→ 不返回
    try (PreparedStatement ps = conn.prepareStatement(sqlGroups)) {
      Instant earlier = Instant.now().minusSeconds(3600);
      ps.setString(1, "like");
      ps.setLong(2, author);
      ps.setLong(3, author);
      ps.setTimestamp(4, Timestamp.from(earlier));
      ps.setTimestamp(5, Timestamp.from(earlier));
      ps.setString(6, "");
      ps.setInt(7, 11);
      try (ResultSet rs = ps.executeQuery()) {
        assertTrue(!rs.next(), "游标早于该组 → 不应返回");
      }
    }

    String sqlComments =
        "SELECT c.id AS id, c.post_id AS \"postId\", c.author_id AS \"authorId\", c.body AS body,"
            + " c.created_at AS \"createdAt\" FROM post_comments c WHERE c.status = 'visible'"
            + " AND c.post_id IN (SELECT po.id FROM posts po WHERE po.author_id = ? AND po.status = 'visible')"
            + " AND c.author_id <> ? AND (c.created_at < ? OR (c.created_at = ? AND c.id < ?))"
            + " ORDER BY c.created_at DESC, c.id DESC LIMIT ?";
    try (PreparedStatement ps = conn.prepareStatement(sqlComments)) {
      ps.setLong(1, author);
      ps.setLong(2, author);
      ps.setTimestamp(3, Timestamp.from(cursorMax));
      ps.setTimestamp(4, Timestamp.from(cursorMax));
      ps.setLong(5, Long.MAX_VALUE);
      ps.setInt(6, 11);
      try (ResultSet rs = ps.executeQuery()) {
        assertTrue(rs.next(), "评论首页应返回 1 条");
        assertEquals("c1", rs.getString("body"));
      }
    }

    long peer = insertUser("j03_dialect_peer");
    exec(
        "INSERT INTO direct_messages (sender_id, recipient_id, body, status, created_at) VALUES ("
            + author
            + ", "
            + peer
            + ", 'm1', 'visible', now() - interval '2 hour')");
    exec(
        "INSERT INTO direct_messages (sender_id, recipient_id, body, status, created_at) VALUES ("
            + peer
            + ", "
            + author
            + ", 'm2', 'visible', now())");
    String sqlConversations =
        "SELECT a.peer_id AS \"peerId\", a.last_message_id AS \"lastMessageId\","
            + " (SELECT m2.body FROM direct_messages m2 WHERE m2.id = a.last_message_id) AS \"lastBody\","
            + " (SELECT m3.sender_id FROM direct_messages m3 WHERE m3.id = a.last_message_id) AS \"lastSenderId\","
            + " (SELECT m4.created_at FROM direct_messages m4 WHERE m4.id = a.last_message_id) AS \"lastCreatedAt\","
            + " (SELECT COUNT(*) FROM direct_messages m5 WHERE m5.sender_id = a.peer_id AND m5.recipient_id = ?"
            + "   AND m5.status = 'visible' AND m5.id > COALESCE((SELECT r.last_read_id FROM dm_read_state r"
            + "     WHERE r.user_id = ? AND r.peer_id = a.peer_id), 0)) AS \"unreadCount\" FROM ("
            + "  SELECT x.peer_id AS peer_id, MAX(x.id) AS last_message_id FROM ("
            + "   SELECT CASE WHEN m.sender_id = ? THEN m.recipient_id ELSE m.sender_id END AS peer_id, m.id AS id"
            + "   FROM direct_messages m WHERE m.status = 'visible' AND (m.sender_id = ? OR m.recipient_id = ?)"
            + "  ) x GROUP BY x.peer_id"
            + ") a ORDER BY a.last_message_id DESC LIMIT ?";
    try (PreparedStatement ps = conn.prepareStatement(sqlConversations)) {
      ps.setLong(1, author);
      ps.setLong(2, author);
      ps.setLong(3, author);
      ps.setLong(4, author);
      ps.setLong(5, author);
      ps.setInt(6, 50);
      try (ResultSet rs = ps.executeQuery()) {
        assertTrue(rs.next(), "应返回 1 个会话");
        assertEquals(peer, rs.getLong("peerId"));
        assertEquals("m2", rs.getString("lastBody"), "最后一条应是对方刚发的 m2（防跨会话串话）");
        assertEquals(peer, rs.getLong("lastSenderId"));
        assertEquals(1, rs.getInt("unreadCount"), "对端 1 条未读（水位缺行视作 0）");
      }
    }
  }

  // ------------------------------------------------------------------ 工具
  /** schema 真源（Alembic）迁移到 head：env APP_DATABASE_URL 指向容器（迁移 env.py 同款约定）。 */
  private static void runAlembicUpgrade(PostgreSQLContainer<?> pg) throws Exception {
    Path repoPython =
        Path.of(System.getProperty("user.dir"))
            .resolve("../../services/python")
            .normalize()
            .toAbsolutePath();
    String url =
        String.format(
            "postgresql+psycopg://%s:%s@%s:%d/%s",
            pg.getUsername(),
            pg.getPassword(),
            pg.getHost(),
            pg.getMappedPort(5432),
            pg.getDatabaseName());
    ProcessBuilder pb = new ProcessBuilder("uv", "run", "alembic", "upgrade", "head");
    pb.directory(repoPython.toFile());
    pb.environment().put("APP_DATABASE_URL", url);
    pb.redirectErrorStream(true);
    Process p = pb.start();
    boolean finished = p.waitFor(300, TimeUnit.SECONDS);
    if (!finished) {
      p.destroyForcibly();
      throw new IllegalStateException("alembic upgrade head 超时（300s）");
    }
    String out = new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
    assertEquals(0, p.exitValue(), "alembic upgrade head 失败：\n" + out);
  }

  private long insertUser(String username) throws Exception {
    exec(
        "INSERT INTO users (username, password_hash, nickname, role, status, created_at, updated_at) VALUES ('"
            + username
            + "', 'x', '"
            + username
            + "', 'user', 'active', now(), now())");
    return queryLong("SELECT id FROM users WHERE username = '" + username + "'");
  }

  private long insertPost(long authorId, String kind, String domain, LocalDate checkinDate)
      throws Exception {
    String sql =
        "INSERT INTO posts (author_id, kind, domain, title, checkin_date) VALUES ("
            + authorId
            + ", '"
            + kind
            + "', "
            + (domain == null ? "NULL" : "'" + domain + "'")
            + ", 't', "
            + (checkinDate == null ? "NULL" : "'" + checkinDate + "'")
            + ")";
    Statement st = conn.createStatement();
    try {
      st.executeUpdate(sql, Statement.RETURN_GENERATED_KEYS);
      try (ResultSet keys = st.getGeneratedKeys()) {
        assertTrue(keys.next(), "应返回生成键");
        return keys.getLong(1);
      }
    } finally {
      st.close();
    }
  }

  private void exec(String sql) throws Exception {
    try (Statement st = conn.createStatement()) {
      st.execute(sql);
    }
  }

  private int execUpdate(String sql) throws SQLException {
    try (Statement st = conn.createStatement()) {
      return st.executeUpdate(sql);
    }
  }

  private int queryInt(String sql) throws SQLException {
    try (Statement st = conn.createStatement();
        ResultSet rs = st.executeQuery(sql)) {
      rs.next();
      return rs.getInt(1);
    }
  }

  private long queryLong(String sql) throws SQLException {
    try (Statement st = conn.createStatement();
        ResultSet rs = st.executeQuery(sql)) {
      rs.next();
      return rs.getLong(1);
    }
  }

  /** EXPLAIN 等多行结果：拼接第一列各行。 */
  private String queryText(String sql) throws SQLException {
    StringBuilder sb = new StringBuilder();
    try (Statement st = conn.createStatement();
        ResultSet rs = st.executeQuery(sql)) {
      while (rs.next()) {
        sb.append(rs.getString(1)).append('\n');
      }
    }
    return sb.toString();
  }
}
