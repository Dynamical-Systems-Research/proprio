"""Replay the published twelve-consumer comparison without Pi or provider access."""

import argparse
import json
from pathlib import Path

from proprio.artifacts import file_sha256
from research.pi_reuse.runtime import evaluate, outcome, summarize

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "artifacts/evidence/studies/pi-reuse"


def read(path):
    return json.loads(path.read_text())


def replay(evidence: Path):
    manifest = read(evidence / "manifest.json")
    for name, expected in manifest["files"].items():
        path = (evidence / name).resolve()
        if not path.is_relative_to(evidence.resolve()) or file_sha256(path) != expected:
            raise ValueError(f"Evidence changed: {name}")
    freeze = read(evidence / "freeze.json")
    for name, expected in freeze["files"].items():
        if name.startswith("src/") or name == "uv.lock":
            if file_sha256(ROOT / name) != expected:
                raise ValueError(f"Evaluator dependency changed: {name}")
    record = read(evidence / "results.json")
    cases = read(evidence / "cases.json")
    contract = read(evidence / "contract.json")
    if file_sha256(evidence / "cases.json") != contract["private_hash"]:
        raise ValueError("Sealed case identity differs")
    for public, original in [
        ("contract.json", "behavioral-contract.json"),
        ("source.md", "behavioral-source.md"),
    ]:
        if file_sha256(evidence / public) != freeze["files"][f"research/pi_transfer/{original}"]:
            raise ValueError(f"Frozen input differs: {public}")
    rows = []
    for saved in record["sessions"]:
        source = evidence / "consumers" / f"{saved['name']}.py"
        if file_sha256(source) != saved["final_hashes"]["skill.py"]:
            raise ValueError(f"Consumer identity differs: {saved['name']}")
        package = evidence / "packages" / f"{saved['pair']}-{saved['version']}"
        for name in ["skill.py", "SKILL.md"]:
            if file_sha256(package / name) != saved["inputs"][f"reference/{name}"]:
                raise ValueError(f"Transferred package differs: {saved['name']}/{name}")
        if file_sha256(evidence / "source.md") != saved["inputs"]["source.md"]:
            raise ValueError(f"Consumer source differs: {saved['name']}")
        code = source.read_text()
        outcomes = [
            outcome(g, c["expected_status"])
            for g, c in zip(evaluate(code, cases), cases, strict=True)
        ]
        if outcomes != saved["outcomes"]:
            raise ValueError(f"Case outcomes differ: {saved['name']}")
        success = (
            saved["operationally_complete"]
            and len(outcomes) == 8
            and all(o["passed"] for o in outcomes)
        )
        if success != saved["success"]:
            raise ValueError(f"Session outcome differs: {saved['name']}")
        rows.append({**saved, "outcomes": outcomes, "success": success})
    comparison = summarize(rows)
    if comparison != record["comparison"]:
        raise ValueError("Paired comparison differs")
    print(
        json.dumps(
            {
                "replay": "PASS",
                "consumers": len(rows),
                "case_outcomes": sum(len(r["outcomes"]) for r in rows),
                "comparison": comparison,
            },
            indent=2,
        )
    )
    return comparison


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT)
    args = parser.parse_args()
    replay(args.evidence)
