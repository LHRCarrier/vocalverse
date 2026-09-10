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
   * <p>注意 JPQL 里 {@code :kind is null or t.kind = :kind} 的写法与 status 同款： H2 与 PG
   * 都能推断出参数类型（这是既有已验证的写法，docs/37 §9「PG 未类型化 NULL」族里 出问题的是**完全无类型提示**的参数，这里 {@code t.kind = :kind}
   * 提供了类型）。
   */
  @Query(
      "select t from TicketEntity t "
          + "where (:status is null or t.status = :status) "
          + "and (:kind is null or t.kind = :kind) "
          + "order by t.id desc")
  Page<TicketEntity> search(
      @Param("status") String status, @Param("kind") String kind, Pageable pageable);
}
