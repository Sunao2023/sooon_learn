import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.sparse import hstack
from sklearn.cluster import MiniBatchKMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer

from cluster_articles_sklearn import (
    ROOT,
    OVERVIEW_DIR,
    SOURCE,
    article_path,
    build_text,
    choose_k,
    jieba_tokens,
    top_cluster_keywords,
)


SECTION_MARKERS = ["## 引用网络", "## 相关文章"]


def vault_wikilink(item: dict) -> str:
    path = article_path(item).relative_to(ROOT).as_posix().removesuffix(".md")
    title = item.get("title") or path.split("/")[-1]
    return f"[[{path}|{title}]]"


def cluster_name(keywords: list[str], cluster_id: int) -> str:
    good = [kw for kw in keywords if len(kw.strip()) >= 2][:3]
    if good:
        return " / ".join(good)
    return f"Cluster {cluster_id}"


def trim_text(text: str, limit: int = 42) -> str:
    value = (text or "").replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def build_model(items: list[dict]):
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
    x_word = word_vectorizer.fit_transform(texts)
    x_char = char_vectorizer.fit_transform(texts)
    x = hstack([x_word, x_char]).tocsr()

    reducer = make_pipeline(
        TruncatedSVD(n_components=200, random_state=42),
        Normalizer(copy=False),
    )
    x_reduced = reducer.fit_transform(x)

    model = MiniBatchKMeans(
        n_clusters=k,
        random_state=42,
        batch_size=512,
        n_init=10,
        max_iter=500,
        reassignment_ratio=0.01,
    )
    labels = model.fit_predict(x_reduced)
    return labels, x_reduced, model.cluster_centers_


def normalized_centers(centers: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(centers, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return centers / norms


def cluster_order(cluster_to_indices: dict[int, list[int]]) -> list[int]:
    return [cid for cid, _ in sorted(cluster_to_indices.items(), key=lambda kv: (-len(kv[1]), kv[0]))]


def exemplars_for_cluster(indices: list[int], vectors: np.ndarray, center: np.ndarray, topn: int = 10) -> list[int]:
    scored = []
    for idx in indices:
        score = float(vectors[idx] @ center)
        scored.append((score, idx))
    scored.sort(reverse=True)
    return [idx for _, idx in scored[:topn]]


def top_neighbors_within_cluster(index: int, indices: list[int], vectors: np.ndarray, topn: int = 4) -> list[int]:
    scored = []
    row = vectors[index]
    for other in indices:
        if other == index:
            continue
        score = float(row @ vectors[other])
        scored.append((score, other))
    scored.sort(reverse=True)
    return [other for _, other in scored[:topn]]


def neighbor_clusters(cluster_id: int, centers_norm: np.ndarray, topn: int = 2) -> list[int]:
    scores = centers_norm @ centers_norm[cluster_id]
    scored = [(float(score), idx) for idx, score in enumerate(scores) if idx != cluster_id]
    scored.sort(reverse=True)
    return [idx for _, idx in scored[:topn]]


def strip_reference_section(text: str) -> str:
    for marker in SECTION_MARKERS:
        if marker in text:
            text = text.split(marker)[0].rstrip() + "\n"
    return text.rstrip() + "\n"


def write_article_references(
    items: list[dict],
    labels: np.ndarray,
    vectors: np.ndarray,
    cluster_to_indices: dict[int, list[int]],
    cluster_meta: dict[int, dict],
    neighbor_cluster_map: dict[int, list[int]],
) -> None:
    for idx, item in enumerate(items):
        path = article_path(item)
        if not path.exists():
            continue
        cluster_id = int(labels[idx])
        same_cluster = top_neighbors_within_cluster(idx, cluster_to_indices[cluster_id], vectors, topn=4)
        cluster_info = cluster_meta[cluster_id]
        text = strip_reference_section(path.read_text(encoding="utf-8"))

        lines = [text.rstrip(), "", "## 引用网络", ""]
        lines.append(
            f"- 所属主题簇：`Cluster {cluster_id}` · `{cluster_info['name']}` · `{cluster_info['size']}` 篇"
        )
        lines.append(f"- 主题关键词：`{' / '.join(cluster_info['keywords'][:6])}`")
        lines.append("")
        lines.append("### 同簇近邻")
        lines.append("")
        for other in same_cluster:
            other_item = items[other]
            lines.append(f"- {vault_wikilink(other_item)}")
            lines.append(f"  - 问题：{trim_text(other_item.get('question') or '无题问题')}")

        lines.append("")
        lines.append("### 主题入口")
        lines.append("")
        for exemplar_idx in cluster_info["exemplars"][:3]:
            exemplar_item = items[exemplar_idx]
            lines.append(f"- {vault_wikilink(exemplar_item)}")
            lines.append(f"  - 问题：{trim_text(exemplar_item.get('question') or '无题问题')}")

        lines.append("")
        lines.append("### 邻近主题")
        lines.append("")
        for neighbor_id in neighbor_cluster_map[cluster_id]:
            neighbor = cluster_meta[neighbor_id]
            entry_idx = neighbor["exemplars"][0]
            entry_item = items[entry_idx]
            lines.append(
                f"- `Cluster {neighbor_id}` · `{neighbor['name']}`：{vault_wikilink(entry_item)}"
            )

        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_catalog(items: list[dict], ordered_clusters: list[int], cluster_meta: dict[int, dict]) -> None:
    lines = [
        "# 文章总目录表",
        "",
        "这份目录表基于 `jieba + sklearn` 聚类结果整理。上半部分是一张总览表，下半部分是每个主题簇的入口说明。",
        "",
        "## 总览表",
        "",
        "| Cluster | 暂定主题 | 篇数 | 关键词 | 入口文章 |",
        "| --- | --- | ---: | --- | --- |",
    ]

    for cid in ordered_clusters:
        meta = cluster_meta[cid]
        entry_item = items[meta["exemplars"][0]]
        keywords = " / ".join(meta["keywords"][:5])
        lines.append(
            f"| {cid} | {meta['name']} | {meta['size']} | {keywords} | {vault_wikilink(entry_item)} |"
        )

    lines.extend(["", "## 主题簇说明", ""])
    for cid in ordered_clusters:
        meta = cluster_meta[cid]
        lines.append(f"### Cluster {cid} · {meta['name']}")
        lines.append("")
        lines.append(f"- 篇数：`{meta['size']}`")
        lines.append(f"- 关键词：`{' / '.join(meta['keywords'][:8])}`")
        year_summary = ", ".join(f"{year} {count}" for year, count in meta["years"].most_common(5))
        lines.append(f"- 年份分布：{year_summary}")
        lines.append("- 入口文章：")
        for idx in meta["exemplars"][:6]:
            item = items[idx]
            lines.append(f"- {vault_wikilink(item)}")
            lines.append(f"  - 问题：{trim_text(item.get('question') or '无题问题', 64)}")
        lines.append("")

    OVERVIEW_DIR.mkdir(exist_ok=True)
    (OVERVIEW_DIR / "文章总目录表.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_cluster_report(items: list[dict], ordered_clusters: list[int], cluster_meta: dict[int, dict]) -> None:
    lines = [
        "# sklearn 聚类分析",
        "",
        f"- 数据源：`{SOURCE}`",
        f"- 文章总数：`{len(items)}`",
        "- 向量化：`jieba 分词 TF-IDF + char_wb TF-IDF`",
        "- 降维：`TruncatedSVD(200) + Normalizer()`",
        f"- 聚类模型：`MiniBatchKMeans(n_clusters={len(ordered_clusters)})`",
        "",
        "## 目录入口",
        "",
        f"- 总目录表见：[文章总目录表]({(OVERVIEW_DIR / '文章总目录表.md')}:1)",
        "",
        "## 最大的聚类",
        "",
    ]
    for cid in ordered_clusters[:15]:
        meta = cluster_meta[cid]
        lines.append(f"### Cluster {cid} · {meta['size']} 篇 · {meta['name']}")
        lines.append("")
        lines.append(f"- 关键词：`{' / '.join(meta['keywords'][:8])}`")
        year_summary = ", ".join(f"{year} {count}" for year, count in meta["years"].most_common(5))
        lines.append(f"- 年份分布：{year_summary}")
        lines.append("- 代表文章：")
        for idx in meta["exemplars"][:6]:
            item = items[idx]
            lines.append(f"- [{item.get('title')}]({article_path(item)}:1)；{item.get('question') or '无题问题'}")
        lines.append("")

    (OVERVIEW_DIR / "sklearn聚类分析.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    items = json.loads(SOURCE.read_text(encoding="utf-8"))
    labels, vectors, centers = build_model(items)

    cluster_to_indices = defaultdict(list)
    for idx, label in enumerate(labels):
        cluster_to_indices[int(label)].append(idx)

    keywords_map = top_cluster_keywords(items, cluster_to_indices, topn=10)
    centers_norm = normalized_centers(centers)
    ordered_clusters = cluster_order(cluster_to_indices)

    cluster_meta = {}
    for cid in ordered_clusters:
        indices = cluster_to_indices[cid]
        exemplars = exemplars_for_cluster(indices, vectors, centers[cid], topn=10)
        years = Counter((items[idx].get("publishedAt") or "未知")[:4] for idx in indices)
        cluster_meta[cid] = {
            "size": len(indices),
            "keywords": keywords_map.get(cid, []),
            "name": cluster_name(keywords_map.get(cid, []), cid),
            "exemplars": exemplars,
            "years": years,
        }

    neighbor_cluster_map = {cid: neighbor_clusters(cid, centers_norm, topn=2) for cid in ordered_clusters}

    report = {
        "source": str(SOURCE),
        "article_count": len(items),
        "clusters": [],
        "articles": [],
    }

    for cid in ordered_clusters:
        meta = cluster_meta[cid]
        report["clusters"].append(
            {
                "cluster_id": cid,
                "name": meta["name"],
                "size": meta["size"],
                "keywords": meta["keywords"],
                "neighbor_clusters": neighbor_cluster_map[cid],
                "year_distribution": dict(meta["years"].most_common()),
                "exemplars": [
                    {
                        "title": items[idx].get("title"),
                        "question": items[idx].get("question"),
                        "publishedAt": items[idx].get("publishedAt"),
                        "path": str(article_path(items[idx])),
                    }
                    for idx in meta["exemplars"][:10]
                ],
            }
        )

    for idx, item in enumerate(items):
        cid = int(labels[idx])
        same_cluster = top_neighbors_within_cluster(idx, cluster_to_indices[cid], vectors, topn=4)
        report["articles"].append(
            {
                "title": item.get("title"),
                "question": item.get("question"),
                "cluster_id": cid,
                "cluster_name": cluster_meta[cid]["name"],
                "path": str(article_path(item)),
                "same_cluster_neighbors": [str(article_path(items[other])) for other in same_cluster],
                "neighbor_clusters": neighbor_cluster_map[cid],
            }
        )

    (OVERVIEW_DIR / "article_clusters_sklearn.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    write_catalog(items, ordered_clusters, cluster_meta)
    write_cluster_report(items, ordered_clusters, cluster_meta)
    write_article_references(items, labels, vectors, cluster_to_indices, cluster_meta, neighbor_cluster_map)

    print(json.dumps({"articles": len(items), "clusters": len(ordered_clusters)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
