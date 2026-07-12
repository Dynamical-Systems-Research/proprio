import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".cff", ".json", ".md", ".py", ".toml", ".yaml", ".yml"}
FORBIDDEN = re.compile(
    r"\b" + "lay" + r"er[ _-]?[123]\b|\b" + "sta" + r"ge[ _-]?2\b",
    re.IGNORECASE,
)
FORBIDDEN_PATH_PARTS = {
    "adaptive",
    "confirmatory",
    "generalization",
    "heldout",
    "internal",
    "legacy",
}


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
        normalized_parts = {
            token for part in relative.parts for token in re.split(r"[._-]+", part.lower())
        }
        if normalized_parts & FORBIDDEN_PATH_PARTS:
            violations.append(str(relative))
        if FORBIDDEN.search(str(relative)):
            violations.append(str(relative))
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                violations.append(f"{relative}:{line_number}")
    assert violations == []


def test_python_identifiers_do_not_bind_the_public_interface_to_a_model() -> None:
    violations = []
    for path in (ROOT / "src/proprio").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
            elif isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.append(node.attr)
            for name in names:
                if re.search(r"deepseek|dsv4", name, re.IGNORECASE):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}:{name}"
                    )
    assert violations == []
