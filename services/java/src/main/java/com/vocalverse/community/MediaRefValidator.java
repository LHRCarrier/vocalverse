package com.vocalverse.community;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/**
 * 发帖 media 契约校验（docs/47 §4.3 · docs/48 B11）。
 *
 * <p>Java 侧**只做契约校验，不碰文件、不查 Python 的 media_assets 表**（跨服务读表会破坏 docs/10 §3.1
 * 写方矩阵）。因此这里能保证的是：形状合法、条数合法、URL 只能指向本服务的媒体前缀（拒绝外链 —— 防盗链 / SSRF / 存储型 XSS 面）。归属与存在性由 Python
 * 侧兜底：{@code public_id} 不可猜，软删后 GET 返回 40403，前端显示「媒体已删除」占位。
 *
 * <p>不强制 kind 与 media 一致：既有契约允许「kind=video 但无 media」（CommunityApiTest 锁定）， 只校验「若给了 media
 * 则形状/条数/类型合法」。
 */
@Component
public class MediaRefValidator {

  /** 与 Python 侧 sniff 白名单一致（docs/47 §4.1） */
  private static final Set<String> IMAGE_MIMES =
      Set.of("image/jpeg", "image/png", "image/webp", "image/gif");

  private static final Set<String> VIDEO_MIMES = Set.of("video/mp4", "video/webm");
  private static final long MAX_IMAGE_BYTES = 20L * 1024 * 1024;
  private static final long MAX_VIDEO_BYTES = 64L * 1024 * 1024;
  private static final int MAX_DIMENSION = 8192;
  private static final int MAX_DURATION_S = 600;
  private static final int MAX_URL_LEN = 512;

  private final String urlPrefix;
  private final int maxItems;

  public MediaRefValidator(
      @Value("${vocalverse.community.media-url-prefix:/api/v1/media/}") String urlPrefix,
      @Value("${vocalverse.community.media-max-items:9}") int maxItems) {
    this.urlPrefix = urlPrefix;
    this.maxItems = Math.max(1, Math.min(maxItems, 20));
  }

  /** 校验并返回规范化后的 media（无 media 时返回 null）。违规抛 42203。 */
  public JsonNode validate(JsonNode media) {
    if (media == null || media.isNull() || media.isMissingNode()) {
      return null;
    }
    if (!media.isObject()) {
      throw invalid("media 必须是对象");
    }
    String type = text(media, "type");
    if (!"image".equals(type) && !"video".equals(type)) {
      throw invalid("media.type 仅支持 image/video");
    }
    JsonNode items = media.get("items");
    if (items == null || !items.isArray() || items.isEmpty()) {
      throw invalid("media.items 至少 1 条");
    }
    if (items.size() > maxItems) {
      throw invalid("media.items 最多 " + maxItems + " 条");
    }
    if ("video".equals(type) && items.size() != 1) {
      throw invalid("视频帖只能有 1 个媒体项");
    }
    boolean video = "video".equals(type);
    for (JsonNode item : items) {
      validateItem(item, video);
    }
    if (media.hasNonNull("coverUrl")) {
      checkUrl(media.get("coverUrl").asText(), "media.coverUrl");
    }
    if (media.hasNonNull("durationS")) {
      double d = media.get("durationS").asDouble(-1);
      if (d <= 0 || d > MAX_DURATION_S) {
        throw invalid("media.durationS 越界");
      }
    }
    return media;
  }

  private void validateItem(JsonNode item, boolean video) {
    if (item == null || !item.isObject()) {
      throw invalid("media.items 元素必须是对象");
    }
    String url = text(item, "url");
    if (url == null || url.isBlank()) {
      throw invalid("media.items[].url 必填");
    }
    checkUrl(url, "media.items[].url");
    String mime = text(item, "mimeType");
    if (mime != null && !mime.isBlank()) {
      Set<String> allowed = video ? VIDEO_MIMES : IMAGE_MIMES;
      if (!allowed.contains(mime)) {
        throw invalid("media.items[].mimeType 不在白名单");
      }
    }
    long size = item.path("size").asLong(-1);
    if (size > (video ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES)) {
      throw invalid("media.items[].size 越界");
    }
    for (String dim : new String[] {"width", "height"}) {
      long v = item.path(dim).asLong(0);
      if (v < 0 || v > MAX_DIMENSION) {
        throw invalid("media.items[]." + dim + " 越界");
      }
    }
  }

  private void checkUrl(String url, String field) {
    if (url.length() > MAX_URL_LEN) {
      throw invalid(field + " 过长");
    }
    // 只允许本服务签发的媒体 URL：拒绝外链（含协议相对 //evil、data:、javascript:）
    if (!url.startsWith(urlPrefix) || url.length() <= urlPrefix.length()) {
      throw invalid(field + " 只能引用本服务的媒体地址");
    }
    String id = url.substring(urlPrefix.length());
    if (id.contains("/") || id.contains("?") || id.contains("#")) {
      throw invalid(field + " 非法");
    }
  }

  private static String text(JsonNode node, String field) {
    JsonNode v = node.get(field);
    return v == null || !v.isTextual() ? null : v.asText();
  }

  private static CommunityException invalid(String message) {
    return new CommunityException(42203, message, HttpStatus.BAD_REQUEST);
  }
}
