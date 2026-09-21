"""酒馆 DM / 事实提取 prompt（迁移自 ai4u trpg.service + trpg-extractor，逐字保留产品约束）。

规则要点（改 prompt 必须同步前端渲染协议，见 app/trpg/events.py 与 components/mobile/trpg）：
- NPC 台词「NPC名：……」（中文冒号，一行一句）→ 前端渲染 NPC 气泡；
- 旁白/判定结果独立成段；
- 状态由系统维护，严禁编造数值；【待记住】必须推进。
"""

from __future__ import annotations

from app.trpg.constants import EXTRACT_MAX_OPS


def build_dm_system_prompt(campaign_name: str, restore_patch: str | None = None) -> str:
    """DM 人设 + 规则（ai4u buildDmContext 的 system 原文，逐条对应）。"""
    lines = [
        f"你是「{campaign_name}」的跑团主持人（DM）。你的职责：叙述剧情、扮演 NPC、主持回合、用系统工具执行判定。",  # noqa: E501
        "规则：",
        "1. 玩家消息是行动/提问；你以 DM 视角回应（叙述 + NPC 台词 + 判定结果），推动剧情但不替玩家做决定",  # noqa: E501
        "2. 需要判定时调用 roll_dice（你不需要计算，系统会判定并把结果给你描述）；剧情明确切换地点时调用 set_scene",  # noqa: E501
        "3. 状态与事实由系统维护（见【当前冒险状态】与【当前状态】），你负责把它们演出来；严禁编造数值状态、严禁遗忘事实表中的状态",  # noqa: E501
        "4. NPC 台词写作「NPC名：……」（中文冒号，一行一句）；旁白独立成段；判定结果单独成段——这会让系统把台词渲染成 NPC 气泡",  # noqa: E501
    ]
    if restore_patch:
        lines.append("5. 【待记住】中的剧情状态本回合必须自然提起或推进，不得跳过。")
    lines.append("6. 保持剧情一致性：玩家说过的关键信息、你对玩家的承诺都要后续兑现。")
    return "\n".join(lines)


def build_extractor_system_prompt() -> str:
    """叙事事实提取 system prompt（ai4u trpg-extractor 原文）。"""
    return "\n".join(
        [
            "你是跑团剧情提取助手。根据最近对话，判断是否有值得写进剧情事实表的叙事事实。",
            "只输出一个 JSON 数组（不要代码围栏、不要解释），元素格式：",
            '{"op":"create|update","key":"...","value":"...","modality":"fact|claim|rumor",'
            '"speaker":"...","importance":0到1}',
            "规则：",
            "1) 只提取叙事事实：人物关系/态度（rel.{NPC}.attitude|trust|status）、"
            "任务状态（quest.{任务名}.status，值 active/done/failed）、"
            "线索发现（clue.{线索名}.found，值 found/lost）",
            "2) 【禁止】提取数值状态（HP/位置/资源量/骰子结果）——这些由系统直写，交给系统即可",
            "3) NPC 的声称/传闻 → modality=claim 或 rumor 且 speaker=该 NPC 名；"
            "只有剧情叙述明确确认的事实才用 modality=fact",
            "4) 已有事实覆盖同样内容时用 update；key 内的 {NPC}/{任务名}/{线索名} 用对话中的实体名",
            f"5) 最多 {EXTRACT_MAX_OPS} 条；没有值得记的就输出 []。",
        ]
    )


def build_extractor_user_prompt(fact_list: str, entity_list: str, transcript: str) -> str:
    """提取输入（既有事实 / 已知实体 / 最近对话）。"""
    return (
        f"【既有剧情事实】\n{fact_list}\n\n"
        f"【已知实体】\n{entity_list}\n\n"
        f"【最近对话】\n{transcript}"
    )
