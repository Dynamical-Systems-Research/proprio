import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_local_markdown_links_exist() -> None:
    documents = [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
    documents.extend((ROOT / "docs").glob("*.md"))
    documents.extend((ROOT / "skills").glob("*/SKILL.md"))
    missing = []
    for document in documents:
        for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local_target = target.split("#", 1)[0]
            if not (document.parent / local_target).resolve().exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert missing == []
