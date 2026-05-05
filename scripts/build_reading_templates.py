import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path("/Users/sunao/Work/Obsidian/soon")
ARTICLES_DIR = ROOT / "文章"
OVERVIEW_DIR = ROOT / "总览"
SOURCE = Path("/Users/sunao/Downloads/ps_2026-04-25_all.json")
CLUSTER_JSON = OVERVIEW_DIR / "article_clusters_sklearn.json"
OUT_DIR = ROOT / "主题分类阅读模板"

POLISHED_CLUSTER_NAMES = {
    0: "东亚比较与国家观感",
    1: "社会结构与政治现代性",
    2: "性别事件与公共裁断",
    3: "朋友相处与关系边界",
    4: "命运、信仰与人生意义",
    5: "社会见闻与现实判断",
    6: "善良、分寸与社会感受",
    7: "俄乌战争与强权政治",
    8: "房价、资产与现实账本",
    9: "学校教育与学生处境",
    10: "裁员变局与行业冲击",
    11: "独立思考与认知方法",
    12: "普通人的体面与表达",
    13: "信息筛选与值得关注",
    14: "艺术欣赏与创作判断",
    15: "国际政治与民族认同",
    16: "技术想象与工程文明",
    17: "性别关系与两性观察",
    18: "自由、道德与价值辩驳",
    19: "知识分子与精神弱点",
    20: "公司治理与组织现场",
    21: "生育抉择与亲密关系",
    22: "恋爱、分手与关系去留",
    23: "世界观与知行落差",
    24: "父母、孩子与家庭教育",
    25: "产品消费与实用选择",
    26: "自处节奏与生活疲惫",
    27: "喜欢、表达与情感细节",
    28: "痛苦、羞耻与自我宽恕",
    29: "公共回应与日常判断",
    30: "焦虑、自信与自我建构",
    31: "文娱评价与公共舆论",
    32: "学习方法与成长驱动力",
    33: "理性、野心与精神追求",
    34: "边界感、付出与人际分寸",
    35: "深度沟通与关系协商",
    36: "产业升级与中国制造",
    37: "人类、动物与进化直觉",
    38: "不满情绪与上下级关系",
    39: "管理协作与职场带人",
}

POLISHED_GROUP_NAMES = {
    (26, 19, 38): "自处、倦怠与角色压力",
}


def slugify(text: str) -> str:
    value = text.replace(" / ", "-").replace("/", "-").strip()
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff\-_]", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "未命名主题"


def sanitize_filename(name: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\n\r\t]', " ", (name or "").strip())
    value = re.sub(r"\s+", " ", value).strip().rstrip(".")
    return value or "未命名"


def article_path(item: dict) -> Path:
    published = item.get("publishedAt") or ""
    year = published[:4] if len(published) >= 4 and published[:4].isdigit() else "未分年"
    month = published[5:7] if len(published) >= 7 and published[5:7].isdigit() else "未分月"
    return ARTICLES_DIR / year / month / f"{sanitize_filename(item.get('title') or '未命名')}.md"


def wikilink(item: dict) -> str:
    rel = article_path(item).relative_to(ROOT).as_posix().removesuffix(".md")
    return f"[[{rel}|{item.get('title') or '未命名'}]]"


def trim(text: str, limit: int = 80) -> str:
    value = (text or "").replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def content_length(item: dict) -> int:
    return len((item.get("content") or "").replace("\n", ""))


def is_long(item: dict) -> bool:
    return content_length(item) >= 2000


def difficulty_score(item: dict) -> tuple[int, int, int]:
    content = item.get("content") or ""
    q = item.get("question") or ""
    paragraph_count = len([p for p in content.split("\n\n") if p.strip()])
    punctuation = content.count("：") + content.count("；") + content.count("（") + content.count(")")
    structural = paragraph_count + punctuation
    return (content_length(item), structural, len(q))


def reading_weight(item: dict) -> int:
    return 7 if is_long(item) else 1


def polished_cluster_name(cluster_id: int, fallback: str) -> str:
    return POLISHED_CLUSTER_NAMES.get(cluster_id, fallback)


def polished_group_name(cluster_ids: list[int], fallback_names: list[str]) -> str:
    key = tuple(cluster_ids)
    if key in POLISHED_GROUP_NAMES:
        return POLISHED_GROUP_NAMES[key]
    names = [polished_cluster_name(cid, name) for cid, name in zip(cluster_ids, fallback_names)]
    return " / ".join(names)


@dataclass
class Packet:
    name: str
    slug: str
    source_clusters: list[int]
    items: list[dict]
    note: str = ""


def packet_style(packet: Packet) -> str:
    longs, shorts = packet_summary(packet)
    ratio = longs / len(packet.items) if packet.items else 0
    text = packet.name
    if any(key in text for key in ["中国", "美国", "俄罗斯", "乌克兰", "事件", "性骚扰", "法律", "自由", "道德", "女性", "男性", "政治"]):
        return "争议读"
    if ratio >= 0.28:
        return "深度读"
    return "轻松读"


def start_label(packet: Packet) -> str:
    longs, shorts = packet_summary(packet)
    ratio = longs / len(packet.items) if packet.items else 0
    style = packet_style(packet)
    if style == "轻松读" and ratio <= 0.16:
        return "推荐起手"
    if style == "争议读":
        return "讨论向"
    if ratio >= 0.32:
        return "后段攻坚"
    return "中段展开"


def weighted_chunks(items: list[dict], target_weight: int = 40, soft_min: int = 32, soft_max: int = 46) -> list[list[dict]]:
    chunks = []
    current = []
    current_weight = 0

    for item in items:
        w = reading_weight(item)
        if current and current_weight >= soft_min and current_weight + w > soft_max:
            chunks.append(current)
            current = []
            current_weight = 0
        current.append(item)
        current_weight += w
        if current_weight >= target_weight:
            chunks.append(current)
            current = []
            current_weight = 0

    if current:
        current_total = sum(reading_weight(x) for x in current)
        if chunks:
            last_total = sum(reading_weight(x) for x in chunks[-1])
            if current_total < soft_min and last_total + current_total <= soft_max:
                chunks[-1].extend(current)
            else:
                chunks.append(current)
        else:
            chunks.append(current)

    return chunks


def reading_card_lines(item: dict) -> list[str]:
    long_flag = is_long(item)
    content = (item.get("content") or "").strip()
    lines = [
        f"## {(item.get('publishedAt') or '')[:10]} · {item.get('title') or '未命名'}",
        "",
        f"- 原文链接：{wikilink(item)}",
        f"- 原问题：{item.get('question') or '无题问题'}",
        f"- 文章长度：`{'长文' if long_flag else '短文'}`（约 `{content_length(item)}` 字）",
        "",
    ]
    if long_flag:
        lines.extend(
            [
                "### AI 输入",
                "",
                "```text",
                f"文章标题：{item.get('title') or '未命名'}",
                f"原问题：{item.get('question') or '无题问题'}",
                "",
                "原文：",
                content,
                "",
                "请你扮演严格但友好的阅读教练。",
                "请你基于我下面的回答和原文内容，检查我是否真正理解了这篇长文。",
                "",
                "1. 这篇长文真正试图定义、澄清或解决的核心问题是什么？文中最关键的概念、标准或判断依据又是什么？",
                "我的回答：",
                "",
                "2. 这篇文章最核心的论证链条是什么？",
                "我的回答：",
                "- 第一步：",
                "- 第二步：",
                "- 第三步：",
                "- 第四步：",
                "",
                "3. 如果不用作者原话，我会如何把这篇文章重新讲给一个没读过的人听？",
                "我的回答：",
                "",
                "4. 这篇文章让我联想到哪些现实经验、人物或别的文章？",
                "我的回答：",
                "",
                "请你完成这些事：",
                "1. 判断我有没有抓住作者真正想定义、澄清或解决的核心问题。",
                "2. 检查我是否准确抓住了文中最关键的概念、标准或判断依据，以及它们之间的关系。",
                "3. 检查我概括的论证链条是否完整，有没有遗漏关键递进、转折、前提或结论。",
                "4. 检查我用自己的话重述时，是否真正保留了文章的结构和力度，而不只是把原文说浅了。",
                "5. 结合我写的现实联想，判断我有没有把文章的意思用偏，或者联想得太远。",
                "6. 指出我哪些地方理解窄了、说泛了、跳步了，或者只是换了一种说法但没有真正理解。",
                "7. 帮我给出一个更清楚、更完整、更有层次的改写版本。",
                "8. 最后告诉我，如果我要继续深读这篇文章，最值得追问的 3 个问题是什么。",
                "9. 请加入一个 100 分制的总体评分，必须客观、公正、严谨，不要因为措辞流畅就虚高给分。",
                "10. 评分时请至少同时考虑：核心问题把握、关键概念/标准理解、论证链条完整度、重述准确度、现实联想是否贴题。",
                "",
                "输出格式：",
                "一、总体评价（含 100 分制评分、扣分点、评分依据）",
                "二、我抓住了什么",
                "三、我漏掉了什么",
                "四、我理解得不够准确的地方",
                "五、可直接替换的改写版",
                "六、如果我要继续深读，最值得追问的 3 个问题",
                "```",
                "",
                "### AI 输出",
                "",
                "```text",
                "",
                "```",
            ]
        )
    else:
        lines.extend(
            [
                "### 阅读卡",
                "",
                "#### 1. 用一句话判断：这篇文章真正想回答的是什么问题？",
                "",
                "- 回答：",
                "",
                "#### 2. 用一句话判断：这篇文章的核心判断是什么？",
                "",
                "- 回答：",
                "",
                "#### 3. 我最想停下来的地方，以及我最认同或最保留意见的地方是什么？",
                "",
                "- 回答：",
            ]
        )
    lines.extend(["", "---", ""])
    return lines


def packet_title(packet: Packet, idx: int) -> str:
    cluster_text = ",".join(str(x) for x in packet.source_clusters)
    return f"{idx:03d}-{packet.slug}-C{cluster_text}.md"


def packet_summary(packet: Packet) -> tuple[int, int]:
    longs = sum(1 for item in packet.items if is_long(item))
    return longs, len(packet.items) - longs


def packet_weight(packet: Packet) -> int:
    return sum(reading_weight(item) for item in packet.items)


def packet_group_key(packet: Packet) -> tuple:
    return tuple(packet.source_clusters)


def packet_order_index(packet: Packet) -> int:
    match = re.search(r"第\s*(\d+)\s*组", packet.name)
    if match:
        return int(match.group(1))
    return 10**9


def write_packet(packet: Packet, idx: int) -> tuple[str, int, int, str, str]:
    file_name = packet_title(packet, idx)
    path = OUT_DIR / file_name
    chronological = sorted(packet.items, key=lambda x: ((x.get("publishedAt") or ""), x.get("title") or ""))
    packet.items.sort(
        key=lambda x: (
            1 if is_long(x) else 0,
            difficulty_score(x),
            (x.get("publishedAt") or ""),
            x.get("title") or "",
        )
    )
    first_date = (chronological[0].get("publishedAt") or "")[:10]
    last_date = (chronological[-1].get("publishedAt") or "")[:10]
    longs, shorts = packet_summary(packet)
    total_weight = packet_weight(packet)

    lines = [
        f"# {packet.name}",
        "",
        f"- 阅读包编号：`{idx:03d}`",
        f"- 涵盖主题簇：`{', '.join(str(c) for c in packet.source_clusters)}`",
        f"- 时间范围：`{first_date}` 至 `{last_date}`",
        f"- 文章数量：`{len(packet.items)}`",
        f"- 长短分布：`长文 {longs} / 短文 {shorts}`",
        f"- 阅读负荷：`长文×7 + 短文 = {total_weight}`",
    ]
    if packet.note:
        lines.append(f"- 说明：{packet.note}")
    lines.extend(
        [
            "",
            "## 使用方式",
            "",
            "- 本包排序规则：先短文，后长文；同类型内按由易到难，再用时间顺序兜底。",
            "- 分包规则：以 `长文×7 + 短文 ≈ 40` 为目标控制单个阅读包的阅读负荷。",
            "- 每读完一篇，只至少写下“一句话概括”和“我保留意见的地方”。",
            "- 长文额外补“用自己的话重新表达”，避免只是在重复原句。",
            "",
            "## 目录",
            "",
        ]
    )
    for item in packet.items:
        lines.append(f"- {(item.get('publishedAt') or '')[:10]} {wikilink(item)}")
    lines.append("")

    for item in packet.items:
        lines.extend(reading_card_lines(item))

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return file_name, longs, shorts, first_date, last_date


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    items = json.loads(SOURCE.read_text(encoding="utf-8"))
    cluster_obj = json.loads(CLUSTER_JSON.read_text(encoding="utf-8"))
    article_by_path = {str(article_path(item)): item for item in items}
    cluster_names = {c["cluster_id"]: polished_cluster_name(c["cluster_id"], c["name"]) for c in cluster_obj["clusters"]}

    by_cluster = defaultdict(list)
    for article in cluster_obj["articles"]:
        item = article_by_path.get(article["path"])
        if item is None:
            continue
        by_cluster[article["cluster_id"]].append(item)

    for cluster_id in by_cluster:
        by_cluster[cluster_id].sort(key=lambda x: ((x.get("publishedAt") or ""), x.get("title") or ""))

    packets: list[Packet] = []
    tiny_clusters = [cid for cid, arr in by_cluster.items() if sum(reading_weight(x) for x in arr) < 28]

    for cid, arr in sorted(by_cluster.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if cid in tiny_clusters:
            continue
        chunks = weighted_chunks(arr)
        for idx, chunk in enumerate(chunks, start=1):
            name = cluster_names[cid]
            note = ""
            current_weight = sum(reading_weight(x) for x in chunk)
            if current_weight < 28:
                pad = []
                pad_weight = 0
                for anchor in arr:
                    if current_weight + pad_weight >= 32:
                        break
                    pad.append(anchor)
                    pad_weight += reading_weight(anchor)
                chunk = chunk + pad
                chunk.sort(key=lambda x: ((x.get("publishedAt") or ""), x.get("title") or ""))
                note = f"本组原始阅读负荷偏低，补入了 `{len(pad)}` 篇同主题锚点重复文章，使 `长文×7 + 短文` 更接近 40。"
            packet_name = f"{name} · 第 {idx} 组"
            packets.append(Packet(packet_name, slugify(f"{name}-{idx:02d}"), [cid], chunk, note=note))

    if tiny_clusters:
        merged = []
        names = []
        for cid in sorted(tiny_clusters, key=lambda x: len(by_cluster[x]), reverse=True):
            merged.extend(by_cluster[cid])
            names.append(cluster_names[cid])
        merged.sort(key=lambda x: ((x.get("publishedAt") or ""), x.get("title") or ""))
        note = ""
        if sum(reading_weight(x) for x in merged) < 32 and merged:
            pad = []
            while sum(reading_weight(x) for x in merged + pad) < 32:
                pad.append(merged[len(pad) % len(merged)])
            merged = merged + pad
            merged.sort(key=lambda x: ((x.get("publishedAt") or ""), x.get("title") or ""))
            note = f"为使联合包的阅读负荷更接近 40，补入了 `{len(pad)}` 篇主题锚点重复文章。"
        packets.append(
            Packet(
                polished_group_name(tiny_clusters, names) + " · 联合阅读包",
                slugify("联合阅读包-" + polished_group_name(tiny_clusters, names)),
                tiny_clusters,
                merged,
                note=note or "这些主题簇本身篇幅太小，因此合并成一个联合阅读包。",
            )
        )

    grouped_packets = defaultdict(list)
    for packet in packets:
        grouped_packets[packet_group_key(packet)].append(packet)

    for group in grouped_packets.values():
        group.sort(
            key=lambda packet: (
                packet_order_index(packet),
                packet.name,
            )
        )

    ordered_groups = sorted(
        grouped_packets.values(),
        key=lambda group: (
            packet_weight(group[0]),
            packet_summary(group[0])[0],
            packet_order_index(group[0]),
            (group[0].items[0].get("publishedAt") or "") if group[0].items else "",
            group[0].name,
        ),
    )
    packets = [packet for group in ordered_groups for packet in group]

    master_lines = [
        "# 主题阅读模板总表",
        "",
        "这套阅读模板按主题簇继续细分成多个 20-30 篇的阅读包，包内文章按时间顺序排布。",
        "",
        "## 总体说明",
        "",
        f"- 原始文章总数：`{len(items)}`",
        f"- 生成阅读包数量：`{len(packets)}`",
        "- 覆盖策略：所有文章至少出现一次；个别超小主题会合并，个别阅读负荷过低的包允许少量重复补齐。",
        "- 长文判定：正文长度 `>= 2000` 字。",
        "- 分包标准：按 `长文×7 + 短文 ≈ 40` 来控制单个阅读包的阅读负荷。",
        "",
        "## 快速入口",
        "",
        "- `推荐起手`：优先选短文占比高、进入门槛低的包。",
        "- `中段展开`：适合在你已经熟悉作者后继续系统阅读。",
        "- `后段攻坚`：长文更多、概念更密，适合深读。",
        "- `轻松读 / 深度读 / 争议读`：是阅读气质，不是质量判断。",
        "",
        "## 总表",
        "",
        "下面这部分使用 Obsidian 任务清单格式，可以直接点击勾选/取消。",
        "",
    ]

    packet_index = []
    for idx, packet in enumerate(packets, start=1):
        file_name, longs, shorts, first_date, last_date = write_packet(packet, idx)
        cluster_text = ", ".join(str(c) for c in packet.source_clusters)
        start = start_label(packet)
        style = packet_style(packet)
        weight = packet_weight(packet)
        master_lines.append(
            f"- [ ] `#{idx:03d}` [[{file_name.removesuffix('.md')}|{packet.name}]]"
        )
        master_lines.append(
            f"  - 起读建议：`{start}`；阅读风格：`{style}`；主题簇：`{cluster_text}`"
        )
        master_lines.append(
            f"  - 篇数：`{len(packet.items)}`；长/短：`{longs}/{shorts}`；阅读负荷：`{weight}`；时间范围：`{first_date} - {last_date}`"
        )
        if packet.note:
            master_lines.append(f"  - 说明：{packet.note}")
        packet_index.append(
            {
                "index": idx,
                "name": packet.name,
                "file": file_name,
                "count": len(packet.items),
                "long": longs,
                "short": shorts,
                "weight": weight,
                "start_label": start,
                "style": style,
                "clusters": packet.source_clusters,
                "start": first_date,
                "end": last_date,
            }
        )

    starters = [p for p in packet_index if p["start_label"] == "推荐起手"][:12]
    if starters:
        master_lines.extend(["", "## 推荐起手", ""])
        for p in starters:
            master_lines.append(
                f"- [ ] `#{p['index']:03d}` [[{p['file'].removesuffix('.md')}|{p['name']}]] · `{p['style']}` · `负荷 {p['weight']}` · `{p['long']}/{p['short']}`"
            )

    by_style = {"轻松读": [], "深度读": [], "争议读": []}
    for p in packet_index:
        by_style[p["style"]].append(p)
    master_lines.extend(["", "## 风格筛选", ""])
    for style_name in ["轻松读", "深度读", "争议读"]:
        master_lines.append(f"### {style_name}")
        master_lines.append("")
        for p in by_style[style_name][:15]:
            master_lines.append(
                f"- [ ] `#{p['index']:03d}` [[{p['file'].removesuffix('.md')}|{p['name']}]] · `负荷 {p['weight']}` · `{p['long']}/{p['short']}` · `{p['start_label']}`"
            )
        master_lines.append("")

    master_lines.extend(
        [
            "## 使用建议",
            "",
            "- 先从总表挑一个主题包，不要一次开太多。",
            "- 一个阅读包读完后，再顺着原文中的 `## 引用网络` 继续扩展。",
            "- 如果你更关心系统性，优先读同一大主题的连续几组；如果你更关心轻松上手，优先读长文占比低的组。",
        ]
    )

    (OUT_DIR / "00-主题阅读模板总表.md").write_text("\n".join(master_lines).rstrip() + "\n", encoding="utf-8")
    (OUT_DIR / "reading_packets_manifest.json").write_text(
        json.dumps(packet_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps({"packets": len(packets), "articles": len(items)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
