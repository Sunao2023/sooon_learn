import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import jieba
from scipy.sparse import hstack
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer


ROOT = Path("/Users/sunao/Work/Obsidian/soon")
ARTICLES_DIR = ROOT / "文章"
OVERVIEW_DIR = ROOT / "总览"
SOURCE = Path("/Users/sunao/Downloads/ps_2026-04-25_all.json")
INVALID_PATH_RE = re.compile(r'[\\/:*?"<>|\n\r\t]')
TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
STOPWORDS = {
    "什么", "为什么", "如何", "怎么", "一个", "是不是", "是否", "为什么会", "怎么办",
    "可以", "应该", "这样", "那个", "这个", "我们", "你们", "他们", "她们", "自己",
    "觉得", "知道", "真的", "就是", "因为", "如果", "没有", "不是", "还是", "已经",
    "现在", "时候", "一种", "哪些", "一个人", "有人", "不会", "不能", "需要", "进行",
    "对于", "以及", "如何看待", "问题", "感觉", "是否能", "为什么我", "什么样", "怎么看",
}


def sanitize_filename(name: str) -> str:
    value = INVALID_PATH_RE.sub(" ", (name or "").strip())
    value = re.sub(r"\s+", " ", value).strip().rstrip(".")
    return value or "未命名"


def article_path(item: dict) -> Path:
    published = item.get("publishedAt") or ""
    year = published[:4] if len(published) >= 4 and published[:4].isdigit() else "未分年"
    month = published[5:7] if len(published) >= 7 and published[5:7].isdigit() else "未分月"
    return ARTICLES_DIR / year / month / f"{sanitize_filename(item.get('title') or '未命名')}.md"


def build_text(item: dict) -> str:
    return "\n".join(
        [
            ((item.get("title") or "") + " ") * 4,
            ((item.get("question") or "") + " ") * 3,
            (item.get("content") or "")[:1200],
        ]
    )


def jieba_tokens(text: str) -> list[str]:
    tokens = []
    for token in jieba.lcut(text, cut_all=False):
        token = token.strip().lower()
        if not token:
            continue
        if len(token) <= 1:
            continue
        if token in STOPWORDS:
            continue
        if re.fullmatch(r"[0-9a-zA-Z._/-]+", token):
            continue
        tokens.append(token)
    return tokens


def choose_k(n_docs: int) -> int:
    # Practical default for a few thousand short-medium documents.
    k = int(round(math.sqrt(n_docs / 2)))
    return max(18, min(48, k))


def top_cluster_keywords(items: list[dict], cluster_to_indices: dict[int, list[int]], topn: int = 8) -> dict[int, list[str]]:
    global_df = Counter()
    per_cluster_tf = {}
    for label, indices in cluster_to_indices.items():
        tf = Counter()
        seen = set()
        for idx in indices:
            item = items[idx]
            text = f"{item.get('title') or ''} {item.get('question') or ''}"
            toks = jieba_tokens(text)
            tf.update(toks)
            seen.update(set(toks))
        per_cluster_tf[label] = tf
        for tok in seen:
            global_df[tok] += 1

    total_clusters = len(cluster_to_indices)
    results = {}
    for label, tf in per_cluster_tf.items():
        scored = []
        for tok, count in tf.items():
            if count < 2:
                continue
            score = count * (math.log((1 + total_clusters) / (1 + global_df[tok])) + 1)
            scored.append((score, tok))
        scored.sort(reverse=True)
        chosen = []
        for _, tok in scored:
            if tok in STOPWORDS:
                continue
            if any(tok in existing or existing in tok for existing in chosen):
                continue
            chosen.append(tok)
            if len(chosen) >= topn:
                break
        results[label] = chosen
    return results


def main() -> None:
    OVERVIEW_DIR.mkdir(exist_ok=True)
    items = json.loads(SOURCE.read_text(encoding="utf-8"))
    texts = [build_text(item) for item in items]
    k = choose_k(len(items))

    word_vectorizer = TfidfVectorizer(
        tokenizer=jieba_tokens,
        preprocessor=lambda x: x,
        token_pattern=None,
        min_df=4,
        max_df=0.25,
        sublinear_tf=True,
    )
    char_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 5),
        min_df=5,
        max_df=0.12,
        sublinear_tf=True,
    )
    X_word = word_vectorizer.fit_transform(texts)
    X_char = char_vectorizer.fit_transform(texts)
    X = hstack([X_word, X_char]).tocsr()

    reducer = make_pipeline(
        TruncatedSVD(n_components=200, random_state=42),
        Normalizer(copy=False),
    )
    X_reduced = reducer.fit_transform(X)

    model = MiniBatchKMeans(
        n_clusters=k,
        random_state=42,
        batch_size=512,
        n_init=10,
        max_iter=500,
        reassignment_ratio=0.01,
    )
    labels = model.fit_predict(X_reduced)

    cluster_to_indices = defaultdict(list)
    for idx, label in enumerate(labels):
        cluster_to_indices[int(label)].append(idx)

    centers = model.cluster_centers_
    cluster_keywords = top_cluster_keywords(items, cluster_to_indices, topn=10)

    per_cluster = []
    for label, indices in sorted(cluster_to_indices.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        distances = []
        center = centers[label]
        for idx in indices:
            row = X_reduced[idx]
            score = float(row @ center)
            distances.append((score, idx))
        distances.sort(reverse=True)
        exemplars = []
        years = Counter()
        for _, idx in distances[:10]:
            item = items[idx]
            exemplars.append(
                {
                    "title": item.get("title"),
                    "question": item.get("question"),
                    "publishedAt": item.get("publishedAt"),
                    "path": str(article_path(item)),
                }
            )
        for idx in indices:
            years[(items[idx].get("publishedAt") or "未知")[:4]] += 1
        per_cluster.append(
            {
                "cluster_id": label,
                "size": len(indices),
                "keywords": cluster_keywords.get(label, []),
                "year_distribution": dict(years.most_common()),
                "exemplars": exemplars,
            }
        )

    report = {
        "source": str(SOURCE),
        "article_count": len(items),
        "vectorizer": {
            "word": {
                "tokenizer": "jieba",
                "min_df": 4,
                "max_df": 0.25,
            },
            "char": {
                "analyzer": "char_wb",
                "ngram_range": [2, 5],
                "min_df": 5,
                "max_df": 0.12,
            },
        },
        "reducer": {
            "type": "TruncatedSVD+Normalizer",
            "n_components": 200,
            "random_state": 42,
        },
        "model": {
            "type": "MiniBatchKMeans",
            "n_clusters": k,
            "random_state": 42,
        },
        "clusters": per_cluster,
    }

    json_path = OVERVIEW_DIR / "article_clusters_sklearn.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# sklearn 聚类分析",
        "",
        f"- 数据源：`{SOURCE}`",
        f"- 文章总数：`{len(items)}`",
        "- 向量化：`jieba 分词 TF-IDF + char_wb TF-IDF`",
        "- 降维：`TruncatedSVD(200) + Normalizer()`",
        f"- 聚类模型：`MiniBatchKMeans(n_clusters={k})`",
        "",
        "## 读法",
        "",
        "- 这里的每一簇不是精确标签，而是一组在标题、问题和正文开头表述上相互接近的文章。",
        "- 关键词用于帮助命名聚类，不一定天然就是主题名；更可靠的是看每簇代表文章。",
        "",
        "## 最大的聚类",
        "",
    ]

    for cluster in per_cluster[:15]:
        lines.append(f"### Cluster {cluster['cluster_id']} · {cluster['size']} 篇")
        lines.append("")
        lines.append(f"- 关键词：`{' / '.join(cluster['keywords'][:8])}`")
        year_summary = ", ".join(f"{year} {count}" for year, count in list(cluster["year_distribution"].items())[:5])
        lines.append(f"- 年份分布：{year_summary}")
        lines.append("- 代表文章：")
        for exemplar in cluster["exemplars"][:6]:
            lines.append(
                f"- [{exemplar['title']}]({exemplar['path']}:1)；{exemplar['question'] or '无题问题'}"
            )
        lines.append("")

    lines.extend(
        [
            "## 观察",
            "",
            "- 这版结果更适合拿来发现“自然聚在一起的文章群”，而不是人工预设主题。",
            "- 如果同一簇里既有同一事件，也有不同事件但论证框架相近的文章，说明作者在复用稳定的判断模型。",
            f"- 机器可读结果见：[article_clusters_sklearn.json]({json_path}:1)",
        ]
    )

    md_path = OVERVIEW_DIR / "sklearn聚类分析.md"
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(md_path)
    print(json_path)


if __name__ == "__main__":
    main()
