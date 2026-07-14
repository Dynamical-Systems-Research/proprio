import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_local_markdown_links_exist() -> None:
    documents = [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
    documents.extend((ROOT / "docs").glob("*.md"))
    documents.extend((ROOT / "skills").rglob("*.md"))
    missing = []
    for document in documents:
        for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local_target = target.split("#", 1)[0]
            if not (document.parent / local_target).resolve().exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert missing == []


def test_demo_media_uses_canonical_video_and_local_poster_only() -> None:
    manifest = json.loads((ROOT / "public/proprio-demo.json").read_text(encoding="utf-8"))
    assert manifest["media"]["video_path"] == "https://dynamicalsystems.ai/proprio-demo.mp4"
    assert not (ROOT / "public/proprio-demo.mp4").exists()
    assert (ROOT / manifest["media"]["poster_path"]).is_file()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "[Technical report](https://dynamicalsystems.ai/blog/" in readme
    assert "[Research blog]" not in readme
