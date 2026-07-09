"""Command-line entrypoint for reproducible Proprio gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from proprio.artifacts import write_canonical_json
from proprio.metrology import run_metrology
from proprio.procedural import ProceduralFault, run_fault_battery, run_procedural
from proprio.reference_xrd import run_composition_battery, run_reference_xrd
from proprio.release import build_evidence_manifest, verify_evidence_manifest
from proprio.skill_drafter import draft_skill_cassettes, run_skill_admission
from proprio.support import run_support_battery
from proprio.xrd_types import ValidityFault


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proprio")
    subparsers = parser.add_subparsers(dest="command", required=True)

    procedural_run = subparsers.add_parser("procedural-run")
    procedural_run.add_argument(
        "--fault",
        choices=[fault.value for fault in ProceduralFault],
        default=ProceduralFault.NONE.value,
    )
    procedural_run.add_argument("--output-dir", type=Path, required=True)

    procedural_battery = subparsers.add_parser("procedural-battery")
    procedural_battery.add_argument("--output-dir", type=Path, required=True)

    metrology = subparsers.add_parser("metrology")
    metrology.add_argument("--output-dir", type=Path, required=True)
    metrology.add_argument("--cases-per-class", type=int)

    support = subparsers.add_parser("support-battery")
    support.add_argument("--output-dir", type=Path, required=True)

    xrd_reference = subparsers.add_parser("xrd-reference")
    xrd_reference.add_argument("--output-dir", type=Path, required=True)
    xrd_reference.add_argument(
        "--validity-fault",
        choices=[fault.value for fault in ValidityFault],
        default=ValidityFault.VALID.value,
    )
    xrd_reference.add_argument("--live-judge", action="store_true")

    composition = subparsers.add_parser("composition-battery")
    composition.add_argument("--output-dir", type=Path, required=True)

    draft_skills = subparsers.add_parser("draft-skills")
    draft_skills.add_argument("--cassette-dir", type=Path, required=True)

    skill_admission = subparsers.add_parser("skill-admission")
    skill_admission.add_argument("--cassette-dir", type=Path, required=True)
    skill_admission.add_argument("--output-dir", type=Path, required=True)

    manifest = subparsers.add_parser("evidence-manifest")
    manifest.add_argument("--root", type=Path, default=Path.cwd())
    manifest.add_argument("--output", type=Path, required=True)
    return parser


def _procedural_run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fault = ProceduralFault(args.fault)
    execution = run_procedural(
        fault=fault,
        raw_output=args.output_dir / f"{fault.value}.raw.jsonl",
    )
    summary = {
        "fault_class": fault.value,
        "detected": execution.detected,
        "record": execution.record.model_dump(mode="json"),
        "raw_event_stream": execution.raw_event_stream.model_dump(mode="json"),
    }
    write_canonical_json(args.output_dir / f"{fault.value}.summary.json", summary)
    return summary


def _procedural_battery(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = run_fault_battery(args.output_dir)
    write_canonical_json(args.output_dir / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "procedural-run":
        result = _procedural_run(args)
    elif args.command == "procedural-battery":
        result = _procedural_battery(args)
    elif args.command == "metrology":
        result = run_metrology(
            output_dir=args.output_dir,
            cases_per_class=args.cases_per_class,
        )
    elif args.command == "support-battery":
        result = run_support_battery(args.output_dir)
    elif args.command == "xrd-reference":
        result = run_reference_xrd(
            output_dir=args.output_dir,
            validity_fault=ValidityFault(args.validity_fault),
            live_judge=args.live_judge,
        )
    elif args.command == "composition-battery":
        result = run_composition_battery(args.output_dir)
    elif args.command == "draft-skills":
        result = draft_skill_cassettes(args.cassette_dir)
    elif args.command == "skill-admission":
        result = run_skill_admission(args.cassette_dir, args.output_dir)
    elif args.command == "evidence-manifest":
        result = build_evidence_manifest(args.root, args.output)
        errors = verify_evidence_manifest(args.root, result)
        result["verification_errors"] = errors
        if errors:
            result["verdict"] = "FAIL"
    else:  # pragma: no cover - argparse enforces commands
        raise AssertionError(args.command)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("verdict") == "FAIL" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
