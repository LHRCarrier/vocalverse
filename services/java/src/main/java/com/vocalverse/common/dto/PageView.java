package com.vocalverse.common.dto;

import java.util.List;
import org.springframework.data.domain.Page;

/**
 * 分页响应（docs/api envelope.md：data = {items, total, page, page_size}）。
 *
 * <p>page 从 1 计（对外契约），内部 Page.getNumber() 从 0 计，此处转换。
 */
public record PageView<T>(List<T> items, long total, int page, int page_size) {

  public static <T> PageView<T> of(Page<T> source) {
    return new PageView<>(
        source.getContent(), source.getTotalElements(), source.getNumber() + 1, source.getSize());
  }
}
