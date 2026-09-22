"""酒馆（TRPG 跑团）域常量（迁移自 ai4u P2-18 实施设计 §10，魔数可追溯）。

红线（对齐 ai4u）：每个常量注释来源与折中理由；调整前先重跑 tests/trpg 全量。
"""

from __future__ import annotations

#: 快照线索注入上限：超出按最后提及时间倒序截断（P2-30 注入预算折中）
SNAPSHOT_CLUE_MAX = 8
#: 快照 Fact 关系子集注入上限（P2-30 修订：防 20 个 NPC 塞爆快照）
SNAPSHOT_FACT_REL_MAX = 6
#: 快照 NPC 状态行上限（docs/56 §C：敌方 HP 进 DM 上下文/面板，按最近提及截断）
SNAPSHOT_NPC_MAX = 6
#: 叙事事实提取频率：每 2 个玩家回合一次（P2-27 战斗一轮内状态变化频繁）
EXTRACT_EVERY_ROUNDS = 2
#: 单次提取最多应用操作数（P2-39 写频率系统级强制）
EXTRACT_MAX_OPS = 3
#: 事实提取输入的最近消息数（P2-27）
EXTRACT_RECENT_MESSAGES = 8
#: 事实 value 长度上限（与 save_memory 同源，静默截断可接受）
FACT_VALUE_MAX_LEN = 200
#: 事实 key 长度上限（规范化 key 由系统生成/校验，超长即非法）
KEY_LEN_MAX = 80
#: 实体名长度上限（key 中段）
ENTITY_NAME_MAX = 60
#: 静态校验悬空窗口：最后提及超出即视为「悬空」（P2-32，约 2 个对话日）
DANGLING_WINDOW_MS = 2 * 24 * 3600 * 1000
#: 场景名长度上限（set_scene 工具入参截断）
SCENE_NAME_MAX = 40
#: 玩家输入长度上限（进 DM 上下文前截断）
QUESTION_MAX = 500
#: 历史消息注入条数（DM 上下文最近 N 条）
HISTORY_MESSAGES = 8
#: DM 生成参数（跑团叙述更长，较陪伴默认上浮；ai4u TRPG_TEMPERATURE/MAX_TOKENS）
DM_TEMPERATURE = 0.8
DM_MAX_TOKENS = 1200
#: 工具调用轮 max_tokens 余量（工具参数 JSON 可能较长，ai4u 取 max(4096, 正文预算)）
TOOL_ROUND_MAX_TOKENS = 4096
#: 工具循环最大轮数（ai4u COMPANION_MAX_ROUNDS=2：round0/1 可调工具，round2 强制正文）
TOOL_MAX_ROUNDS = 2
#: 一次性 DM 回复 TTS 合成的句子上限（防长旁白烧 TTS 配额；超出只回文本）
TTS_MAX_SENTENCES = 10

#: State 类域（系统直写，LLM 提取一律拒绝；P2-22/27 红线 1；docs/56 §2 增 npc）
STATE_DOMAINS = frozenset({"pc", "scene", "npc"})
#: Fact 类域（LLM 提取：rel=人物关系 / quest=任务 / clue=线索；item/encounter 为工具域）
FACT_DOMAINS = frozenset({"rel", "quest", "clue"})

#: 域 → 属性白名单（P2-24 两级白名单之属性层；新增属性必须先登记；docs/56 §2 扩展）
DOMAIN_PROPERTIES: dict[str, tuple[str, ...]] = {
    "pc": ("hp", "location", "inventory"),
    "scene": ("current",),
    "rel": ("attitude", "trust", "status"),
    "quest": ("progress", "kind", "stage", "status"),
    "clue": ("found",),
    "npc": ("hp", "status"),
    "item": ("qty", "owner", "effect", "consumable"),
    "encounter": ("status", "order", "turn", "round"),
}

#: 系统专有属性（docs/56 §2）：LLM 提取（writer="llm"）一律拒写——进度钟/先攻/数量只能是
#: 工具（writer="system"）的算术结果，模型只叙事（DiceFrame 口径：模型讲故事，引擎管状态）。
SYSTEM_ONLY_PROPERTIES = frozenset(
    {"progress", "kind", "stage", "order", "turn", "round", "qty", "owner", "consumable"}
)

#: 域 → 实体 kind（P2-42 实体注册：rel→npc / quest→task / clue→clue / pc→pc；
#: docs/56 §2：item→task（实体登记用）、encounter 不登记实体）
DOMAIN_ENTITY_KIND: dict[str, str] = {
    "rel": "npc",
    "quest": "task",
    "clue": "clue",
    "pc": "pc",
    "scene": "scene",
    "npc": "npc",
    "item": "task",
}

#: 属性 → 值词对照表（P2-35 矛盾检测：摘要出现反向词且提到该实体 → 判定矛盾）
OPPOSITE_PAIRS: tuple[tuple[str, str], ...] = (
    ("友好", "敌对"),
    ("敌意", "友善"),
    ("信任", "警惕"),
    ("成功", "失败"),
    ("完成", "未完成"),
    ("已完成", "进行中"),
    ("进行中", "已完成"),
    ("活着", "死了"),
    ("存活", "死亡"),
)
