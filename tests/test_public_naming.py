import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".cff", ".json", ".md", ".py", ".toml", ".yaml", ".yml"}
FORBIDDEN = re.compile(
    r"\b" + "lay" + r"ers?\b|\b" + "lay" + r"er[ _-]?[123]\b|\b" + "sta" + r"ge[ _-]?2\b",
    re.IGNORECASE,
)


def test_public_repository_uses_semantic_phase_names() -> None:
    violations = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(ROOT)
        if any(
            part in {".git", ".pytest_cache", ".ruff_cache", ".venv"} for part in relative.parts
        ):
            continue
        if relative.parts[:2] == ("artifacts", "generated"):
            continue
        if FORBIDDEN.search(str(relative)):
            violations.append(str(relative))
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                violations.append(f"{relative}:{line_number}")
    assert violations == []
