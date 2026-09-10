package com.vocalverse.console.moderation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.console.audit.AdminAuditLogEntity;
import com.vocalverse.console.audit.AdminAuditLogRepository;
import com.vocalverse.console.audit.AuditService;
import com.vocalverse.console.auth.ConsolePrincipal;
import com.vocalverse.console.rbac.AdminUserEntity;
import com.vocalverse.console.rbac.AdminUserRepository;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 审核域服务（docs/50 §6.2 状态机 + §5.3.8/§5.3.9）。
 *
 * <h2>决定为什么必须是条件 UPDATE</h2>
 *
 * <p>{@link ModerationCaseRepository#decide} 的 SQL 带 {@code WHERE status='pending'}。 若改成「先 {@code
 * findById} 再 {@code setStatus} 再 save」（read-modify-write），两个并发决定在 PG READ COMMITTED 下**都会读到
 * pending、都会写成功**，结果是两个审核员各自看到「我处理了」， 而内容最终状态取决于谁最后提交 —— 这正是 docs/50 §6.2 要求消除的竞态。 条件 UPDATE 把判定下推到
 * DB：第二个事务的行锁等待结束后重读发现 status 已变 → 匹配 0 行 → 46010。
 *
 * <h2>目标写入与状态推进的顺序</h2>
 *
 * <p>先写目标（{@code posts.status='hidden'}）再条件更新工单，两者同一事务： 工单更新 0 行 → 抛 46010 → 整个事务回滚 →
 * <b>目标写入也被撤销</b>。 反过来先更新工单再写目标，若目标写失败（46009）则工单已推进，需要额外补偿，更容易出错。
 */
@Service
public class ModerationService {

  private static final Logger log = LoggerFactory.getLogger(ModerationService.class);

  /** 决定枚举（docs/50 §6.2）。 */
  public enum Decision {
    APPROVE("approve", ModerationCaseEntity.STATUS_APPROVED, null),
    HIDE("hide", ModerationCaseEntity.STATUS_APPROVED, ModerationTargetWriter.STATUS_HIDDEN),
    DELETE("delete", ModerationCaseEntity.STATUS_APPROVED, ModerationTargetWriter.STATUS_DELETED),
    REJECT("reject", ModerationCaseEntity.STATUS_REJECTED, null),
    ESCALATE("escalate", ModerationCaseEntity.STATUS_ESCALATED, null);

    private final String wire;
    private final String nextStatus;
    private final String targetStatus;

    Decision(String wire, String nextStatus, String targetStatus) {
      this.wire = wire;
      this.nextStatus = nextStatus;
      this.targetStatus = targetStatus;
    }

    public String wire() {
      return wire;
    }

    public String nextStatus() {
      return nextStatus;
    }

    /** 对目标表的写入（null = 不动目标）。 */
    public String targetStatus() {
      return targetStatus;
    }

    public static Decision parse(String raw) {
      if (raw == null) {
        throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "decision 不能为空");
      }
      for (Decision d : values()) {
        if (d.wire.equalsIgnoreCase(raw.trim())) {
          return d;
        }
      }
      throw ConsoleException.of(
          ConsoleErrorCodes.INVALID_PARAM, "decision 仅支持 approve|hide|delete|reject|escalate");
    }
  }

  private final ModerationCaseRepository cases;
  private final ModerationReportRepository reports;
  private final ModerationTargetWriter targets;
  private final AuditService audit;
  private final AdminAuditLogRepository auditLogs;
  private final AdminUserRepository adminUsers;
  private final ObjectMapper mapper;

  public ModerationService(
      ModerationCaseRepository cases,
      ModerationReportRepository reports,
      ModerationTargetWriter targets,
      AuditService audit,
      AdminAuditLogRepository auditLogs,
      AdminUserRepository adminUsers,
      ObjectMapper mapper) {
    this.cases = cases;
    this.reports = reports;
    this.targets = targets;
    this.audit = audit;
    this.auditLogs = auditLogs;
    this.adminUsers = adminUsers;
    this.mapper = mapper;
  }

  // ------------------------------------------------------------------ 查询

  @Transactional(readOnly = true)
  public Page<ModerationCaseEntity> list(
      String status, String targetType, Short priority, Long assigneeId, int page, int pageSize) {
    return cases.search(
        blankToNull(status),
        blankToNull(targetType),
        priority,
        assigneeId,
        PageRequest.of(Math.max(0, page - 1), clampPageSize(pageSize)));
  }

  @Transactional(readOnly = true)
  public ModerationCaseEntity require(Long id) {
    return cases
        .findById(id)
        .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "审核单不存在"));
  }

  /** 详情附加信息：目标快照 + 目标当前状态。 */
  @Transactional(readOnly = true)
  public Map<String, Object> describe(ModerationCaseEntity c) {
    Map<String, Object> out = new LinkedHashMap<>();
    out.put("targetExists", targets.exists(c.getTargetType(), c.getTargetId()));
    out.put("targetStatus", targets.currentStatus(c.getTargetType(), c.getTargetId()));
    out.put("targetAuthorId", targets.authorId(c.getTargetType(), c.getTargetId()));
    out.put("snapshot", c.getSnapshot() == null ? null : readJson(c.getSnapshot()));
    return out;
  }

  /** 决定历史 —— 直接来自 {@code admin_audit_logs}（docs/50 §5.3.7「单一审计流」，无独立 moderation_actions 表）。 */
  @Transactional(readOnly = true)
  public List<AdminAuditLogEntity> history(Long caseId) {
    return auditLogs.decisionHistory("moderation_case", String.valueOf(caseId));
  }

  // ------------------------------------------------------------------ 建单

  public record CreateRequest(
      String targetType,
      Long targetId,
      String source,
      String reasonCode,
      Short priority,
      Long assigneeId) {}

  /**
   * 手动建单（docs/50 §10.2 POST /moderation/cases；也是未来接自动送审引擎的入口，§6.2 联动硬点 4）。
   *
   * <h2>锁顺序（避免 reports ⇄ cases 死锁）</h2>
   *
   * <p>本模块固定 **{@code moderation_cases} → {@code moderation_reports}** 的加锁/读取顺序， 两条路径都遵守：
   *
   * <ul>
   *   <li>{@link #create}：先读/插 cases，再（仅首次）读 reports 数快照；
   *   <li>{@link #handleReport}：先读 cases（{@code findOpen}）→ 再更新 reports（{@code reports.handle}）。
   * </ul>
   *
   * <p>反例（原来会死锁的写法）：{@code create} 里反复调 {@code findOpen} 之后又让 {@code buildSnapshot} 再去数 reports，而
   * {@code handleReport} 是「先 update report、再插 case」—— 两条路径顺序相反时， 并发下会形成 {@code cases ←→ reports}
   * 环并抛 {@code 40P01 deadlock detected}。 所以 {@link #handleReport} 走 {@link #insertCase} 直接插单（不重读
   * reports）， 并且计数由调用方传入，保证「先 cases 后 reports」在所有路径上一致。
   *
   * <h2>并发建单</h2>
   *
   * <p>两个请求同时为同一目标建单时，PG 的部分唯一索引 {@code uq_moderation_cases_target_pending} 会拒绝
   * 第二行。这里捕获约束冲突并**返回既有待审单**（幂等），而不是让 {@code DataIntegrityViolationException} 冒泡成 500 ——
   * 用户看到的是「这单已经在队列里了」，这是正确且无害的结果。
   */
  @Transactional
  public ModerationCaseEntity create(ConsolePrincipal principal, CreateRequest req) {
    Validated v = validate(req);
    List<ModerationCaseEntity> open = cases.findOpen(v.targetType(), v.targetId());
    if (!open.isEmpty()) {
      return open.get(0); // 幂等：复用既有待审单
    }
    return insertCase(principal, v, null);
  }

  /** 建单入参校验结果（校验与落库分离，便于复用与测试）。 */
  private record Validated(
      String targetType,
      Long targetId,
      String source,
      String reasonCode,
      short priority,
      Long assigneeId) {}

  private Validated validate(CreateRequest req) {
    String targetType = requireTargetType(req.targetType());
    if (req.targetId() == null) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "targetId 不能为空");
    }
    if (!targets.exists(targetType, req.targetId())) {
      throw ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND);
    }
    String source = req.source() == null ? ModerationCaseEntity.SOURCE_MANUAL : req.source().trim();
    if (!List.of(
            ModerationCaseEntity.SOURCE_AUTO,
            ModerationCaseEntity.SOURCE_REPORT,
            ModerationCaseEntity.SOURCE_MANUAL)
        .contains(source)) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "source 仅支持 auto|report|manual");
    }
    String reasonCode = requireReasonCode(req.reasonCode());
    short priority = req.priority() == null ? (short) 2 : req.priority();
    if (priority < 1 || priority > 3) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "priority 仅支持 1(高)/2(中)/3(低)");
    }
    if (req.assigneeId() != null && adminUsers.findById(req.assigneeId()).isEmpty()) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "assigneeId 对应的管理员不存在");
    }
    return new Validated(
        targetType, req.targetId(), source, reasonCode, priority, req.assigneeId());
  }

  /**
   * 落库建单（**不重读 reports**；{@code reportCount} 由调用方在「先 cases 后 reports」的顺序下取得）。
   *
   * @param reportCount 快照里的举报数；null = 由本方法读一次（仅限没有 reports 写操作参与的路径）
   */
  private ModerationCaseEntity insertCase(
      ConsolePrincipal principal, Validated v, Integer reportCount) {
    Instant now = Instant.now();
    ModerationCaseEntity e = new ModerationCaseEntity();
    e.setTargetType(v.targetType());
    e.setTargetId(v.targetId());
    e.setSource(v.source());
    e.setReasonCode(v.reasonCode());
    e.setPriority(v.priority());
    e.setStatus(ModerationCaseEntity.STATUS_PENDING);
    e.setSnippet(targets.snippet(v.targetType(), v.targetId()));
    e.setSnapshot(buildSnapshot(v.targetType(), v.targetId(), reportCount));
    e.setAssigneeId(v.assigneeId());
    e.setCreatedAt(now);
    e.setUpdatedAt(now);

    ModerationCaseEntity saved;
    try {
      saved = cases.saveAndFlush(e);
    } catch (org.springframework.dao.DataIntegrityViolationException ex) {
      // 并发建单撞 uq_moderation_cases_target_pending → 幂等返回既有单（而非 500）
      ModerationCaseEntity existing =
          cases.findOpen(v.targetType(), v.targetId()).stream().findFirst().orElse(null);
      if (existing != null) {
        return existing;
      }
      throw ConsoleException.of(ConsoleErrorCodes.CASE_STATE_CONFLICT, "该目标已有待处理审核单（并发建单）");
    }

    audit.record(
        principal,
        "moderation.case.create",
        "moderation_case",
        String.valueOf(saved.getId()),
        "建审核单：" + v.targetType() + "#" + v.targetId(),
        detail(
            "targetType", v.targetType(),
            "priority", v.priority(),
            "reasonCode", v.reasonCode(),
            "prevStatus", null,
            "nextStatus", ModerationCaseEntity.STATUS_PENDING));
    return saved;
  }

  /** 指派（docs/50 §10.2 POST /cases/{id}/assign）。终态单 → 46010。{@code assigneeId=null} = 取消认领。 */
  @Transactional
  public ModerationCaseEntity assign(
      ConsolePrincipal principal, Long caseId, Long assigneeId, String note) {
    ModerationCaseEntity before = require(caseId);
    if (assigneeId != null && adminUsers.findById(assigneeId).isEmpty()) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "assigneeId 对应的管理员不存在");
    }
    int rows = cases.assign(caseId, assigneeId, Instant.now());
    if (rows == 0) {
      throw ConsoleException.of(
          ConsoleErrorCodes.CASE_STATE_CONFLICT, "审核单已处于终态，不能指派：" + before.getStatus());
    }
    boolean unassign = assigneeId == null;
    audit.record(
        principal,
        "moderation.case.assign",
        "moderation_case",
        String.valueOf(caseId),
        unassign ? "取消认领审核单" : ("指派审核单给 " + adminName(assigneeId)),
        detail(
            "assigneeId",
            assigneeId,
            "prevStatus",
            before.getStatus(),
            "nextStatus",
            before.getStatus(),
            "before",
            before.getAssigneeId() == null ? null : String.valueOf(before.getAssigneeId()),
            "after",
            assigneeId == null ? null : String.valueOf(assigneeId),
            "note",
            note));
    return require(caseId);
  }

  // ------------------------------------------------------------------ 决定（核心）

  /**
   * 决定（docs/50 §6.2）。
   *
   * <p>审计在**本方法的事务内**写（{@link AuditService#record} 是 MANDATORY）： 决定失败回滚 → 审计也无行；决定成功 → 审计必有行。这是
   * docs/50 §9.3 的不变量。
   *
   * <h2>审计记录的是真实前后状态，不是「我以为的前后状态」</h2>
   *
   * <p>三处如实记录，缺一条审计就会说谎：
   *
   * <ol>
   *   <li><b>审单状态</b>：{@code prevStatus} 取本事务内读到的工单状态；
   *   <li><b>目标状态</b>：{@code targetPrevStatus} 在**写目标之前**读一次（同一事务）， {@code targetNextStatus}
   *       取实际写入的值（或「未改目标」）。只记 {@code decision=hide} 而不记 「posts.status 从 visible 变成
   *       hidden」，事后无法回答「这条内容当时到底可不可见」；
   *   <li><b>并发可见</b>：把读到的 {@code targetPrevStatus} 作为 CAS 的期望值传给条件 UPDATE （见 {@link
   *       ModerationCaseRepository#decide}），目标若已被别人改过则整笔 46010 回滚， 不会出现「审计写着 hidden、库里其实是 deleted」。
   * </ol>
   */
  @Transactional
  public ModerationCaseEntity decide(
      ConsolePrincipal principal, Long caseId, String decisionRaw, String reasonCode, String note) {
    Decision decision = Decision.parse(decisionRaw);
    ModerationCaseEntity before = require(caseId);
    String prevStatus = before.getStatus();

    if (ModerationCaseEntity.STATUS_APPROVED.equals(prevStatus)
        || ModerationCaseEntity.STATUS_REJECTED.equals(prevStatus)
        || ModerationCaseEntity.STATUS_WITHDRAWN.equals(prevStatus)) {
      // 已终态：快路径直接 46010（不必等到 UPDATE 才发现，也让错误更明确）
      throw ConsoleException.of(ConsoleErrorCodes.CASE_STATE_CONFLICT, "审核单状态不允许该动作：" + prevStatus);
    }

    // 目标当前状态（同一事务内读取）→ 作为 CAS 期望值 + 审计的「真实旧值」
    String targetPrevStatus = targets.currentStatus(before.getTargetType(), before.getTargetId());
    String targetNextStatus = null;

    if (decision.targetStatus() != null) {
      if (!targets.supportsHideDelete(before.getTargetType())) {
        // media / direct_message：Java 不是写方（docs/50 §5.4 + docs/06 §10 写方矩阵）→ 拒绝，不静默成功
        throw new ConsoleException(
            ConsoleErrorCodes.INVALID_PARAM,
            "目标类型 "
                + before.getTargetType()
                + " 不支持 Java 侧隐藏/删除：媒体处置请在「媒体库」页面操作（Python 端点，content:media:write），"
                + "私信本期只读。可改用 approve / reject / escalate（仅推进审单状态）。",
            ConsoleErrorCodes.status(ConsoleErrorCodes.INVALID_PARAM));
      }
      // hide 与 delete **互相不可复活**：对已 deleted 的内容下 hide（或反之）必须被拒。
      // 否则一个「隐藏」决定会把更严的「删除」降级回可恢复状态 —— 审核严重性被静默降低，
      // 而且库里看不出发生过（审计只记 decision=hide）。
      if (!decision.targetStatus().equals(targetPrevStatus)
          && (ModerationTargetWriter.STATUS_DELETED.equals(targetPrevStatus)
              || ModerationTargetWriter.STATUS_HIDDEN.equals(targetPrevStatus))) {
        throw ConsoleException.of(
            ConsoleErrorCodes.CASE_STATE_CONFLICT,
            "目标当前为 "
                + targetPrevStatus
                + "，不允许改为 "
                + decision.targetStatus()
                + "（隐藏/删除互相不可复活；如需恢复请走对应的恢复流程）");
      }
      if (decision.targetStatus().equals(targetPrevStatus)) {
        // 目标已是该状态 → 幂等成功（docs/50 §6.2「目标已 hidden → 幂等成功」），不重复写
        targetNextStatus = targetPrevStatus;
      } else {
        targets.applyStatus(before.getTargetType(), before.getTargetId(), decision.targetStatus());
        targetNextStatus = decision.targetStatus();
      }
    }

    // 条件 UPDATE：rowsAffected==0 → 该单已处于终态 / 已被并发处理 → 46010，整个事务回滚（目标写入一并撤销）
    // 注意：**不再传目标状态作为 CAS 期望值**——那是两个查询期常量的比较，既不成立又会让 Hibernate
    // 报 `Unknown data type: "?"`（见 ModerationCaseRepository.decide 的说明）。目标层的并发保护由
    // 上面「写目标之前读一次 + 已是 hidden/deleted 时显式拒绝」承担。
    int rows =
        cases.decide(
            caseId,
            decision.nextStatus(),
            principal == null ? null : principal.adminUserId(),
            note,
            before.getPriority(),
            Instant.now());
    if (rows == 0) {
      throw ConsoleException.of(ConsoleErrorCodes.CASE_STATE_CONFLICT, "审核单已被并发处理或目标状态已变更，请刷新后重试");
    }

    String resolvedReason =
        reasonCode == null || reasonCode.isBlank() ? before.getReasonCode() : reasonCode;
    audit.record(
        principal,
        "moderation.decide",
        "moderation_case",
        String.valueOf(caseId),
        "审核决定 " + decision.wire() + "：" + before.getTargetType() + "#" + before.getTargetId(),
        detail(
            "decision", decision.wire(),
            "prevStatus", prevStatus,
            "nextStatus", decision.nextStatus(),
            "reasonCode", resolvedReason,
            "note", note,
            "targetType", before.getTargetType(),
            // 目标的真实前后状态（审计不得与 posts.status 实际值不一致）
            "status", targetPrevStatus,
            "before", targetPrevStatus,
            "after", targetNextStatus));
    log.info(
        "审核决定 caseId={} decision={} target={}#{} {}→{} by={}",
        caseId,
        decision.wire(),
        before.getTargetType(),
        before.getTargetId(),
        targetPrevStatus,
        targetNextStatus,
        principal == null ? "-" : principal.username());
    return require(caseId);
  }

  // ------------------------------------------------------------------ 举报

  @Transactional(readOnly = true)
  public Page<ModerationReportEntity> listReports(
      String status, String targetType, int page, int pageSize) {
    return reports.search(
        blankToNull(status),
        blankToNull(targetType),
        PageRequest.of(Math.max(0, page - 1), clampPageSize(pageSize)));
  }

  public record HandleRequest(String action, Long caseId, String note) {}

  /**
   * 审计动作名与原因码的**唯一真源**（docs/50 §5.3.7 / §5.3.8）。
   *
   * <p>控制台前端按这些字面量过滤（{@code moderation.decide} / {@code moderation.case.assign} / {@code
   * moderation.case.create} / {@code moderation.report.handle}；原因码 {@code
   * spam|abuse|porn|violence|politics|ad|copyright|misinfo|other}）。 集中成常量并由 {@code GET
   * /moderation/contract} 暴露，是为了让「前端写死的字面量」与「后端真写的值」 有**可对账的出处** ——
   * 否则任一方改字面量都是一次静默失效（前端筛不到、页面空白，但不报错）。
   */
  public static final List<String> AUDIT_ACTIONS =
      List.of(
          "moderation.decide",
          "moderation.case.assign",
          "moderation.case.create",
          "moderation.report.handle");

  /** 原因码枚举（docs/50 §5.3.8）：控制台下拉框与后端校验共用同一份清单。 */
  public static final List<String> REASON_CODES =
      List.of(
          "spam", "abuse", "porn", "violence", "politics", "ad", "copyright", "misinfo", "other");

  /**
   * 处理举报（docs/50 §10.2 POST /reports/{id}/handle；action ∈ accept|reject|duplicate）。
   *
   * <p>{@code accept} 时**创建/复用**审核单并回填 {@code case_id}：举报的终点是审核单， 只有这样才能让「举报 → 处置 →
   * 留痕」形成一条链（docs/50 §5.3.9 的 {@code case_id} 就是这个用途）。
   *
   * <p><b>46015 vs 46010 的分工</b>：46015 是「举报**入库**时已存在同举报人+同目标的待处理记录」（幂等， 回传既有 {@code caseId}，见
   * {@link #createReport}）；而处理（handle）本身重复 = 状态已非 pending → 46010。
   */
  @Transactional
  public ModerationReportEntity handleReport(
      ConsolePrincipal principal, Long reportId, HandleRequest req) {
    ModerationReportEntity before =
        reports
            .findById(reportId)
            .orElseThrow(() -> ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND, "举报不存在"));
    if (!ModerationReportEntity.STATUS_PENDING.equals(before.getStatus())) {
      throw ConsoleException.of(
          ConsoleErrorCodes.CASE_STATE_CONFLICT, "举报已处理：" + before.getStatus());
    }
    String action = req == null || req.action() == null ? "" : req.action().trim();
    String nextStatus =
        switch (action) {
          case "accept" -> ModerationReportEntity.STATUS_ACCEPTED;
          case "reject" -> ModerationReportEntity.STATUS_REJECTED;
            // 「判重」= 这条举报与另一条重复：状态写 duplicate，并回填被重复举报所属的审单
          case "duplicate" -> ModerationReportEntity.STATUS_DUPLICATE;
          default ->
              throw ConsoleException.of(
                  ConsoleErrorCodes.INVALID_PARAM, "action 仅支持 accept|reject|duplicate");
        };

    Long linkedCaseId = req == null ? null : req.caseId();
    int openCount = cases.findOpen(before.getTargetType(), before.getTargetId()).size();
    if ("accept".equals(action)) {
      List<ModerationCaseEntity> open =
          cases.findOpen(before.getTargetType(), before.getTargetId());
      if (!open.isEmpty()) {
        linkedCaseId = open.get(0).getId();
      } else if (linkedCaseId == null) {
        // 锁顺序：先 cases（上面已读）→ 再 reports（下面的 handle）。这里走 insertCase 直接插单，
        // 不再重读 reports，避免 create() 内部再查一次造成 cases/reports 交叉加锁（见 create 的锁顺序说明）。
        ModerationCaseEntity created =
            insertCase(
                principal,
                new Validated(
                    before.getTargetType(),
                    before.getTargetId(),
                    ModerationCaseEntity.SOURCE_REPORT,
                    before.getReasonCode(),
                    (short) 2,
                    null),
                openCount);
        linkedCaseId = created.getId();
      } else if (cases.findById(linkedCaseId).isEmpty()) {
        throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "caseId 不存在：" + linkedCaseId);
      }
    } else if ("duplicate".equals(action) && linkedCaseId == null) {
      // 「判重」的语义是「这条举报与另一条重复」——所以**必须**指向那条被重复的举报所属的审核单，
      // 否则 duplicate 只是把状态改掉、不产生任何关联。取同一目标下最早的一条其他举报作为重复源。
      linkedCaseId =
          reports
              .findFirstByTargetTypeAndTargetIdOrderByIdAsc(
                  before.getTargetType(), before.getTargetId())
              .filter(other -> !other.getId().equals(reportId))
              .map(ModerationReportEntity::getCaseId)
              .orElse(null);
      if (linkedCaseId == null) {
        // 同目标下没有别的举报可判重 → 该动作不适用，明确报错而不是写一个无意义的 duplicate 状态
        throw ConsoleException.of(
            ConsoleErrorCodes.INVALID_PARAM, "无法判重：同一目标下没有其他举报记录可关联（若确属重复，请用 reject 并说明）");
      }
    }

    int rows =
        reports.handle(
            reportId,
            nextStatus,
            principal == null ? null : principal.adminUserId(),
            linkedCaseId,
            Instant.now());
    if (rows == 0) {
      throw ConsoleException.of(ConsoleErrorCodes.CASE_STATE_CONFLICT, "举报已被并发处理");
    }

    audit.record(
        principal,
        "moderation.report.handle",
        "moderation_report",
        String.valueOf(reportId),
        "处理举报：" + action,
        detail(
            "decision",
            action,
            "prevStatus",
            before.getStatus(),
            "nextStatus",
            nextStatus,
            "caseId",
            linkedCaseId,
            "reasonCode",
            before.getReasonCode(),
            "note",
            req == null ? null : req.note()));
    return reports.findById(reportId).orElseThrow();
  }

  /**
   * 举报入库（本期由控制台/测试调用；C 端举报入口属 Python 侧职责，登记为已知缺口）。
   *
   * <p>46015：同举报人对同目标已有待处理举报 → 幂等返回既有 {@code caseId}（docs/50 §10.4）。
   */
  @Transactional
  public ModerationReportEntity createReport(
      Long reporterUserId, String targetType, Long targetId, String reasonCode, String detailText) {
    if (reporterUserId == null) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "reporterUserId 不能为空");
    }
    String tt = requireTargetType(targetType);
    if (targetId == null) {
      throw ConsoleException.of(ConsoleErrorCodes.INVALID_PARAM, "targetId 不能为空");
    }
    if (!targets.exists(tt, targetId)) {
      throw ConsoleException.of(ConsoleErrorCodes.TARGET_NOT_FOUND);
    }
    List<ModerationReportEntity> pending = reports.findPending(reporterUserId, tt, targetId);
    if (!pending.isEmpty()) {
      ModerationReportEntity existing = pending.get(0);
      Long caseId =
          existing.getCaseId() != null
              ? existing.getCaseId()
              : cases.findOpen(tt, targetId).stream()
                  .findFirst()
                  .map(ModerationCaseEntity::getId)
                  .orElse(null);
      throw ConsoleException.of(
          ConsoleErrorCodes.REPORT_DUPLICATE,
          "举报已存在待处理记录",
          caseId == null
              ? Map.of("reportId", existing.getId())
              : Map.of("caseId", caseId, "reportId", existing.getId()));
    }
    Instant now = Instant.now();
    ModerationReportEntity e = new ModerationReportEntity();
    e.setReporterUserId(reporterUserId);
    e.setTargetType(tt);
    e.setTargetId(targetId);
    e.setReasonCode(requireReasonCode(reasonCode));
    e.setDetail(
        detailText == null ? null : detailText.substring(0, Math.min(500, detailText.length())));
    e.setStatus(ModerationReportEntity.STATUS_PENDING);
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return reports.save(e);
  }

  /**
   * 队列统计 / 看板数据源（docs/50 §10.2 GET /moderation/stats）。
   *
   * <p><b>形状由控制台契约反推</b>（前端已按这个形状渲染，扁平 map 会让审核工作台整页空白）：
   *
   * <pre>
   * {
   *   pending, escalated, approvedToday, rejectedToday,
   *   trend:     [{date, pending, approved, rejected}],   // 近 days 天，逐日
   *   decisions: [{decision, count}],                    // 窗口内决定构成
   *   // 兼容/补充字段（不删，避免破坏已有消费方）
   *   total, approved, rejected, withdrawn, byStatus,
   *   reportsPending, reportsAccepted, reportsRejected, reportsDuplicate, days
   * }
   * </pre>
   *
   * <p>{@code trend} 的 {@code pending} 是**当日累计待办**（当日结束时该窗口内仍未决定的建单数）， 而不是「当日新建数」——
   * 看板要回答的是「那天积压了多少」，不是「那天来了多少」。 两个数差别很大：只给新建数会让积压完全不可见。
   *
   * @param days 回溯天数，钳制在 1..90（防止一次请求把全表拉出来）
   */
  @Transactional(readOnly = true)
  public Map<String, Object> stats(int days) {
    int window = Math.min(Math.max(days, 1), 90);
    java.time.LocalDate today = java.time.LocalDate.now(java.time.ZoneOffset.UTC);
    java.time.LocalDate from = today.minusDays(window - 1L);
    Instant since = from.atStartOfDay(java.time.ZoneOffset.UTC).toInstant();

    // ── 逐日分桶（Java 侧，方言无关；见 ModerationCaseRepository.statsRows 的说明）
    Map<java.time.LocalDate, int[]> perDay = new LinkedHashMap<>();
    for (int i = 0; i < window; i++) {
      perDay.put(
          from.plusDays(i), new int[] {0, 0, 0, 0}); // [created, approved, rejected, pendingEnd]
    }
    for (Object[] row : cases.statsRows(since)) {
      Instant createdAt = toInstant(row[0]);
      Instant decidedAt = toInstant(row[1]);
      String status = row[2] == null ? null : String.valueOf(row[2]);
      if (createdAt != null) {
        java.time.LocalDate d = createdAt.atZone(java.time.ZoneOffset.UTC).toLocalDate();
        int[] bucket = perDay.get(d);
        if (bucket != null) {
          bucket[0]++;
          // 建单当刻即计入「当日结束时仍待办」，若同日已决定则在下面被减掉
          bucket[3]++;
        }
      }
      if (decidedAt != null) {
        java.time.LocalDate d = decidedAt.atZone(java.time.ZoneOffset.UTC).toLocalDate();
        int[] bucket = perDay.get(d);
        if (bucket != null) {
          if (ModerationCaseEntity.STATUS_APPROVED.equals(status)) {
            bucket[1]++;
          } else if (ModerationCaseEntity.STATUS_REJECTED.equals(status)) {
            bucket[2]++;
          }
        }
      }
    }

    List<Map<String, Object>> trend = new java.util.ArrayList<>(window);
    List<Map<String, Object>> decisions = new java.util.ArrayList<>();
    int approvedInWindow = 0;
    int rejectedInWindow = 0;
    for (Map.Entry<java.time.LocalDate, int[]> e : perDay.entrySet()) {
      int[] b = e.getValue();
      approvedInWindow += b[1];
      rejectedInWindow += b[2];
      Map<String, Object> point = new LinkedHashMap<>();
      point.put("date", e.getKey().toString());
      point.put("created", b[0]);
      // 当日结束后仍未决定的建单数（下界：跨窗口之前建单、窗口内未决定的不计入）
      point.put("pending", Math.max(0, b[3] - b[1] - b[2]));
      point.put("approved", b[1]);
      point.put("rejected", b[2]);
      trend.add(point);
    }
    decisions.add(Map.of("decision", "approved", "count", approvedInWindow));
    decisions.add(Map.of("decision", "rejected", "count", rejectedInWindow));
    decisions.add(
        Map.of(
            "decision",
            "escalated",
            "count",
            cases.countByStatus(ModerationCaseEntity.STATUS_ESCALATED)));
    decisions.add(
        Map.of(
            "decision",
            "withdrawn",
            "count",
            cases.countByStatus(ModerationCaseEntity.STATUS_WITHDRAWN)));

    java.time.LocalDate todayDate = today;
    int approvedToday = perDay.containsKey(todayDate) ? perDay.get(todayDate)[1] : 0;
    int rejectedToday = perDay.containsKey(todayDate) ? perDay.get(todayDate)[2] : 0;

    long pending = cases.countByStatus(ModerationCaseEntity.STATUS_PENDING);
    long escalated = cases.countByStatus(ModerationCaseEntity.STATUS_ESCALATED);
    long approved = cases.countByStatus(ModerationCaseEntity.STATUS_APPROVED);
    long rejected = cases.countByStatus(ModerationCaseEntity.STATUS_REJECTED);
    long withdrawn = cases.countByStatus(ModerationCaseEntity.STATUS_WITHDRAWN);

    Map<String, Object> byStatus = new LinkedHashMap<>();
    for (Object[] row : cases.countGroupByStatus()) {
      byStatus.put(String.valueOf(row[0]), row[1]);
    }

    Map<String, Object> out = new LinkedHashMap<>();
    // ── 控制台契约字段（顺序即展示顺序）
    out.put("pending", pending);
    out.put("escalated", escalated);
    out.put("approvedToday", approvedToday);
    out.put("rejectedToday", rejectedToday);
    out.put("trend", trend);
    out.put("decisions", decisions);
    // ── 兼容/补充字段
    out.put("days", window);
    out.put("total", cases.count());
    out.put("approved", approved);
    out.put("rejected", rejected);
    out.put("withdrawn", withdrawn);
    out.put("byStatus", byStatus);
    out.put("reportsPending", reports.countByStatus(ModerationReportEntity.STATUS_PENDING));
    out.put("reportsAccepted", reports.countByStatus(ModerationReportEntity.STATUS_ACCEPTED));
    out.put("reportsRejected", reports.countByStatus(ModerationReportEntity.STATUS_REJECTED));
    out.put("reportsDuplicate", reports.countByStatus(ModerationReportEntity.STATUS_DUPLICATE));
    return out;
  }

  /** 原生/JPQL 投影的时间列归一（PG 给 Instant、H2 给 OffsetDateTime/Timestamp）。 */
  private static Instant toInstant(Object raw) {
    if (raw == null) {
      return null;
    }
    if (raw instanceof Instant i) {
      return i;
    }
    if (raw instanceof java.time.OffsetDateTime odt) {
      return odt.toInstant();
    }
    if (raw instanceof java.sql.Timestamp ts) {
      return ts.toInstant();
    }
    if (raw instanceof java.time.LocalDateTime ldt) {
      return ldt.toInstant(java.time.ZoneOffset.UTC);
    }
    return null;
  }

  // ------------------------------------------------------------------ 内部

  /**
   * 送审快照（docs/50 §5.3.8：{@code
   * {authorId,authorHandle,domain,kind,mediaPublicIds,postId,reportCount}}）。
   */
  private String buildSnapshot(String targetType, Long targetId, Integer reportCount) {
    Map<String, Object> snap = new LinkedHashMap<>();
    snap.put("kind", targetType);
    snap.put("targetId", targetId);
    snap.put("authorId", targets.authorId(targetType, targetId));
    if (ModerationCaseEntity.TARGET_COMMENT.equals(targetType)) {
      snap.put("postId", targets.comment(targetId).map(c -> c.getPostId()).orElse(null));
    } else if (ModerationCaseEntity.TARGET_POST.equals(targetType)) {
      snap.put("postId", targetId);
    }
    // reportCount 由调用方传入时不再回查 reports（锁顺序：cases → reports）
    snap.put(
        "reportCount",
        reportCount != null ? reportCount : cases.countOpenForTarget(targetType, targetId));
    try {
      return mapper.writeValueAsString(snap);
    } catch (Exception e) {
      log.warn("审核单快照序列化失败，已置空：{}", e.getMessage());
      return null;
    }
  }

  private Object readJson(String raw) {
    try {
      return mapper.readTree(raw);
    } catch (Exception e) {
      return raw;
    }
  }

  private String adminName(Long adminUserId) {
    return adminUsers
        .findById(adminUserId)
        .map(AdminUserEntity::getUsername)
        .orElse("#" + adminUserId);
  }

  private static String requireTargetType(String raw) {
    String t = raw == null ? "" : raw.trim();
    if (!List.of(
            ModerationCaseEntity.TARGET_POST,
            ModerationCaseEntity.TARGET_COMMENT,
            ModerationCaseEntity.TARGET_MEDIA,
            ModerationCaseEntity.TARGET_DIRECT_MESSAGE)
        .contains(t)) {
      throw ConsoleException.of(
          ConsoleErrorCodes.INVALID_PARAM, "targetType 仅支持 post|comment|media|direct_message");
    }
    return t;
  }

  private static String requireReasonCode(String raw) {
    String r = raw == null ? "" : raw.trim();
    if (!REASON_CODES.contains(r)) {
      throw ConsoleException.of(
          ConsoleErrorCodes.INVALID_PARAM,
          "reasonCode 仅支持 spam|abuse|porn|violence|politics|ad|copyright|misinfo|other");
    }
    return r;
  }

  private static int clampPageSize(int pageSize) {
    return Math.min(Math.max(pageSize, 1), 100);
  }

  private static String blankToNull(String s) {
    return s == null || s.isBlank() ? null : s;
  }

  /** 有序 detail 构造（键必须在 {@code AuditFieldAllowlist} 内，否则会被静默丢弃并计数）。 */
  private static Map<String, Object> detail(Object... kv) {
    Map<String, Object> m = new LinkedHashMap<>();
    for (int i = 0; i + 1 < kv.length; i += 2) {
      m.put(String.valueOf(kv[i]), kv[i + 1]);
    }
    return m.isEmpty() ? null : m;
  }
}
