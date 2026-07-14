"""Command-line interface for Proprio qualification workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from proprio.artifacts import write_canonical_json
from proprio.cross_family import (
    freeze_cross_family_method,
    run_cross_family_panel,
    run_cross_family_session,
)
from proprio.external_instruments import EXTERNAL_INSTRUMENTS
from proprio.instruments import INSTRUMENTS
from proprio.interface import (
    candidate_from_directory,
    execute_candidate,
    inspect_source,
    read_visible_evidence,
    stage_evolution,
    verify_locked,
)
from proprio.metrology import run_metrology
from proprio.procedural import ProceduralFault, run_fault_battery, run_procedural
from proprio.reference_xrd import run_composition_battery, run_reference_xrd
from proprio.release import build_evidence_manifest, verify_evidence_manifest
from proprio.skill_drafter import run_skill_admission
from proprio.skill_publication import publish_skill_library
from proprio.support import run_support_battery
from proprio.xrd_types import ValidityFault


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proprio",
        description="Acquire and qualify scientific-instrument skills in simulation.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    procedural_run = commands.add_parser("procedural-run", help="Run one simulated XRD scan.")
    procedural_run.add_argument(
        "--fault",
        choices=[fault.value for fault in ProceduralFault],
        default=ProceduralFault.NONE.value,
    )
    procedural_run.add_argument("--output-dir", type=Path, required=True)

    procedural_battery = commands.add_parser(
        "procedural-battery", help="Run the XRD execution fault battery."
    )
    procedural_battery.add_argument("--output-dir", type=Path, required=True)

    metrology = commands.add_parser("metrology", help="Measure XRD verifier performance.")
    metrology.add_argument("--output-dir", type=Path, required=True)
    metrology.add_argument("--cases-per-class", type=int)

    support = commands.add_parser("support-battery", help="Evaluate substrate support checks.")
    support.add_argument("--output-dir", type=Path, required=True)

    xrd_reference = commands.add_parser("xrd-reference", help="Run the reference XRD workflow.")
    xrd_reference.add_argument("--output-dir", type=Path, required=True)
    xrd_reference.add_argument(
        "--validity-fault",
        choices=[fault.value for fault in ValidityFault],
        default=ValidityFault.VALID.value,
    )
    xrd_reference.add_argument("--live-judge", action="store_true")

    composition = commands.add_parser(
        "composition-battery", help="Exercise the complete XRD qualification chain."
    )
    composition.add_argument("--output-dir", type=Path, required=True)

    admission = commands.add_parser(
        "skill-admission", help="Replay deterministic skill admission cases."
    )
    admission.add_argument("--cassette-dir", type=Path, required=True)
    admission.add_argument("--output-dir", type=Path, required=True)

    freeze = commands.add_parser(
        "cross-family-freeze", help="Freeze the cross-family acquisition method."
    )
    freeze.add_argument("--output-dir", type=Path, required=True)
    freeze.add_argument("--evidence-root", type=Path)

    session = commands.add_parser(
        "cross-family-session", help="Run one persistent acquisition session."
    )
    session.add_argument("--instrument", choices=sorted(EXTERNAL_INSTRUMENTS), required=True)
    session.add_argument("--output-dir", type=Path, required=True)
    session.add_argument("--session-index", type=int, default=0)
    session.add_argument("--freeze", type=Path, required=True)

    panel = commands.add_parser(
        "cross-family-panel", help="Run the frozen cross-family binding panel."
    )
    panel.add_argument("--output-dir", type=Path, required=True)
    panel.add_argument("--freeze", type=Path, required=True)

    inspect = commands.add_parser(
        "inspect-source", help="Read one instrument source and controller contract."
    )
    inspect.add_argument("--instrument", choices=sorted(INSTRUMENTS), required=True)

    execute = commands.add_parser(
        "execute-candidate", help="Run an agent-authored candidate on visible conditions."
    )
    execute.add_argument("--instrument", choices=sorted(INSTRUMENTS), required=True)
    execute.add_argument("--candidate-dir", type=Path, required=True)
    execute.add_argument("--output-dir", type=Path, required=True)
    execute.add_argument("--agent", default="external-agent")

    evidence = commands.add_parser(
        "read-visible-evidence", help="Read a candidate's visible execution evidence."
    )
    evidence.add_argument("--run-dir", type=Path, required=True)

    locked = commands.add_parser(
        "verify-locked", help="Replay visible behavior and run locked verification."
    )
    locked.add_argument("--instrument", choices=sorted(INSTRUMENTS), required=True)
    locked.add_argument("--candidate-dir", type=Path, required=True)
    locked.add_argument("--output-dir", type=Path, required=True)
    locked.add_argument("--agent", default="external-agent")

    evolution = commands.add_parser(
        "stage-evolution", help="Stage a non-regressive skill after simulated drift."
    )
    evolution.add_argument("--instrument", choices=sorted(INSTRUMENTS), required=True)
    evolution.add_argument("--parent-dir", type=Path, required=True)
    evolution.add_argument("--candidate-dir", type=Path, required=True)
    evolution.add_argument("--output-dir", type=Path, required=True)
    evolution.add_argument("--agent", default="external-agent")

    manifest = commands.add_parser(
        "evidence-manifest", help="Create and verify the release evidence manifest."
    )
    manifest.add_argument("--root", type=Path, default=Path.cwd())
    manifest.add_argument("--output", type=Path, required=True)

    publish = commands.add_parser(
        "publish-skills", help="Regenerate compact skill verification records and catalog."
    )
    publish.add_argument("--root", type=Path, default=Path.cwd())
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


def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "procedural-run":
        return _procedural_run(args)
    if args.command == "procedural-battery":
        args.output_dir.mkdir(parents=True, exist_ok=True)
        result = run_fault_battery(args.output_dir)
        write_canonical_json(args.output_dir / "summary.json", result)
        return result
    if args.command == "metrology":
        return run_metrology(
            output_dir=args.output_dir,
            cases_per_class=args.cases_per_class,
        )
    if args.command == "support-battery":
        return run_support_battery(args.output_dir)
    if args.command == "xrd-reference":
        return run_reference_xrd(
            output_dir=args.output_dir,
            validity_fault=ValidityFault(args.validity_fault),
            live_judge=args.live_judge,
        )
    if args.command == "composition-battery":
        return run_composition_battery(args.output_dir)
    if args.command == "skill-admission":
        return run_skill_admission(args.cassette_dir, args.output_dir)
    if args.command == "cross-family-freeze":
        return freeze_cross_family_method(args.output_dir, evidence_root=args.evidence_root)
    if args.command == "cross-family-session":
        return run_cross_family_session(
            args.instrument,
            args.output_dir,
            session_index=args.session_index,
            freeze_path=args.freeze,
        )
    if args.command == "cross-family-panel":
        return run_cross_family_panel(args.output_dir, freeze_path=args.freeze)
    if args.command == "inspect-source":
        return inspect_source(args.instrument)
    if args.command == "execute-candidate":
        candidate = candidate_from_directory(args.instrument, args.candidate_dir, agent=args.agent)
        return execute_candidate(args.instrument, candidate, output_dir=args.output_dir)
    if args.command == "read-visible-evidence":
        return read_visible_evidence(args.run_dir)
    if args.command == "verify-locked":
        candidate = candidate_from_directory(args.instrument, args.candidate_dir, agent=args.agent)
        return verify_locked(candidate, output_dir=args.output_dir)
    if args.command == "stage-evolution":
        parent = candidate_from_directory(args.instrument, args.parent_dir, agent="admitted-parent")
        candidate = candidate_from_directory(args.instrument, args.candidate_dir, agent=args.agent)
        return stage_evolution(parent, candidate, output_dir=args.output_dir)
    if args.command == "evidence-manifest":
        result = build_evidence_manifest(args.root, args.output)
        errors = verify_evidence_manifest(args.root, result)
        result["verification_errors"] = errors
        if errors:
            result["verdict"] = "FAIL"
        return result
    if args.command == "publish-skills":
        return publish_skill_library(args.root)
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    result = _run(_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("verdict") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
