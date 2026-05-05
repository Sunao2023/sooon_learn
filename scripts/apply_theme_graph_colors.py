import colorsys
import json
import re
from pathlib import Path


ROOT = Path("/Users/sunao/Work/Obsidian/soon")
OVERVIEW_DIR = ROOT / "总览"
GRAPH_JSON = ROOT / ".obsidian" / "graph.json"
CLUSTER_JSON = OVERVIEW_DIR / "article_clusters_sklearn.json"


RELATIONSHIP_HINTS = {"朋友", "男朋友", "女朋友", "结婚", "恋爱", "喜欢", "女性", "男性", "家长", "父母", "孩子"}
POLITICS_HINTS = {"中国", "美国", "国家", "政治", "战争", "俄罗斯", "乌克兰", "民族", "法律", "警方", "日本", "韩国"}
ART_HINTS = {"文笔", "艺术", "绘画", "电影", "作家", "美术", "书法", "建筑"}
WORK_HINTS = {"公司", "员工", "制造业", "产品", "技术", "芯片", "工作", "领导", "下属", "企业", "财务部"}
MIND_HINTS = {"焦虑", "抑郁症", "善良", "独立思考", "理性", "信仰", "痛苦", "自由", "原理", "逻辑学", "学习"}


def sanitize_theme_tag(name: str) -> str:
    value = name.strip()
    value = value.replace(" / ", "-").replace("/", "-")
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff\-_]", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "未命名主题"


def pick_family(keywords: list[str]) -> str:
    keyset = set(keywords)
    if keyset & RELATIONSHIP_HINTS:
        return "relationship"
    if keyset & POLITICS_HINTS:
        return "politics"
    if keyset & ART_HINTS:
        return "art"
    if keyset & WORK_HINTS:
        return "work"
    if keyset & MIND_HINTS:
        return "mind"
    return "general"


def palette_color(family: str, index: int) -> tuple[int, str]:
    families = {
        "relationship": (0.96, 0.57, [0.48, 0.56, 0.64, 0.40, 0.71, 0.32, 0.60, 0.52]),
        "politics": (0.60, 0.58, [0.45, 0.53, 0.61, 0.37, 0.69, 0.77, 0.29, 0.57]),
        "art": (0.79, 0.52, [0.46, 0.54, 0.62, 0.38, 0.70, 0.30, 0.58, 0.66]),
        "work": (0.42, 0.48, [0.42, 0.50, 0.58, 0.34, 0.66, 0.74, 0.26, 0.54]),
        "mind": (0.12, 0.56, [0.46, 0.54, 0.62, 0.38, 0.70, 0.30, 0.58, 0.66]),
        "general": (0.08, 0.10, [0.45, 0.55, 0.65, 0.35, 0.75, 0.28, 0.60, 0.50]),
    }
    hue, sat, lightnesses = families[family]
    light = lightnesses[index % len(lightnesses)]
    hue = (hue + (index * 0.023)) % 1.0
    rgb = colorsys.hls_to_rgb(hue, light, sat)
    r, g, b = [round(channel * 255) for channel in rgb]
    rgb_int = (r << 16) + (g << 8) + b
    hex_color = f"#{r:02X}{g:02X}{b:02X}"
    return rgb_int, hex_color


def split_frontmatter(text: str) -> tuple[list[str], str]:
    if not text.startswith("---\n"):
        raise ValueError("Expected YAML frontmatter")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError("Malformed frontmatter")
    _, fm, body = parts
    return fm.rstrip("\n").splitlines(), body


def rewrite_frontmatter(lines: list[str], cluster_id: int, theme_name: str, theme_tag: str) -> list[str]:
    cleaned = []
    skip_tag_items = False
    for line in lines:
        if skip_tag_items:
            if line.startswith("  - "):
                continue
            skip_tag_items = False
        if line.startswith("tags:"):
            skip_tag_items = True
            continue
        if line.startswith("theme_cluster:") or line.startswith("theme_cluster_id:"):
            continue
        cleaned.append(line)

    insert_at = 1 if cleaned and cleaned[0].startswith("title:") else 0
    injected = [
        "tags:",
        f"  - cluster/{cluster_id:02d}",
        f"  - theme/{theme_tag}",
        f'theme_cluster: "{theme_name}"',
        f"theme_cluster_id: {cluster_id}",
    ]
    return cleaned[:insert_at] + injected + cleaned[insert_at:]


def update_note(path: Path, cluster_id: int, theme_name: str, theme_tag: str) -> None:
    text = path.read_text(encoding="utf-8")
    fm_lines, body = split_frontmatter(text)
    new_fm = rewrite_frontmatter(fm_lines, cluster_id, theme_name, theme_tag)
    new_text = "---\n" + "\n".join(new_fm).rstrip() + "\n---\n" + body.lstrip("\n")
    path.write_text(new_text, encoding="utf-8")


def main() -> None:
    data = json.loads(CLUSTER_JSON.read_text(encoding="utf-8"))
    clusters = data["clusters"]
    articles = data["articles"]

    family_counts = {}
    cluster_meta = {}
    color_groups = []

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        name = cluster["name"]
        keywords = cluster.get("keywords", [])
        theme_tag = sanitize_theme_tag(name)
        family = pick_family(keywords)
        family_counts.setdefault(family, 0)
        rgb_int, hex_color = palette_color(family, family_counts[family])
        family_counts[family] += 1

        cluster_meta[cluster_id] = {
            "name": name,
            "theme_tag": theme_tag,
            "rgb": rgb_int,
            "hex": hex_color,
        }
        color_groups.append(
            {
                "query": f"tag:#theme/{theme_tag}",
                "color": {"a": 1, "rgb": rgb_int},
            }
        )
        cluster["theme_tag"] = theme_tag
        cluster["color_hex"] = hex_color

    for article in articles:
        cluster_id = article["cluster_id"]
        meta = cluster_meta[cluster_id]
        path = Path(article["path"])
        if path.exists():
            update_note(path, cluster_id, meta["name"], meta["theme_tag"])
        article["theme_tag"] = meta["theme_tag"]
        article["color_hex"] = meta["hex"]

    graph = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    graph["colorGroups"] = color_groups
    graph["collapse-color-groups"] = False
    graph["showTags"] = False
    GRAPH_JSON.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    CLUSTER_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 主题配色表",
        "",
        "这份配色表对应 Obsidian 关系图中的主题分组颜色。",
        "",
        "| Cluster | 主题 | 标签 | 颜色 |",
        "| --- | --- | --- | --- |",
    ]
    for cluster in clusters:
        lines.append(
            f"| {cluster['cluster_id']} | {cluster['name']} | `theme/{cluster_meta[cluster['cluster_id']]['theme_tag']}` | `{cluster_meta[cluster['cluster_id']]['hex']}` |"
        )
    OVERVIEW_DIR.mkdir(exist_ok=True)
    (OVERVIEW_DIR / "主题配色表.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    print(json.dumps({"clusters": len(clusters), "articles": len(articles)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
