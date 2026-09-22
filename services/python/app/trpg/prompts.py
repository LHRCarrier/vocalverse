"""酒馆 DM / 事实提取 prompt（迁移自 ai4u trpg.service + trpg-extractor，逐字保留产品约束）。

规则要点（改 prompt 必须同步前端渲染协议，见 app/trpg/events.py 与 components/mobile/trpg）：
- NPC 台词「NPC名：……」（中文冒号，一行一句）→ 前端渲染 NPC 气泡；
- 旁白/判定结果独立成段；
- 状态由系统维护，严禁编造数值；【待记住】必须推进。
"""

from __future__ import annotations

from app.trpg.constants import EXTRACT_MAX_OPS


def build_dm_system_prompt(
    campaign_name: str, restore_patch: str | None = None, lang: str = "zh"
) -> str:
    """DM 人设 + 规则（ai4u buildDmContext 的 system 原文，逐条对应）。

    ``lang``：DM **输出语言**（zh=中文叙述 / en=English narration；docs/52 §12.2）——
    玩家输入语言不限，规则与 NPC 台词格式（「名：……」）保持中文冒号以兼容前端分段协议。
    """
    lines = [
        f"你是「{campaign_name}」的跑团主持人（DM）。"  # noqa: E501
        "你的职责：叙述剧情、扮演 NPC、主持回合、用系统工具执行判定。",
    ]
    if lang == "en":
        lines.append(
            "【语言规则·最高优先级】你的全部输出——旁白、NPC 台词、判定说明、系统提示——必须使用"
            "自然的英文，**无论玩家用何种语言输入**（玩家的中文只是行动描述，不代表要切回中文；"
            "上文历史里出现中文也不改变本规则）。NPC 台词写作 'Name: ...'（英文冒号，一行一句）。"
        )
    else:
        lines.append("输出语言：用中文叙述与扮演 NPC（玩家可用任意语言输入）。")
    lines += [
        "规则：",
        "1. 玩家消息是行动/提问；你以 DM 视角回应（叙述 + NPC 台词 + 判定结果），推动剧情但不替玩家做决定",  # noqa: E501
        "2. 需要判定时调用 roll_dice（你不需要计算，系统会判定并把结果给你描述）；剧情明确切换地点时调用 set_scene",  # noqa: E501
        "3. 状态与事实由系统维护（见【当前冒险状态】与【当前状态】），你负责把它们演出来；严禁编造数值状态、严禁遗忘事实表中的状态",  # noqa: E501
        "4. NPC 台词写作「NPC名：……」（中文冒号，一行一句）；旁白独立成段；判定结果单独成段——这会让系统把台词渲染成 NPC 气泡",  # noqa: E501
    ]
    if restore_patch:
        lines.append("5. 【待记住】中的剧情状态本回合必须自然提起或推进，不得跳过。")
    lines.append("6. 保持剧情一致性：玩家说过的关键信息、你对玩家的承诺都要后续兑现。")
    lines.append(
        "7. 关键节点（角色首次登场、重要剧情转折）可调用 show_portrait 让角色立绘出场；"
        "同一场景对同一角色至多一次，不要每回合调用。"
    )
    return "\n".join(lines)


def build_card_prompt(theme: str, lang: str) -> str:
    """场景卡生成 prompt（管理端随机生成 + 用户按词汇生成共用；docs/52 §12.1）。

    要求：只输出一个 JSON 对象；字段与服务器归一规则一致；模板 key 必须落在白名单域内
    （pc/rel/quest/clue，属性见 DOMAIN_PROPERTIES）——服务端仍会逐项校验，此处是质量引导。
    """
    lang_line = (
        "All player-facing text (title/summary/scene/opening_line/tags, and values inside "
        "template) must be in natural English."
        if lang == "en"
        else "所有面向玩家的文本（标题/简介/场景/开场叙述/标签与模板里的值）一律用中文。"
    )
    return "\n".join(
        [
            "你是 TRPG 跑团的开局设计助手。根据主题设计一张**开场场景卡**，只输出一个 JSON 对象"
            "（不要代码围栏、不要解释）。",
            f"主题：{theme}",
            lang_line,
            "JSON 字段：",
            '{"title":"≤30字标题","summary":"一句话简介（≤80字）","language":"zh|en",'
            '"tags":["≤4个标签"],"scene":"起始场景名（≤20字）",'
            '"opening_line":"DM 开场叙述：2-4 句，营造画面感，最后留一个钩子，≤300字",'
            '"template":{"pc_name":"主角","pc":{"hp":12,"location":"具体位置","inventory":"随身物"},'
            '"facts":[{"key":"rel.角色名.attitude","value":"敌对|友善|中立","modality":"fact"}],'
            '"tasks":["任务1","任务2"],"clues":[{"title":"线索名","content":"线索内容","scene":"场景"}]}}',
            "模板规则：",
            "1) facts 的 key 只能是 rel.{NPC名}.attitude|trust|status、quest.{任务名}.status、"
            "clue.{线索名}.found、pc.{PC名}.hp|location|inventory；",
            "2) 最多 3 条 facts、2 条 tasks、2 条 clues；没有就留空数组；",
            "3) 数值状态（HP）只写在 template.pc 里，不要写成 facts；",
            "4) 词条要具体、可直接被 DM 使用（NPC 有名字、线索指向剧情）。",
        ]
    )


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
