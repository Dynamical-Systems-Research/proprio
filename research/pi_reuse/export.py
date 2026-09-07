"""Export allowlisted, compact evidence from the completed local study. No inference."""

import argparse
import json
import shutil
from pathlib import Path

from proprio.artifacts import file_sha256, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "artifacts/evidence/studies/pi-reuse"


def read(path):
    return json.loads(path.read_text())


def export(run: Path, output: Path):
    freeze = read(run / "freeze.json")
    # The archived acquisition implementation is immutable even though the public
    # runner has been extracted and its machine-specific setup removed.
    for name, expected in freeze["files"].items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError(f"Frozen input changed: {name}")
    contract = read(ROOT / "research/pi_transfer/behavioral-contract.json")
    if file_sha256(run / "sealed-cases.json") != contract["private_hash"]:
        raise ValueError("Sealed cases changed")
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)

    def copy(source, relative):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    copy(run / "freeze.json", "freeze.json")
    copy(run / "sealed-cases.json", "cases.json")
    copy(ROOT / "research/pi_transfer/behavioral-contract.json", "contract.json")
    copy(ROOT / "research/pi_transfer/behavioral-source.md", "source.md")
    summary = read(run / "summary.json")
    sessions = []
    for row in summary["sessions"]:
        name = row["name"]
        folder = run / name
        source = folder / "final/skill.py"
        if file_sha256(source) != row["final_hashes"]["skill.py"]:
            raise ValueError(f"Consumer changed: {name}")
        copy(source, f"consumers/{name}.py")
        sessions.append({**row, "inputs": read(folder / "run.json")["inputs"]})
    packages = []
    for pair in range(1, 4):
        for version, stage in [("before", "draft"), ("after", "repair")]:
            name = f"{pair}-{version}"
            folder = run / "packages" / name
            hashes = read(folder / "hashes.json")
            for filename, expected in hashes.items():
                if file_sha256(folder / filename) != expected:
                    raise ValueError(f"Package changed: {name}/{filename}")
                copy(folder / filename, f"packages/{name}/{filename}")
            packages.append(
                {
                    "name": name,
                    "hashes": hashes,
                    "receipt": read(run / f"{stage}-{pair}/receipt.json"),
                }
            )
    # Preserve all evaluated repair proposals, including unsuccessful ones, without
    # publishing conversations or full controller traces.
    repairs = []
    for pair in range(1, 4):
        for attempt in sorted((run / f"repair-{pair}/attempts").glob("*.json")):
            record = read(attempt)
            relative = f"repairs/{pair}-{attempt.stem}.py"
            (output / relative).parent.mkdir(parents=True, exist_ok=True)
            (output / relative).write_text(record["source"])
            repairs.append(
                {
                    "path": relative,
                    "checks": [
                        {
                            "name": case["name"],
                            "expected_status": case["expected_status"],
                            "verdict": gate["verdict"],
                            "runtime_error": gate["runtime_error"],
                            "failed_checks": [
                                c["check_id"] for c in gate["checks"] if not c["passed"]
                            ],
                        }
                        for gate, case in zip(record["gates"], contract["visible"], strict=True)
                    ],
                }
            )
    billing = read(run / "provider-billing.json")
    accounting = {
        k: billing[k]
        for k in [
            "billing_interpretation",
            "confirmed_openrouter_charge_usd",
            "reported_cost_usd",
            "reported_upstream_inference_cost_usd",
            "upstream_inference_cost_by_stage_usd",
            "openrouter_charge_by_stage_usd",
            "routes",
            "session_count",
            "unique_generation_count",
        ]
    }
    write_canonical_json(
        output / "results.json",
        {
            "schema_version": "proprio.pi_reuse.v1",
            "base_commit": "dcc7cee94796346e0ba4985bcd475a12c8c07d32",
            "sessions": sessions,
            "comparison": summary["comparison"],
            "packages": packages,
            "repair_attempts": repairs,
            "accounting": accounting,
            "provenance": "Frozen hashes identify the original acquisition implementation. "
            "The public runner is an extracted implementation; deterministic replay checks "
            "its outcomes against the archived study. Earlier pilots are separate and not pooled.",
        },
    )
    paths = sorted(p for p in output.rglob("*") if p.is_file())
    write_canonical_json(
        output / "manifest.json",
        {"files": {str(p.relative_to(output)): file_sha256(p) for p in paths}},
    )
    print(f"Exported {len(paths)} evidence files to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT)
    args = parser.parse_args()
    export(args.run, args.output)
