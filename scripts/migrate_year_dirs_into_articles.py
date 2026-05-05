import re
import shutil
from pathlib import Path


ROOT = Path("/Users/sunao/Work/Obsidian/soon")
ARTICLES_DIR = ROOT / "文章"
YEAR_NAMES = [str(year) for year in range(2017, 2027)]
TEXT_SUFFIXES = {".md", ".json", ".py"}


WIKILINK_RE = re.compile(r"\[\[([0-9]{4}/[0-9]{2}/[^\]|]+)")
ABS_PATH_RE = re.compile(r"(/Users/sunao/Work/Obsidian/soon/)(20[0-9]{2}/[0-9]{2}/)")


def move_year_directories() -> None:
    ARTICLES_DIR.mkdir(exist_ok=True)
    for year in YEAR_NAMES:
        src = ROOT / year
        dst = ARTICLES_DIR / year
        if src.exists():
            if dst.exists():
                for child in src.iterdir():
                    target = dst / child.name
                    if target.exists():
                        raise FileExistsError(f"Target already exists: {target}")
                    shutil.move(str(child), str(target))
                src.rmdir()
            else:
                shutil.move(str(src), str(dst))


def rewrite_text(text: str) -> str:
    text = WIKILINK_RE.sub(lambda m: f"[[文章/{m.group(1)}", text)
    text = ABS_PATH_RE.sub(lambda m: f"{m.group(1)}文章/{m.group(2)}", text)
    return text


def update_text_files() -> int:
    changed = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        original = path.read_text(encoding="utf-8")
        updated = rewrite_text(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def main() -> None:
    move_year_directories()
    changed = update_text_files()
    print({"articles_dir": str(ARTICLES_DIR), "updated_files": changed})


if __name__ == "__main__":
    main()
