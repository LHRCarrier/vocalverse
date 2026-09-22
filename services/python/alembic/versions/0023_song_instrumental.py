"""songs.instrumental_url：伴奏轨（跟唱时播放 · 2026-09-22）

背景：用户口径「原唱是给用户学习、用来听的；伴奏指的是用户在唱的时候的伴奏音乐，
没有伴奏怎么唱」。此前跟唱录音前会停掉参考音（防外放被麦克风录进评分），面板里也没有
任何伴奏概念。本列存 Demucs 分离出的 **no_vocals 伴奏轨**（`local/_make_songs_singable.py`
生成，落 `data/audio/demo_<slug>_instrumental.wav`），前端在录音期间播放它。

口径：
- **纯展示/播放字段**（可空、无默认值、不参与评分与参考旋律提取——提取仍走
  `vocal_ref_url`）；历史行 NULL，前端无伴奏轨时回退「无伴奏」；
- 长度 512 对齐 audio_url/vocal_ref_url/cover_url；
- 写入方：本地演示脚本（Python）；正式链路若上架伴奏轨，仍应走 Java（docs/10 §3 单写方纪律）。

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("songs", sa.Column("instrumental_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("songs", "instrumental_url")
