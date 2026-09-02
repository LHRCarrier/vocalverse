package com.vocalverse.ticket;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TicketRepository extends JpaRepository<TicketEntity, Long> {

  List<TicketEntity> findByUserIdOrderByIdDesc(Long userId);

  @Query(
      "select t from TicketEntity t where (:status is null or t.status = :status) order by t.id desc")
  Page<TicketEntity> search(@Param("status") String status, Pageable pageable);
}
