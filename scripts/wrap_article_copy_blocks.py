import re
from pathlib import Path


ROOT = Path("/Users/sunao/Work/Obsidian/soon")
ARTICLES_DIR = ROOT / "文章"


TITLE_RE = re.compile(
    r"^(---\n.*?\n---\n)(#\s+(?P<title>.+?)\n\n##\s+问题\n\n(?P<question>.*?)\n\n##\s+正文\n\n(?P<body>.*?))(\n##\s+来源\n\n.*)$",
    re.DOTALL,
)


def build_replacement(frontmatter: str, title: str, question: str, body: str, tail: str) -> str:
    title = title.strip()
    question = question.strip()
    body = body.rstrip()
    sections = [
        frontmatter,
        "## 标题",
        "",
        "```text",
        title,
        "```",
        "",
        "## 问题",
        "",
        "```text",
        question,
        "```",
        "",
        "## 回答",
        "",
        "```text",
        body,
        "```",
        tail,
    ]
    return "\n".join(sections).rstrip() + "\n"


def update_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    match = TITLE_RE.match(original)
    if not match:
        return False
    updated = build_replacement(
        match.group(1),
        match.group("title"),
        match.group("question"),
        match.group("body"),
        match.group(6),
    )
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    changed = 0
    total = 0
    skipped = []
    for path in sorted(ARTICLES_DIR.rglob("*.md")):
        total += 1
        try:
            if update_file(path):
                changed += 1
        except Exception as exc:  # pragma: no cover - best-effort migration
            skipped.append((str(path), str(exc)))
    print({"total": total, "changed": changed, "skipped": len(skipped)})
    for path, err in skipped[:20]:
        print(f"SKIP {path}: {err}")


if __name__ == "__main__":
    main()
