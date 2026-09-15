package com.vocalverse.ticket;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TicketRepository extends JpaRepository<TicketEntity, Long> {

  List<TicketEntity> findByUserIdOrderByIdDesc(Long userId);

  /**
   * 管理侧分页：status / kind 均可空过滤，按 id 倒序（新建在前）。
   *
   * <p>2026-09-10：{@code kind} 过滤是**控制台新增**（退役旧管理端后，控制台是该表唯一 HTTP 面）。 旧签名 {@code search(status,
   * pageable)} 已删除 —— 它的唯一调用方是已退役的 {@code AdminTicketController}，留着会变成「无人调用但仍需维护」的死代码。
   *
   * <p><b>2026-09-10 更正</b>：本方法原先的注释说"`{@code :kind is null or t.kind = :kind}` H2 与 PG
   * 都能推断出参数类型"—— 那只对**字符串**参数碰巧成立。真 PG 实测同一写法在 ①**时间戳**参数（{@code could not determine data type of
   * parameter $N}）与 ②**{@code concat}/{@code ||} 里的参数**（被解析成 bytea → {@code function lower(bytea)
   * does not exist}） 两种情形下**必然失败**，且 H2 全绿（测试抓不到）。 现在全仓统一给空值判断加 {@code cast}：类型显式、语义不变、不再依赖"碰巧能推断"。
   */
  @Query(
      "select t from TicketEntity t "
          + "where (cast(:status as string) is null or t.status = :status) "
          + "and (cast(:kind as string) is null or t.kind = :kind) "
          + "order by t.id desc")
  Page<TicketEntity> search(
      @Param("status") String status, @Param("kind") String kind, Pageable pageable);
}
