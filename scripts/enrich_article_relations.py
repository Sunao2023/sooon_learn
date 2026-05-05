import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix


ROOT = Path("/Users/sunao/Work/Obsidian/soon")
ARTICLES_DIR = ROOT / "文章"
OVERVIEW_DIR = ROOT / "总览"
SOURCE = Path("/Users/sunao/Downloads/ps_2026-04-25_all.json")
RELATED_MARKER = "## 相关文章"

THEMES = {
    "自我与情绪": ["焦虑", "痛苦", "情绪", "抑郁", "孤独", "内耗", "羞耻", "屈辱", "恐惧", "自卑", "崩溃"],
    "关系与婚恋": ["喜欢", "爱", "婚", "恋", "女朋友", "男朋友", "结婚", "出轨", "暧昧", "孩子"],
    "工作与成长": ["工作", "职业", "上班", "公司", "职场", "成长", "学习", "能力", "努力", "成功"],
    "社会观察": ["社会", "阶层", "普通人", "底层", "性别", "女性", "男性", "教育", "学校", "学生"],
    "政治与国际": ["美国", "中国", "俄罗斯", "乌克兰", "特朗普", "民主", "战争", "国家", "政治", "台湾"],
    "艺术与创作": ["写作", "文笔", "小说", "画", "绘画", "艺术", "创作", "摄影", "速写", "诗"],
    "科技与AI": ["ai", "人工智能", "deepseek", "芯片", "科技", "算法", "程序员", "模型"],
    "道德与价值": ["道德", "善良", "正义", "自由", "责任", "独立思考", "集体主义", "自私", "自律"],
}

CJK_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
INVALID_PATH_RE = re.compile(r'[\\/:*?"<>|\n\r\t]')


def sanitize_filename(name: str) -> str:
    value = INVALID_PATH_RE.sub(" ", (name or "").strip())
    value = re.sub(r"\s+", " ", value).strip().rstrip(".")
    return value or "未命名"


def article_path(item: dict) -> Path:
    published = item.get("publishedAt") or ""
    year = published[:4] if len(published) >= 4 and published[:4].isdigit() else "未分年"
    month = published[5:7] if len(published) >= 7 and published[5:7].isdigit() else "未分月"
    return ARTICLES_DIR / year / month / f"{sanitize_filename(item.get('title') or '未命名')}.md"


def normalize(text: str) -> str:
    value = " ".join(CJK_RE.findall(text or ""))
    return re.sub(r"\s+", " ", value).strip().lower()


def grams(text: str) -> list[str]:
    value = text.replace(" ", "")
    result = []
    for n in (2, 3):
        if len(value) >= n:
            result.extend(value[i : i + n] for i in range(len(value) - n + 1))
    return result


def classify_themes(item: dict) -> list[str]:
    text = " ".join(
        [
            item.get("title") or "",
            item.get("question") or "",
            (item.get("content") or "")[:300],
        ]
    ).lower()
    matched = []
    for theme, keywords in THEMES.items():
        if any(keyword.lower() in text for keyword in keywords):
            matched.append(theme)
    return matched


def relative_link(src: Path, dst: Path) -> str:
    return Path(re.sub(r"\\", "/", os.path.relpath(dst, start=src.parent))).as_posix()


def build_similarity(items: list[dict]) -> csr_matrix:
    doc_tfs = []
    df = Counter()
    total_docs = len(items)

    for item in items:
        text = " ".join(
            [
                item.get("title") or "",
                item.get("question") or "",
                (item.get("content") or "")[:400],
            ]
        )
        tf = Counter(grams(normalize(text)))
        doc_tfs.append(tf)
        for token in tf:
            df[token] += 1

    vocab = {}
    upper_bound = max(8, int(total_docs * 0.25))
    for token, count in df.items():
        if 3 <= count <= upper_bound:
            vocab[token] = len(vocab)

    rows = []
    cols = []
    data = []
    for i, tf in enumerate(doc_tfs):
        weighted = {}
        total_terms = sum(tf.values()) or 1
        for token, count in tf.items():
            j = vocab.get(token)
            if j is None:
                continue
            idf = math.log((1 + total_docs) / (1 + df[token])) + 1
            weighted[j] = (count / total_terms) * idf
        norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
        for j, value in weighted.items():
            rows.append(i)
            cols.append(j)
            data.append(value / norm)

    matrix = csr_matrix((data, (rows, cols)), shape=(total_docs, len(vocab)), dtype=np.float32)
    return (matrix @ matrix.T).tocsr()


def choose_related(
    index: int,
    items: list[dict],
    similarity: csr_matrix,
    theme_index: dict[str, list[int]],
    themes_by_article: list[list[str]],
) -> list[int]:
    related = []
    seen = {index}

    row = similarity.getrow(index)
    candidates = []
    for other, score in zip(row.indices, row.data):
        if other == index or score < 0.18:
            continue
        candidates.append((float(score), int(other)))
    candidates.sort(reverse=True)

    for score, other in candidates:
        if other in seen:
            continue
        related.append(other)
        seen.add(other)
        if len(related) >= 3:
            break

    for theme in themes_by_article[index]:
        for other in theme_index[theme]:
            if other in seen:
                continue
            related.append(other)
            seen.add(other)
            if len(related) >= 5:
                return related

    return related[:5]


def update_article(path: Path, current: dict, related_items: list[dict]) -> None:
    text = path.read_text(encoding="utf-8")
    if RELATED_MARKER in text:
        text = text.split(RELATED_MARKER)[0].rstrip() + "\n"

    lines = [text.rstrip(), "", RELATED_MARKER, ""]
    if related_items:
        lines.append("这些文章与本文在问题意识、主题或论证框架上较接近：")
        lines.append("")
        for item in related_items:
            target = article_path(item)
            link = relative_link(path, target)
            question = item.get("question") or "无题问题"
            lines.append(f"- [{item.get('title') or '未命名'}]({link})")
            lines.append(f"  - 问题：{question}")
    else:
        lines.append("暂未找到足够接近的相关文章。")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_thought_map(items: list[dict], themes_by_article: list[list[str]], related_map: dict[int, list[int]]) -> str:
    theme_counts = Counter()
    theme_examples = defaultdict(list)
    year_counts = defaultdict(Counter)
    question_stems = Counter()

    for idx, item in enumerate(items):
        year = (item.get("publishedAt") or "未知")[:4]
        question = item.get("question") or ""
        for theme in themes_by_article[idx]:
            theme_counts[theme] += 1
            year_counts[year][theme] += 1
            if len(theme_examples[theme]) < 6:
                theme_examples[theme].append(item)

        for stem in ["为什么", "如何", "怎么看", "怎么办", "是否", "是不是", "能不能", "如何看待"]:
            if stem in question:
                question_stems[stem] += 1

    lines = [
        "# 作者思想地图",
        "",
        "这份地图不是逐篇摘要，而是把这批文章反复出现的关切、判断方式和问题结构压缩成一个可浏览的框架。",
        "",
        "## 核心观察",
        "",
        "- 这些文章最稳定的底盘，不是事件本身，而是对人的判断、关系中的权力、以及个体如何在秩序里安放自己的问题。",
        "- 作者常用的写法不是中性分析，而是借具体问题拆穿提问背后的预设，再把问题重写成一个更根本的命题。",
        "- 因此文章之间的关系，很多不是“同题”，而是“同一个判断框架在不同场景下反复出现”。",
        "",
        "## 主要母题",
        "",
    ]

    for theme, count in theme_counts.most_common():
        lines.append(f"### {theme}")
        lines.append("")
        lines.append(f"- 相关文章约 `{count}` 篇。")
        sample_titles = " / ".join(item.get("title") or "未命名" for item in theme_examples[theme][:4])
        lines.append(f"- 代表文章：{sample_titles}")
        if theme == "关系与婚恋":
            lines.append("- 这里反复讨论的是欲望、占有、边界、忠诚，以及人为什么会被某类关系吸引。")
        elif theme == "工作与成长":
            lines.append("- 这里的核心不是鸡汤式努力，而是能力、耐受、职业适配和长期主义。")
        elif theme == "社会观察":
            lines.append("- 这部分经常把个体困境放回阶层、性别、教育和社会角色里看。")
        elif theme == "政治与国际":
            lines.append("- 这部分更强调秩序、国家利益、群体心理和历史惯性，而不是单点新闻。")
        elif theme == "道德与价值":
            lines.append("- 这里经常处理的是“看起来正确”的道德语言与真实人性之间的缝隙。")
        elif theme == "自我与情绪":
            lines.append("- 这里关注情绪如何不是单纯的毛病，而是认知、关系和生存状态的信号。")
        elif theme == "艺术与创作":
            lines.append("- 这里常把创作理解为感受力、结构能力和表达自由，而不只是技巧。")
        elif theme == "科技与AI":
            lines.append("- 这部分常把 AI 当作一面镜子，照见人的能力焦虑、替代恐惧和新工具伦理。")
        lines.append("")

    lines.extend(
        [
            "## 常见提问结构",
            "",
            "- 这些文章高频回应的不是事实问答，而是几类稳定句式：",
        ]
    )
    for stem, count in question_stems.most_common():
        lines.append(f"- `{stem}`：约 `{count}` 次")

    lines.extend(
        [
            "",
            "## 时间上的重心变化",
            "",
        ]
    )
    for year in sorted(year_counts):
        summary = ", ".join(f"{theme} {count}" for theme, count in year_counts[year].most_common(4))
        lines.append(f"- `{year}`：{summary}")

    lines.extend(
        [
            "",
            "## 关系网络怎么读",
            "",
            "- 同题关系：极少，但存在重复收录或重发。",
            "- 同主题关系：大量文章围绕同一母题展开，适合按主题连读。",
            "- 同框架关系：即使标题和事件不同，背后的判断逻辑高度相似，这类关系最值得建双链。",
            "",
            "## 推荐阅读方式",
            "",
            "- 从任一篇文章底部的“相关文章”继续跳转，适合顺着思路走。",
            "- 先按主题挑入口，再回看不同年份的变化，适合看作者关注点如何转移。",
            "- 对同一个问题意识，优先比较不同场景下的文章，最容易看出作者的稳定判断。",
            "",
            "## 例子",
            "",
        ]
    )

    example_indices = [i for i, related in related_map.items() if len(related) >= 3][:6]
    for idx in example_indices:
        current = items[idx]
        lines.append(f"### {current.get('title') or '未命名'}")
        lines.append("")
        lines.append(f"- 问题：{current.get('question') or '无'}")
        lines.append("- 相关文章：")
        for other in related_map[idx][:3]:
            item = items[other]
            path = article_path(item)
            lines.append(f"- [{item.get('title') or '未命名'}]({path.relative_to(ROOT).as_posix()})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    items = json.loads(SOURCE.read_text(encoding="utf-8"))
    similarity = build_similarity(items)

    themes_by_article = [classify_themes(item) for item in items]
    theme_index = defaultdict(list)
    for idx, themes in enumerate(themes_by_article):
        for theme in themes:
            theme_index[theme].append(idx)

    related_map = {}
    for idx, item in enumerate(items):
        path = article_path(item)
        if not path.exists():
            continue
        related_map[idx] = choose_related(idx, items, similarity, theme_index, themes_by_article)

    for idx, related_indices in related_map.items():
        current = items[idx]
        path = article_path(current)
        related_items = [items[other] for other in related_indices if article_path(items[other]).exists()]
        update_article(path, current, related_items)

    thought_map = build_thought_map(items, themes_by_article, related_map)
    OVERVIEW_DIR.mkdir(exist_ok=True)
    (OVERVIEW_DIR / "作者思想地图.md").write_text(thought_map, encoding="utf-8")

    summary = {
        "article_count": len(items),
        "updated_articles": len(related_map),
        "thought_map": str(OVERVIEW_DIR / "作者思想地图.md"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
