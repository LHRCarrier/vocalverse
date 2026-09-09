package com.vocalverse.community;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.community.dto.CommunityView.AuthorView;
import com.vocalverse.community.dto.CommunityView.CoinState;
import com.vocalverse.community.dto.CommunityView.CommentPage;
import com.vocalverse.community.dto.CommunityView.CommentView;
import com.vocalverse.community.dto.CommunityView.CommunityPostView;
import com.vocalverse.community.dto.CommunityView.FeedPage;
import com.vocalverse.community.dto.CommunityView.FollowRecommend;
import com.vocalverse.community.dto.CommunityView.FollowSummary;
import com.vocalverse.community.dto.CommunityView.LikeState;
import com.vocalverse.community.dto.CommunityView.NotificationItem;
import com.vocalverse.community.dto.CommunityView.NotificationsPage;
import com.vocalverse.community.dto.CommunityView.ShareState;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import com.vocalverse.user.UserRepository;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 社区内容服务（Java 写方唯一实现 · docs/37 §5）。
 *
 * <p>沿用口径：统一可见谓词 status='visible'；互动与计数增减同事务；like/coin/share 幂等 （唯一键兜底 + 重复请求返回当前态）；checkin
 * 卡仅开放点赞（评论/投币/分享 40302）； media/checkin_snapshot 为 JSON 文本列 → ObjectMapper 转换。
 */
@Service
public class CommunityService {

  public static final String KIND_ARTICLE = "article";
  public static final String KIND_VIDEO = "video";
  public static final String KIND_CHECKIN = "checkin";
  public static final String ACTION_LIKE = "like";
  public static final String ACTION_COIN = "coin";
  public static final String ACTION_SHARE = "share";
  public static final String STATUS_VISIBLE = "visible";
  private static final int MAX_LIMIT = 20;

  /** keyset 游标（base64url(epochMillis|id)）；null = 首页。 */
  private record Cursor(Instant ts, Long id) {}

  private final PostRepository posts;
  private final PostCommentRepository comments;
  private final PostLikeRepository likes;
  private final PostInteractionRepository interactions;
  private final FollowRepository follows;
  private final UserRepository users;
  private final UserProfileRepository profiles;
  private final ObjectMapper mapper;
  private final MediaRefValidator mediaValidator;
  private final boolean postEnabled;

  public CommunityService(
      PostRepository posts,
      PostCommentRepository comments,
      PostLikeRepository likes,
      PostInteractionRepository interactions,
      FollowRepository follows,
      UserRepository users,
      UserProfileRepository profiles,
      ObjectMapper mapper,
      MediaRefValidator mediaValidator,
      @Value("${vocalverse.community.post-enabled:false}") boolean postEnabled) {
    this.posts = posts;
    this.comments = comments;
    this.likes = likes;
    this.interactions = interactions;
    this.follows = follows;
    this.users = users;
    this.profiles = profiles;
    this.mapper = mapper;
    this.mediaValidator = mediaValidator;
    this.postEnabled = postEnabled;
  }

  // ------------------------------------------------------------------ feed

  @Transactional(readOnly = true)
  public FeedPage feed(Long actorId, String domain, String cursor, int limit, boolean mine) {
    String normalized = normalizeDomain(domain);
    Cursor c = decodeCursor(cursor);
    int pageSize = clampLimit(limit);
    // mine=true → 只看本人发帖（「我的发帖」页，docs/47 §5.1 · 2026-09-09 补）
    Long authorFilter = mine ? actorId : null;
    // 多取一条判 hasMore（docs/37 §5 keyset 约定）；DESC 排序由 Pageable 携带（Criteria 执行）
    PageRequest pageable =
        PageRequest.of(0, pageSize + 1, Sort.by(Sort.Direction.DESC, "createdAt", "id"));
    List<PostEntity> rows = posts.feed(normalized, authorFilter, c.ts(), c.id(), pageable);
    boolean hasMore = rows.size() > pageSize;
    List<PostEntity> page = hasMore ? rows.subList(0, pageSize) : rows;
    List<CommunityPostView> views = buildViews(page, actorId);
    String next = hasMore ? encodeCursor(lastKey(page)) : null;
    return new FeedPage(views, next, hasMore);
  }

  // ------------------------------------------------------------------ 帖

  @Transactional
  public CommunityPostView create(
      Long userId, String title, String body, String kind, String domain, JsonNode media) {
    if (!postEnabled) {
      throw new CommunityException(40302, "社区发帖功能未开放", HttpStatus.FORBIDDEN);
    }
    if (!(KIND_ARTICLE.equals(kind) || KIND_VIDEO.equals(kind))) {
      throw new CommunityException(42203, "kind 仅支持 article/video", HttpStatus.BAD_REQUEST);
    }
    String normalized = normalizeDomain(domain);
    if (normalized == null) {
      throw new CommunityException(42203, "发帖必须选择领域", HttpStatus.BAD_REQUEST);
    }
    if (body == null || body.isBlank()) {
      throw new CommunityException(42203, "帖子正文不能为空", HttpStatus.BAD_REQUEST);
    }
    // media 契约校验（docs/47 §4.3）：形状/条数/URL 前缀白名单；违规 42203
    JsonNode validatedMedia = mediaValidator.validate(media);
    PostEntity e = new PostEntity();
    e.setAuthorId(userId);
    e.setKind(kind);
    e.setDomain(normalized);
    e.setTitle(title);
    e.setBody(body);
    if (validatedMedia != null) {
      try {
        e.setMedia(mapper.writeValueAsString(validatedMedia));
      } catch (Exception ex) {
        throw new CommunityException(42203, "media 序列化失败", HttpStatus.BAD_REQUEST);
      }
    }
    e.setStatus(STATUS_VISIBLE);
    Instant now = Instant.now();
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    e = posts.save(e);
    return buildViews(List.of(e), userId).get(0);
  }

  @Transactional(readOnly = true)
  public CommunityPostView detail(Long userId, Long postId) {
    PostEntity post = posts.findById(postId).orElseThrow(() -> notFound("内容不存在或已删除"));
    boolean isAuthor = post.getAuthorId().equals(userId);
    if (!STATUS_VISIBLE.equals(post.getStatus()) && !isAuthor) {
      throw notFound("内容不存在或已删除");
    }
    return buildViews(List.of(post), userId).get(0);
  }

  @Transactional
  public void delete(Long userId, Long postId) {
    PostEntity post = posts.findById(postId).orElseThrow(() -> notFound("内容不存在或已删除"));
    if (!post.getAuthorId().equals(userId)) {
      throw new CommunityException(40302, "只能删除自己的内容", HttpStatus.FORBIDDEN);
    }
    if (!STATUS_VISIBLE.equals(post.getStatus())) {
      throw notFound("内容不存在或已删除"); // 幂等：已删除视为不存在
    }
    post.setStatus("deleted");
    post.setUpdatedAt(Instant.now());
    posts.save(post);
  }

  // ------------------------------------------------------------------ 评论

  @Transactional(readOnly = true)
  public CommentPage comments(Long actorId, Long postId, String cursor, int limit) {
    requireVisible(postId);
    Cursor c = decodeCursor(cursor);
    int pageSize = clampLimit(limit);
    // 多取一条判 hasMore（docs/37 §5 keyset 约定）；ASC 排序由 Pageable 携带（Criteria 执行）
    PageRequest pageable =
        PageRequest.of(0, pageSize + 1, Sort.by(Sort.Direction.ASC, "createdAt", "id"));
    List<PostCommentEntity> rows = comments.page(postId, c.ts(), c.id(), pageable);
    boolean hasMore = rows.size() > pageSize;
    List<PostCommentEntity> page = hasMore ? rows.subList(0, pageSize) : rows;
    // J-05：批量聚合作者（一次 loadAuthors），替代逐条 toCommentView 的 2 查询/条 N+1
    List<CommentView> views = toCommentViews(page);
    String next = hasMore ? encodeCursor(lastKey(page)) : null;
    return new CommentPage(views, next, hasMore);
  }

  @Transactional
  public CommentView addComment(Long userId, Long postId, String body) {
    PostEntity post = requireVisible(postId);
    if (KIND_CHECKIN.equals(post.getKind())) {
      throw new CommunityException(40302, "打卡卡不支持评论", HttpStatus.FORBIDDEN);
    }
    if (body == null || body.isBlank() || body.length() > 500) {
      throw new CommunityException(42203, "评论需 1~500 字", HttpStatus.BAD_REQUEST);
    }
    PostCommentEntity c = new PostCommentEntity();
    c.setPostId(postId);
    c.setAuthorId(userId);
    c.setBody(body);
    c.setStatus(STATUS_VISIBLE);
    Instant now = Instant.now();
    c.setCreatedAt(now);
    c.setUpdatedAt(now);
    c = comments.save(c);
    posts.incrementComment(postId);
    return toCommentView(c);
  }

  // ------------------------------------------------------------------ 互动

  @Transactional
  public LikeState like(Long userId, Long postId, boolean on) {
    requireVisible(postId);
    boolean liked;
    if (on) {
      // 唯一键原子幂等（ON CONFLICT DO NOTHING，J-01）：并发双击只生效一次。
      // 替代「先查后插」check-then-act（PG READ COMMITTED 下两次并发查空 → 撞唯一键 →
      // 未捕获 DataIntegrityViolationException → 500）；DB 原子性消除竞态窗口，不再依赖异常兜底。
      int inserted = likes.insertIgnoreConflict(postId, userId, Instant.now());
      if (inserted > 0) {
        posts.incrementLike(postId);
        interactions.insertIgnoreConflict(userId, postId, ACTION_LIKE, Instant.now());
      }
      liked = true;
    } else {
      // 先判存在再减（J-01）：仅当事实行真实删除（返回 1）才递减计数——并发双击取消各自执行
      // 「删除+递减」会双减，GREATEST 只兜底到 0 不防漂移；删行与计数同事务，行消失即计数保护。
      int removed = likes.deleteOneByPostIdAndLikerId(postId, userId);
      if (removed > 0) {
        posts.decrementLike(postId);
        interactions.deleteByActorIdAndPostIdAndAction(userId, postId, ACTION_LIKE);
      }
      liked = false;
    }
    return new LikeState(liked, requireVisible(postId).getLikeCount());
  }

  @Transactional
  public CoinState coin(Long userId, Long postId) {
    PostEntity post = requireVisible(postId);
    if (KIND_CHECKIN.equals(post.getKind())) {
      throw new CommunityException(40302, "打卡卡不支持投币", HttpStatus.FORBIDDEN);
    }
    boolean coined = insertInteractionIdempotent(userId, postId, ACTION_COIN);
    if (coined) {
      posts.incrementCoin(postId);
    }
    return new CoinState(coined, requireVisible(postId).getCoinCount());
  }

  @Transactional
  public ShareState share(Long userId, Long postId) {
    PostEntity post = requireVisible(postId);
    if (KIND_CHECKIN.equals(post.getKind())) {
      throw new CommunityException(40302, "打卡卡不支持分享", HttpStatus.FORBIDDEN);
    }
    boolean shared = insertInteractionIdempotent(userId, postId, ACTION_SHARE);
    if (shared) {
      posts.incrementShare(postId);
    }
    return new ShareState(shared, requireVisible(postId).getShareCount());
  }

  // ------------------------------------------------------------------ /internal/checkin

  /**
   * 打卡卡物化 upsert（docs/21 §4 · 幂等键 (author_id, checkin_date)：存在则 practice_count+1、
   * overall=GREATEST(旧,新)、其余子分/时长更新为本次；否则插入新卡。仅 kind='checkin' 命中。
   */
  @Transactional
  public long upsertCheckin(
      Long userId,
      String practiceDate,
      Long sessionId,
      Double overall,
      Double pron,
      Double gram,
      Double fluency,
      Integer turns,
      Integer durationS) {
    users
        .findById(userId)
        .orElseThrow(
            () ->
                new org.springframework.web.server.ResponseStatusException(
                    HttpStatus.NOT_FOUND, "user not found"));
    LocalDate date = LocalDate.parse(practiceDate);
    PostEntity post =
        posts.findFirstByAuthorIdAndCheckinDateAndKind(userId, date, KIND_CHECKIN).orElse(null);
    Instant now = Instant.now();
    if (post == null) {
      post = new PostEntity();
      post.setAuthorId(userId);
      post.setKind(KIND_CHECKIN);
      post.setTitle("今日打卡");
      post.setStatus(STATUS_VISIBLE);
      post.setCheckinDate(date);
      post.setSessionId(sessionId);
      post.setLikeCount(0);
      post.setCoinCount(0);
      post.setCommentCount(0);
      post.setShareCount(0);
      post.setCreatedAt(now);
      post.setCheckinSnapshot(
          writeCheckinSnapshot(null, overall, pron, gram, fluency, turns, durationS, 1));
    } else {
      post.setSessionId(sessionId == null ? post.getSessionId() : sessionId);
      // 当日终态（C-16 口径：明示会刷新，不承诺历史稳定）
      post.setCheckinSnapshot(
          writeCheckinSnapshot(
              parseJson(post.getCheckinSnapshot()),
              overall,
              pron,
              gram,
              fluency,
              turns,
              durationS,
              null));
    }
    post.setUpdatedAt(now);
    return posts.save(post).getId();
  }

  private String writeCheckinSnapshot(
      JsonNode prev,
      Double overall,
      Double pron,
      Double gram,
      Double fluency,
      Integer turns,
      Integer durationS,
      Integer practiceCount) {
    try {
      com.fasterxml.jackson.databind.node.ObjectNode n = mapper.createObjectNode();
      double oldOverall =
          prev != null && prev.path("overall").isNumber() ? prev.path("overall").asDouble() : -1;
      n.put("overall", maxIfPresent(oldOverall, overall));
      n.put("pron", pron == null ? null : pron);
      n.put("gram", gram == null ? null : gram);
      n.put("fluency", fluency == null ? null : fluency);
      n.put("turns", turns == null ? 0 : turns);
      n.put("duration_s", durationS == null ? 0 : durationS);
      int count =
          practiceCount != null
              ? practiceCount
              : (prev != null && prev.path("practice_count").isIntegralNumber()
                      ? prev.path("practice_count").asInt()
                      : 0)
                  + 1;
      n.put("practice_count", count);
      return mapper.writeValueAsString(n);
    } catch (Exception e) {
      throw new IllegalStateException("打卡快照序列化失败", e);
    }
  }

  private static double maxIfPresent(double base, Double value) {
    return value == null ? base : Math.max(base, value);
  }

  // ------------------------------------------------------------------ S2 · 关注

  @Transactional
  public void follow(Long me, Long targetId) {
    if (me.equals(targetId)) {
      throw new CommunityException(42203, "不能关注自己", HttpStatus.BAD_REQUEST);
    }
    users
        .findById(targetId)
        .orElseThrow(() -> new CommunityException(40402, "用户不存在", HttpStatus.NOT_FOUND));
    if (follows.findByFollowerIdAndFolloweeId(me, targetId).isEmpty()) {
      FollowEntity f = new FollowEntity();
      f.setFollowerId(me);
      f.setFolloweeId(targetId);
      f.setCreatedAt(Instant.now());
      follows.saveAndFlush(f);
    }
  }

  @Transactional
  public void unfollow(Long me, Long targetId) {
    follows.deleteByFollowerIdAndFolloweeId(me, targetId);
  }

  /** 关注列表（+对方是否也关注我 = 互关） */
  @Transactional(readOnly = true)
  public List<FollowSummary> followingList(Long me) {
    List<FollowEntity> rows = follows.findByFollowerIdOrderByCreatedAtDesc(me);
    List<Long> targetIds = rows.stream().map(FollowEntity::getFolloweeId).toList();
    Map<Long, AuthorView> authors = loadAuthors(targetIds);
    Set<Long> backers =
        follows.findByFolloweeIdAndFollowerIdIn(me, targetIds).stream()
            .map(FollowEntity::getFollowerId)
            .collect(Collectors.toSet());
    return rows.stream()
        .map(
            f ->
                new FollowSummary(
                    authors.getOrDefault(f.getFolloweeId(), emptyAuthor(f.getFolloweeId())),
                    f.getCreatedAt().toString(),
                    backers.contains(f.getFolloweeId())))
        .toList();
  }

  /**
   * 推荐关注：候选 = 全库用户分页（排除自己；J-06 收敛：不再全表加载 + 每用户 3 次查询的 3N+1）。 limit 默认 50、上限
   * 100；演示口径：无候选筛选算法（规模增长后按画像/同领域过滤，登记 docs/41 §5）。
   */
  @Transactional(readOnly = true)
  public List<FollowRecommend> recommendations(Long me, int limit) {
    int cap = Math.min(Math.max(limit, 1), 100);
    List<Long> ids =
        users.findAll(PageRequest.of(0, cap)).stream()
            .map(UserEntity::getId)
            .filter(id -> !id.equals(me))
            .toList();
    if (ids.isEmpty()) {
      return List.of();
    }
    // 批量：作者 1 次 + 关注判定 1 次（替代旧实现每用户 2 次作者 + 1 次关注的 3N+1）
    Map<Long, AuthorView> authors = loadAuthors(ids);
    Set<Long> followed =
        follows.findByFollowerIdAndFolloweeIdIn(me, ids).stream()
            .map(FollowEntity::getFolloweeId)
            .collect(Collectors.toSet());
    return ids.stream()
        .map(
            id ->
                new FollowRecommend(
                    authors.getOrDefault(id, emptyAuthor(id)), followed.contains(id)))
        .toList();
  }

  /** 关注流：仅关注作者的新内容（keyset DESC，复用 buildViews 聚合作者/互动态）。 */
  @Transactional(readOnly = true)
  public FeedPage followingFeed(Long me, String cursor, int limit) {
    Cursor c = decodeCursor(cursor);
    int pageSize = clampLimit(limit);
    PageRequest pageable =
        PageRequest.of(0, pageSize + 1, Sort.by(Sort.Direction.DESC, "createdAt", "id"));
    // J-06：空关注快检（不跑 EXISTS 查询）；有关注走相关子查询——不再拼巨型 authorIds IN
    List<PostEntity> rows =
        follows.countByFollowerId(me) == 0
            ? List.of()
            : posts.followingFeed(me, c.ts(), c.id(), pageable);
    boolean hasMore = rows.size() > pageSize;
    List<PostEntity> page = hasMore ? rows.subList(0, pageSize) : rows;
    List<CommunityPostView> views = buildViews(page, me);
    String next = hasMore ? encodeCursor(lastKey(page)) : null;
    return new FeedPage(views, next, hasMore);
  }

  // ------------------------------------------------------------------ S2 · 通知（派生 · mergeKey 聚合）

  private record NotiGroup(
      String key, Long postId, String action, int count, Instant latest, Long latestActorId) {}

  private static final int NOTIFICATION_WINDOW = 50;

  /**
   * 互动通知（docs/38 §5 mergeKey 模板 · 演示窗口 = 近 50 条互动/评论，内存聚合）： like/coin/share 按 (post, action, 当日
   * UTC) 聚合为「actor 等 N 人…」；comment 逐条带内容； 仅本人可见帖、排除自身动作（自赞/自评不通知）；cursor = base64(ts|itemId) 阈值分页。
   */
  @Transactional(readOnly = true)
  public NotificationsPage notifications(Long me, String cursor, int limit) {
    int pageSize = clampLimit(limit);
    List<PostInteractionEntity> inters =
        interactions.findMine(me, PageRequest.of(0, NOTIFICATION_WINDOW));
    List<PostCommentEntity> cmts = comments.findMine(me, PageRequest.of(0, NOTIFICATION_WINDOW));
    inters.removeIf(i -> i.getActorId().equals(me));
    cmts.removeIf(c -> c.getAuthorId().equals(me));

    Set<Long> postIds = new HashSet<>();
    inters.forEach(i -> postIds.add(i.getPostId()));
    cmts.forEach(c -> postIds.add(c.getPostId()));
    Map<Long, PostEntity> postMap =
        posts.findAllById(postIds).stream()
            .collect(Collectors.toMap(PostEntity::getId, Function.identity()));
    Set<Long> actorIds = new HashSet<>();
    inters.forEach(i -> actorIds.add(i.getActorId()));
    cmts.forEach(c -> actorIds.add(c.getAuthorId()));
    Map<Long, AuthorView> actorMap = loadAuthors(new ArrayList<>(actorIds));

    // 聚合 like/coin/share：mergeKey = postId|action|当日UTC
    Map<String, NotiGroup> groups = new LinkedHashMap<>();
    for (PostInteractionEntity i : inters) {
      String key =
          i.getPostId()
              + "|"
              + i.getAction()
              + "|"
              + i.getCreatedAt().atZone(ZoneOffset.UTC).toLocalDate();
      NotiGroup prev = groups.get(key);
      if (prev == null) {
        groups.put(
            key,
            new NotiGroup(key, i.getPostId(), i.getAction(), 1, i.getCreatedAt(), i.getActorId()));
      } else {
        groups.put(
            key,
            new NotiGroup(
                key,
                prev.postId(),
                prev.action(),
                prev.count() + 1,
                prev.latest().isAfter(i.getCreatedAt()) ? prev.latest() : i.getCreatedAt(),
                prev.latest().isAfter(i.getCreatedAt()) ? prev.latestActorId() : i.getActorId()));
      }
    }

    List<NotificationItem> items = new ArrayList<>();
    for (NotiGroup g : groups.values()) {
      items.add(
          new NotificationItem(
              "n|" + g.key(),
              g.action(),
              g.postId(),
              titleOf(postMap.get(g.postId())),
              nicknameOf(actorMap, g.latestActorId()),
              g.count(),
              null,
              g.latest()));
    }
    for (PostCommentEntity c : cmts) {
      items.add(
          new NotificationItem(
              "c|" + c.getId(),
              "comment",
              c.getPostId(),
              titleOf(postMap.get(c.getPostId())),
              nicknameOf(actorMap, c.getAuthorId()),
              1,
              c.getBody(),
              c.getCreatedAt()));
    }

    // 排序：时间倒序，同刻按 itemId 升序（配合阈值游标）
    items.sort(
        Comparator.comparing(NotificationItem::createdAt)
            .reversed()
            .thenComparing(NotificationItem::id));

    // 阈值游标
    CursorThreshold threshold = decodeNotiCursor(cursor);
    List<NotificationItem> filtered = new ArrayList<>();
    for (NotificationItem it : items) {
      if (threshold.ts() == null) {
        filtered.add(it);
        continue;
      }
      int tsCmp = it.createdAt().compareTo(threshold.ts());
      if (tsCmp < 0 || (tsCmp == 0 && it.id().compareTo(threshold.id()) > 0)) {
        filtered.add(it);
      }
    }
    boolean hasMore = filtered.size() > pageSize;
    List<NotificationItem> page = hasMore ? filtered.subList(0, pageSize) : filtered;
    NotificationItem last = page.isEmpty() ? null : page.get(page.size() - 1);
    String next = hasMore && last != null ? encodeNotiCursor(last.createdAt(), last.id()) : null;
    return new NotificationsPage(page, next, hasMore);
  }

  private static String titleOf(PostEntity p) {
    if (p == null) return "内容";
    return KIND_CHECKIN.equals(p.getKind())
        ? "今日打卡"
        : (p.getTitle() != null ? p.getTitle() : p.getBody());
  }

  private static String nicknameOf(Map<Long, AuthorView> actors, Long id) {
    AuthorView a = actors.get(id);
    return a == null ? "有同修" : a.nickname();
  }

  private record CursorThreshold(Instant ts, String id) {}

  private static CursorThreshold decodeNotiCursor(String cursor) {
    if (cursor == null || cursor.isBlank()) {
      return new CursorThreshold(null, null);
    }
    try {
      String raw = new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8);
      String[] parts = raw.split("\\|");
      return new CursorThreshold(Instant.parse(parts[0]), parts[1]);
    } catch (Exception e) {
      throw new CommunityException(42203, "分页游标非法", HttpStatus.BAD_REQUEST);
    }
  }

  private static String encodeNotiCursor(Instant ts, String id) {
    String raw = micro(ts).toString() + "|" + id;
    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
  }

  // ------------------------------------------------------------------ 内部

  /**
   * 唯一键幂等插入：true=本次新增；false=已存在（重复请求返回当前态，不双计）。
   *
   * <p>J-01 起改用 DB 层 {@code ON CONFLICT DO NOTHING} 原子兜底：旧「先查后插 + catch
   * DataIntegrityViolationException」即便捕获冲突，Hibernate 已把当前事务标为 rollback-only， 提交期仍抛
   * UnexpectedRollbackException（真并发下 500 依旧）——冲突路径根本不会走到「返回当前态」。
   */
  private boolean insertInteractionIdempotent(Long actorId, Long postId, String action) {
    return interactions.insertIgnoreConflict(actorId, postId, action, Instant.now()) > 0;
  }

  private PostEntity requireVisible(Long postId) {
    return posts.findVisible(postId).orElseThrow(() -> notFound("内容不存在或已删除"));
  }

  private CommunityException notFound(String message) {
    return new CommunityException(40402, message, HttpStatus.NOT_FOUND);
  }

  private String normalizeDomain(String domain) {
    if (domain == null || domain.isBlank() || "recommend".equals(domain)) {
      return null;
    }
    if (!Set.of("news", "teaching", "overseas").contains(domain)) {
      throw new CommunityException(
          42203, "domain 仅支持 news/teaching/overseas", HttpStatus.BAD_REQUEST);
    }
    return domain;
  }

  private int clampLimit(int limit) {
    return Math.min(Math.max(limit, 1), MAX_LIMIT);
  }

  private List<CommunityPostView> buildViews(List<PostEntity> rows, Long actorId) {
    if (rows.isEmpty()) {
      return List.of();
    }
    List<Long> postIds = rows.stream().map(PostEntity::getId).toList();
    Map<Long, AuthorView> authorMap =
        loadAuthors(rows.stream().map(PostEntity::getAuthorId).toList());
    Set<Long> likedSet = new HashSet<>();
    Set<Long> coinedSet = new HashSet<>();
    if (actorId != null) {
      likes.findByLikerIdAndPostIdIn(actorId, postIds).forEach(l -> likedSet.add(l.getPostId()));
      interactions
          .findByActorIdAndPostIdInAndAction(actorId, postIds, ACTION_COIN)
          .forEach(i -> coinedSet.add(i.getPostId()));
    }
    return rows.stream()
        .map(
            p ->
                toPostView(
                    p,
                    authorMap.getOrDefault(p.getAuthorId(), emptyAuthor(p.getAuthorId())),
                    likedSet.contains(p.getId()),
                    coinedSet.contains(p.getId())))
        .toList();
  }

  private Map<Long, AuthorView> loadAuthors(List<Long> authorIds) {
    Map<Long, UserEntity> userMap =
        users.findAllById(authorIds).stream()
            .collect(Collectors.toMap(UserEntity::getId, Function.identity()));
    // 用 user_id（非 PK）批量取档案：作者 id 是 users.id，findAllById 会命中错误行（2026-09-06 修复）
    Map<Long, UserProfileEntity> profileMap =
        profiles.findByUserIdIn(authorIds).stream()
            .collect(Collectors.toMap(UserProfileEntity::getUserId, Function.identity()));
    Map<Long, AuthorView> out = new HashMap<>();
    for (Long id : authorIds) {
      UserEntity u = userMap.get(id);
      UserProfileEntity p = profileMap.get(id);
      out.putIfAbsent(
          id,
          new AuthorView(
              id,
              u == null ? "未知用户" : u.getNickname(),
              p == null ? null : p.getHandle(),
              p == null ? null : p.getTint(),
              p == null ? "L1" : p.getCefrLevel(),
              p == null ? null : p.getAvatarUrl()));
    }
    return out;
  }

  private AuthorView emptyAuthor(Long id) {
    return new AuthorView(id, "未知用户", null, null, "L1", null);
  }

  private CommunityPostView toPostView(
      PostEntity p, AuthorView author, boolean liked, boolean coined) {
    JsonNode media = parseJson(p.getMedia());
    Double checkinOverall = null;
    Integer checkinPracticeCount = null;
    if (KIND_CHECKIN.equals(p.getKind())) {
      JsonNode snap = parseJson(p.getCheckinSnapshot());
      if (snap != null) {
        JsonNode overall = snap.get("overall");
        JsonNode count = snap.get("practice_count");
        checkinOverall = overall != null && overall.isNumber() ? overall.asDouble() : null;
        checkinPracticeCount = count != null && count.isIntegralNumber() ? count.asInt() : 0;
      }
    }
    return new CommunityPostView(
        p.getId(),
        author,
        p.getKind(),
        p.getDomain(),
        p.getTitle(),
        p.getBody(),
        media,
        p.getCreatedAt(),
        p.getLikeCount(),
        p.getCoinCount(),
        p.getCommentCount(),
        p.getShareCount(),
        liked,
        coined,
        checkinOverall,
        checkinPracticeCount,
        p.getCheckinDate() == null ? null : p.getCheckinDate().toString());
  }

  /**
   * 批量组装评论（J-05）：先收集页内全部 authorId 一次 loadAuthors 得 authorMap， 再逐条组装——替代 toCommentView 逐条 2 查询/条 的
   * N+1（20 条页 ≈41 次往返 → 3 次）。
   */
  private List<CommentView> toCommentViews(List<PostCommentEntity> rows) {
    if (rows.isEmpty()) {
      return List.of();
    }
    Map<Long, AuthorView> authorMap =
        loadAuthors(rows.stream().map(PostCommentEntity::getAuthorId).toList());
    return rows.stream()
        .map(
            c ->
                new CommentView(
                    c.getId(),
                    authorMap.getOrDefault(c.getAuthorId(), emptyAuthor(c.getAuthorId())),
                    c.getBody(),
                    c.getCreatedAt(),
                    c.getReplyToNickname()))
        .toList();
  }

  private CommentView toCommentView(PostCommentEntity c) {
    return toCommentViews(List.of(c)).get(0);
  }

  private JsonNode parseJson(String json) {
    if (json == null || json.isBlank()) {
      return null;
    }
    try {
      return mapper.readTree(json);
    } catch (Exception e) {
      return null;
    }
  }

  private Cursor decodeCursor(String cursor) {
    if (cursor == null || cursor.isBlank()) {
      return new Cursor(null, null);
    }
    try {
      String raw = new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8);
      String[] parts = raw.split("\\|");
      // ISO-8601 全精度 + 微秒归一：DB 时间精度（6 位）与 JVM Instant（9 位）口径对齐，
      // 否则同值比较错位、keyset 重复返回同页（toEpochMilli 截断同理，已弃）
      return new Cursor(micro(Instant.parse(parts[0])), Long.parseLong(parts[1]));
    } catch (Exception e) {
      throw new CommunityException(42203, "分页游标非法", HttpStatus.BAD_REQUEST);
    }
  }

  private String encodeCursor(Cursor c) {
    if (c == null || c.ts() == null || c.id() == null) {
      return null;
    }
    String raw = micro(c.ts()).toString() + "|" + c.id();
    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
  }

  /** 截断到微秒（TIMESTAMP(6) 口径；1 微秒 = 1000 ns——用 %1000，勿用 %1_000_000 那是毫秒）。 */
  private static Instant micro(Instant i) {
    return Instant.ofEpochSecond(i.getEpochSecond(), i.getNano() - i.getNano() % 1_000);
  }

  private Cursor lastKey(List<?> rows) {
    if (rows.isEmpty()) {
      return null;
    }
    Object last = rows.get(rows.size() - 1);
    if (last instanceof PostEntity p) {
      return new Cursor(p.getCreatedAt(), p.getId());
    }
    PostCommentEntity c = (PostCommentEntity) last;
    return new Cursor(c.getCreatedAt(), c.getId());
  }
}
