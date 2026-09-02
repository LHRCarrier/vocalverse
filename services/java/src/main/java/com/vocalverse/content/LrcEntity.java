package com.vocalverse.content;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 逐句歌词（**Java 写**；逐句评分唯一真源，docs/10 §4.3）。
 *
 * <p>编辑方式为「整首重写」：删旧插新（seq 1..n 重排）→ song_pitch_refs 随 lrc_id 级联删除 （Python 侧补提取）；source 须与所属
 * songs.source 一致（docs/11 Q-B19 冗余审计）。
 */
@Entity
@Table(name = "lrc")
public class LrcEntity {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "song_id", nullable = false)
  private Long songId;

  @Column(nullable = false)
  private Integer seq;

  @Column(name = "offset_ms", nullable = false)
  private Long offsetMs;

  @Column(name = "end_offset_ms")
  private Long endOffsetMs;

  /** 列名是 text（与模块级无冲突，Java 侧无遮蔽问题）；属性命名保留语义。 */
  @Column(name = "text", nullable = false)
  private String lineText;

  @Column(nullable = false, length = 32)
  private String source;

  @Column(name = "created_at", nullable = false)
  private Instant createdAt;

  public Long getId() {
    return id;
  }

  public Long getSongId() {
    return songId;
  }

  public void setSongId(Long songId) {
    this.songId = songId;
  }

  public Integer getSeq() {
    return seq;
  }

  public void setSeq(Integer seq) {
    this.seq = seq;
  }

  public Long getOffsetMs() {
    return offsetMs;
  }

  public void setOffsetMs(Long offsetMs) {
    this.offsetMs = offsetMs;
  }

  public Long getEndOffsetMs() {
    return endOffsetMs;
  }

  public void setEndOffsetMs(Long endOffsetMs) {
    this.endOffsetMs = endOffsetMs;
  }

  public String getLineText() {
    return lineText;
  }

  public void setLineText(String lineText) {
    this.lineText = lineText;
  }

  public String getSource() {
    return source;
  }

  public void setSource(String source) {
    this.source = source;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(Instant createdAt) {
    this.createdAt = createdAt;
  }
}
