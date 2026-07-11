"""Command-line entrypoint for reproducible Proprio gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from proprio.adaptive_microscopy_metrology import run_adaptive_microscopy_metrology
from proprio.adaptive_microscopy_study import (
    lock_causal_development_panel,
    run_live_adaptive_microscopy_causal_repair,
    run_live_adaptive_microscopy_curve_metrology,
    run_live_adaptive_microscopy_preflight,
    run_live_adaptive_microscopy_reset_battery,
    run_live_adaptive_microscopy_search,
    run_live_adaptive_microscopy_uncertainty_battery,
)
from proprio.adaptive_validation import run_live_adaptive_microscopy_locked
from proprio.agent_smoke import run_persistent_smoke
from proprio.artifacts import write_canonical_json
from proprio.causal_evidence import summarize_accumulated_causal_evidence
from proprio.confirmatory_metrology import run_confirmatory_metrology
from proprio.confirmatory_study import (
    replay_confirmatory_study,
    run_live_confirmatory_judges,
    run_live_confirmatory_study,
)
from proprio.engineering_burden import run_engineering_burden
from proprio.heldout_preflight import import_heldout_preflight_evidence
from proprio.history_repair import run_live_history_repair
from proprio.independent_review import run_live_independent_review, summarize_independent_study
from proprio.instrument_metrology import run_instrument_metrology
from proprio.instrument_study import replay_instrument_study, run_live_instrument_study
from proprio.instrument_types import CandidatePackage
from proprio.judge_metrology import (
    CONFIRMATORY_INSTRUMENT_IDS,
    run_live_confirmatory_judge_metrology,
    run_live_judge_metrology,
    summarize_judge_metrology,
)
from proprio.locked_validation import run_locked_validation_once
from proprio.method_freeze import freeze_adaptive_method, verify_adaptive_method_freeze
from proprio.metrology import run_metrology
from proprio.microscopy import capture_live_microscopy_reference
from proprio.microscopy_evolution import (
    replay_microscopy_evolution,
    run_live_microscopy_evolution,
    summarize_microscopy_evolution,
)
from proprio.microscopy_metrology import run_microscopy_metrology
from proprio.model_ablation import run_live_model_ablation
from proprio.procedural import ProceduralFault, run_fault_battery, run_procedural
from proprio.reference_xrd import run_composition_battery, run_reference_xrd
from proprio.release import build_evidence_manifest, verify_evidence_manifest
from proprio.replication_study import INSTRUMENT_IDS as REPLICATION_INSTRUMENT_IDS
from proprio.replication_study import run_live_replication_study, summarize_replication_study
from proprio.skill_drafter import draft_skill_cassettes, run_skill_admission
from proprio.skill_evolution import replay_evolution_study, run_live_evolution_study
from proprio.skill_library import package_confirmatory_skills, package_microscopy_skill
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

    instrument_metrology = subparsers.add_parser("instrument-metrology")
    instrument_metrology.add_argument("--output-dir", type=Path, required=True)
    instrument_metrology.add_argument("--cases-per-class", type=int, default=300)

    instrument_study_live = subparsers.add_parser("instrument-study-live")
    instrument_study_live.add_argument("--cassette-dir", type=Path, required=True)
    instrument_study_live.add_argument("--skip-judge", action="store_true")

    instrument_study_replay = subparsers.add_parser("instrument-study-replay")
    instrument_study_replay.add_argument("--cassette-dir", type=Path, required=True)
    instrument_study_replay.add_argument("--output-dir", type=Path, required=True)

    evolution_live = subparsers.add_parser("evolution-live")
    evolution_live.add_argument("--study-cassette-dir", type=Path, required=True)
    evolution_live.add_argument("--output-dir", type=Path, required=True)

    evolution_replay = subparsers.add_parser("evolution-replay")
    evolution_replay.add_argument("--cassette-dir", type=Path, required=True)
    evolution_replay.add_argument("--output-dir", type=Path, required=True)

    judge_metrology_live = subparsers.add_parser("judge-metrology-live")
    judge_metrology_live.add_argument("--output-dir", type=Path, required=True)

    judge_metrology_replay = subparsers.add_parser("judge-metrology-replay")
    judge_metrology_replay.add_argument("--cassette-dir", type=Path, required=True)

    confirmatory_judge_metrology_live = subparsers.add_parser("confirmatory-judge-metrology-live")
    confirmatory_judge_metrology_live.add_argument("--output-dir", type=Path, required=True)

    confirmatory_judge_metrology_replay = subparsers.add_parser(
        "confirmatory-judge-metrology-replay"
    )
    confirmatory_judge_metrology_replay.add_argument("--cassette-dir", type=Path, required=True)

    model_ablation = subparsers.add_parser("model-ablation-live")
    model_ablation.add_argument("--primary-cassette-dir", type=Path, required=True)
    model_ablation.add_argument("--output-dir", type=Path, required=True)
    model_ablation.add_argument(
        "--study",
        choices=["native_draft", "shared_failure_repair"],
        required=True,
    )

    locked_validation = subparsers.add_parser("locked-validation")
    locked_validation.add_argument("--candidate", type=Path, required=True)
    locked_validation.add_argument("--output-dir", type=Path, required=True)

    confirmatory_metrology = subparsers.add_parser("confirmatory-metrology")
    confirmatory_metrology.add_argument("--output-dir", type=Path, required=True)
    confirmatory_metrology.add_argument("--cases-per-class", type=int)

    confirmatory_study = subparsers.add_parser("confirmatory-study-live")
    confirmatory_study.add_argument("--output-dir", type=Path, required=True)

    confirmatory_replay = subparsers.add_parser("confirmatory-study-replay")
    confirmatory_replay.add_argument("--cassette-dir", type=Path, required=True)
    confirmatory_replay.add_argument("--output-dir", type=Path, required=True)

    confirmatory_judge = subparsers.add_parser("confirmatory-judge-live")
    confirmatory_judge.add_argument("--cassette-dir", type=Path, required=True)

    microscopy_reference = subparsers.add_parser("microscopy-reference-live")
    microscopy_reference.add_argument("--output-dir", type=Path, required=True)
    microscopy_reference.add_argument("--base-url", default="http://127.0.0.1:5100")

    adaptive_microscopy_preflight = subparsers.add_parser("adaptive-microscopy-preflight")
    adaptive_microscopy_preflight.add_argument("--output-dir", type=Path, required=True)
    adaptive_microscopy_preflight.add_argument("--base-url", default="http://127.0.0.1:5100")

    adaptive_reset = subparsers.add_parser("adaptive-microscopy-reset")
    adaptive_reset.add_argument("--output-dir", type=Path, required=True)
    adaptive_reset.add_argument(
        "--base-urls",
        nargs="+",
        default=["http://127.0.0.1:5100"],
    )
    adaptive_reset.add_argument("--cases-per-simulator", type=int, default=5)

    adaptive_curve = subparsers.add_parser("adaptive-microscopy-curve-metrology")
    adaptive_curve.add_argument("--output-dir", type=Path, required=True)
    adaptive_curve.add_argument(
        "--base-urls",
        nargs="+",
        default=["http://127.0.0.1:5100"],
    )
    adaptive_curve.add_argument("--cases-per-group", type=int, default=20)

    adaptive_microscopy_search = subparsers.add_parser("adaptive-microscopy-search-live")
    adaptive_microscopy_search.add_argument("--output-dir", type=Path, required=True)
    adaptive_microscopy_search.add_argument("--base-url", default="http://127.0.0.1:5100")
    adaptive_microscopy_search.add_argument("--seed-base", type=int, default=920000)
    adaptive_microscopy_search.add_argument("--smoke", action="store_true")

    adaptive_uncertainty = subparsers.add_parser("adaptive-microscopy-uncertainty")
    adaptive_uncertainty.add_argument("--output-dir", type=Path, required=True)
    adaptive_uncertainty.add_argument(
        "--base-urls",
        nargs="+",
        default=["http://127.0.0.1:5100"],
    )
    adaptive_uncertainty.add_argument("--cases-per-group", type=int, default=20)

    adaptive_metrology = subparsers.add_parser("adaptive-microscopy-metrology")
    adaptive_metrology.add_argument("--output-dir", type=Path, required=True)
    adaptive_metrology.add_argument("--cases-per-class", type=int, default=300)

    adaptive_causal = subparsers.add_parser("adaptive-microscopy-causal-repair-live")
    adaptive_causal.add_argument("--output-dir", type=Path, required=True)
    adaptive_causal.add_argument("--candidate", type=Path, required=True)
    adaptive_causal.add_argument(
        "--base-urls",
        nargs="+",
        default=[
            "http://127.0.0.1:5100",
            "http://127.0.0.1:5101",
            "http://127.0.0.1:5102",
            "http://127.0.0.1:5103",
        ],
    )
    adaptive_causal.add_argument("--seed", type=int, default=990000)
    adaptive_causal.add_argument("--trials", type=int, default=30)

    causal_lock = subparsers.add_parser("adaptive-microscopy-causal-lock")
    causal_lock.add_argument("--attempt-dir", type=Path, required=True)
    causal_lock.add_argument("--output-dir", type=Path, required=True)
    causal_lock.add_argument("--completed-trials", type=int, default=4)

    adaptive_locked = subparsers.add_parser("adaptive-microscopy-locked")
    adaptive_locked.add_argument("--output-dir", type=Path, required=True)
    adaptive_locked.add_argument("--search", type=Path, required=True)
    adaptive_locked.add_argument("--base-url", default="http://127.0.0.1:5100")

    method_freeze = subparsers.add_parser("adaptive-method-freeze")
    method_freeze.add_argument("--output-dir", type=Path, required=True)
    method_freeze.add_argument("--generated-root", type=Path)

    method_verify = subparsers.add_parser("adaptive-method-verify")
    method_verify.add_argument("--manifest", type=Path, required=True)

    causal_evidence = subparsers.add_parser("causal-evidence-summary")
    causal_evidence.add_argument("--output-dir", type=Path, required=True)
    causal_evidence.add_argument("--confirmatory", type=Path, required=True)
    causal_evidence.add_argument("--diagnostic", type=Path, required=True)
    causal_evidence.add_argument("--openflexure-lock", type=Path, required=True)

    heldout_preflight = subparsers.add_parser("heldout-preflight-import")
    heldout_preflight.add_argument("--output-dir", type=Path, required=True)
    heldout_preflight.add_argument("--preregistration", type=Path, required=True)
    heldout_preflight.add_argument("--evidence", type=Path, nargs="+", required=True)

    persistent_smoke = subparsers.add_parser("persistent-smoke")
    persistent_smoke.add_argument("--instrument", required=True)
    persistent_smoke.add_argument("--output-dir", type=Path, required=True)
    persistent_smoke.add_argument("--parent-episode", type=Path, default=None)

    microscopy_metrology = subparsers.add_parser("microscopy-metrology")
    microscopy_metrology.add_argument("--reference-dir", type=Path, required=True)
    microscopy_metrology.add_argument("--output-dir", type=Path, required=True)
    microscopy_metrology.add_argument("--cases-per-class", type=int, default=300)

    microscopy_evolution = subparsers.add_parser("microscopy-evolution-live")
    microscopy_evolution.add_argument("--replication-root", type=Path, required=True)
    microscopy_evolution.add_argument("--output-dir", type=Path, required=True)
    microscopy_evolution.add_argument("--base-url", default="http://127.0.0.1:5100")

    microscopy_evolution_replay = subparsers.add_parser("microscopy-evolution-replay")
    microscopy_evolution_replay.add_argument("--cassette-dir", type=Path, required=True)
    microscopy_evolution_replay.add_argument("--output-dir", type=Path, required=True)

    microscopy_evolution_summary = subparsers.add_parser("microscopy-evolution-summary")
    microscopy_evolution_summary.add_argument("--cassette-dir", type=Path, required=True)

    replication = subparsers.add_parser("replication-study-live")
    replication.add_argument("--output-dir", type=Path, required=True)
    replication.add_argument("--base-url", default="http://127.0.0.1:5100")
    replication.add_argument(
        "--instrument-id",
        action="append",
        choices=REPLICATION_INSTRUMENT_IDS,
    )
    replication.add_argument("--replicate", action="append", type=int)

    replication_summary = subparsers.add_parser("replication-study-summary")
    replication_summary.add_argument("--cassette-dir", type=Path, required=True)

    independent_review = subparsers.add_parser("independent-review-live")
    independent_review.add_argument("--output-dir", type=Path, required=True)
    independent_review.add_argument("--base-url", default="http://127.0.0.1:5100")
    independent_review.add_argument(
        "--dsv4-confirmatory-root",
        type=Path,
        default=Path("cassettes/judge-metrology-confirmatory"),
    )

    independent_review_summary = subparsers.add_parser("independent-review-summary")
    independent_review_summary.add_argument("--cassette-dir", type=Path, required=True)
    independent_review_summary.add_argument(
        "--dsv4-confirmatory-root",
        type=Path,
        default=Path("cassettes/judge-metrology-confirmatory"),
    )

    engineering_burden = subparsers.add_parser("engineering-burden")
    engineering_burden.add_argument("--output-dir", type=Path, required=True)

    history_repair = subparsers.add_parser("history-repair-live")
    history_repair.add_argument("--candidate-dir", type=Path, required=True)
    history_repair.add_argument("--output-dir", type=Path, required=True)
    package_skills = subparsers.add_parser("package-confirmatory-skills")
    package_skills.add_argument("--cassette-dir", type=Path, required=True)
    package_skills.add_argument("--root", type=Path, default=Path.cwd())
    package_skills.add_argument("--output-dir", type=Path, required=True)
    package_microscopy = subparsers.add_parser("package-microscopy-skill")
    package_microscopy.add_argument("--evolution-dir", type=Path, required=True)
    package_microscopy.add_argument("--root", type=Path, default=Path.cwd())
    package_microscopy.add_argument("--output-dir", type=Path, required=True)
    model_ablation.add_argument(
        "--prompt-condition",
        choices=["original", "disclosed_executor_contract"],
        required=True,
    )

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
    elif args.command == "instrument-metrology":
        result = run_instrument_metrology(
            args.output_dir,
            cases_per_class=args.cases_per_class,
        )
    elif args.command == "instrument-study-live":
        result = run_live_instrument_study(
            args.cassette_dir,
            run_judge=not args.skip_judge,
        )
    elif args.command == "instrument-study-replay":
        result = replay_instrument_study(args.cassette_dir, args.output_dir)
    elif args.command == "evolution-live":
        result = run_live_evolution_study(args.study_cassette_dir, args.output_dir)
    elif args.command == "evolution-replay":
        result = replay_evolution_study(args.cassette_dir, args.output_dir)
    elif args.command == "judge-metrology-live":
        result = run_live_judge_metrology(args.output_dir)
    elif args.command == "judge-metrology-replay":
        result = summarize_judge_metrology(args.cassette_dir)
    elif args.command == "confirmatory-judge-metrology-live":
        result = run_live_confirmatory_judge_metrology(args.output_dir)
    elif args.command == "confirmatory-judge-metrology-replay":
        result = summarize_judge_metrology(
            args.cassette_dir,
            instrument_ids=CONFIRMATORY_INSTRUMENT_IDS,
        )
    elif args.command == "model-ablation-live":
        result = run_live_model_ablation(
            args.primary_cassette_dir,
            args.output_dir,
            study=args.study,
            prompt_condition=args.prompt_condition,
        )
    elif args.command == "locked-validation":
        candidate = CandidatePackage.model_validate_json(args.candidate.read_text(encoding="utf-8"))
        result = run_locked_validation_once(
            candidate,
            args.output_dir / "selection-seal.json",
            args.output_dir / "locked-validation.json",
        ).model_dump(mode="json")
    elif args.command == "confirmatory-metrology":
        result = run_confirmatory_metrology(
            args.output_dir,
            cases_per_class=args.cases_per_class,
        )
    elif args.command == "confirmatory-study-live":
        result = run_live_confirmatory_study(args.output_dir)
    elif args.command == "confirmatory-study-replay":
        result = replay_confirmatory_study(args.cassette_dir, args.output_dir)
    elif args.command == "confirmatory-judge-live":
        result = run_live_confirmatory_judges(args.cassette_dir)
    elif args.command == "microscopy-reference-live":
        result = capture_live_microscopy_reference(args.output_dir, base_url=args.base_url)
    elif args.command == "adaptive-microscopy-preflight":
        result = run_live_adaptive_microscopy_preflight(
            args.output_dir,
            base_url=args.base_url,
        )
    elif args.command == "adaptive-microscopy-reset":
        result = run_live_adaptive_microscopy_reset_battery(
            args.output_dir,
            base_urls=tuple(args.base_urls),
            cases_per_simulator=args.cases_per_simulator,
        )
    elif args.command == "adaptive-microscopy-curve-metrology":
        result = run_live_adaptive_microscopy_curve_metrology(
            args.output_dir,
            base_urls=tuple(args.base_urls),
            cases_per_group=args.cases_per_group,
        )
    elif args.command == "adaptive-microscopy-search-live":
        result = run_live_adaptive_microscopy_search(
            args.output_dir,
            base_url=args.base_url,
            seed_base=args.seed_base,
            smoke=args.smoke,
        )
    elif args.command == "adaptive-microscopy-uncertainty":
        result = run_live_adaptive_microscopy_uncertainty_battery(
            args.output_dir,
            base_urls=tuple(args.base_urls),
            cases_per_group=args.cases_per_group,
        )
    elif args.command == "adaptive-microscopy-metrology":
        result = run_adaptive_microscopy_metrology(
            args.output_dir,
            cases_per_class=args.cases_per_class,
        )
    elif args.command == "adaptive-microscopy-causal-repair-live":
        result = run_live_adaptive_microscopy_causal_repair(
            args.output_dir,
            candidate_path=args.candidate,
            base_urls=tuple(args.base_urls),
            seed=args.seed,
            trials=args.trials,
        )
    elif args.command == "adaptive-microscopy-causal-lock":
        result = lock_causal_development_panel(
            args.attempt_dir,
            args.output_dir,
            completed_trials=args.completed_trials,
        )
    elif args.command == "adaptive-microscopy-locked":
        result = run_live_adaptive_microscopy_locked(
            args.output_dir,
            search_path=args.search,
            base_url=args.base_url,
        )
    elif args.command == "adaptive-method-freeze":
        result = freeze_adaptive_method(
            args.output_dir,
            generated_root=args.generated_root,
        )
    elif args.command == "adaptive-method-verify":
        result = verify_adaptive_method_freeze(args.manifest)
    elif args.command == "causal-evidence-summary":
        result = summarize_accumulated_causal_evidence(
            args.output_dir,
            confirmatory_path=args.confirmatory,
            diagnostic_path=args.diagnostic,
            openflexure_lock_path=args.openflexure_lock,
        )
    elif args.command == "persistent-smoke":
        result = run_persistent_smoke(
            args.instrument,
            args.output_dir,
            parent_episode=args.parent_episode,
        )
    elif args.command == "heldout-preflight-import":
        result = import_heldout_preflight_evidence(
            args.output_dir,
            preregistration_path=args.preregistration,
            evidence_paths=tuple(args.evidence),
        )
    elif args.command == "microscopy-metrology":
        result = run_microscopy_metrology(
            np.load(args.reference_dir / "baseline.npy", allow_pickle=False),
            np.load(args.reference_dir / "focused.npy", allow_pickle=False),
            np.load(args.reference_dir / "underfocused.npy", allow_pickle=False),
            output_dir=args.output_dir,
            cases_per_class=args.cases_per_class,
        )
    elif args.command == "microscopy-evolution-live":
        result = run_live_microscopy_evolution(
            args.replication_root,
            args.output_dir,
            base_url=args.base_url,
        )
    elif args.command == "microscopy-evolution-replay":
        result = replay_microscopy_evolution(args.cassette_dir, args.output_dir)
    elif args.command == "microscopy-evolution-summary":
        result = summarize_microscopy_evolution(args.cassette_dir)
    elif args.command == "replication-study-live":
        result = run_live_replication_study(
            args.output_dir,
            instrument_ids=tuple(args.instrument_id or REPLICATION_INSTRUMENT_IDS),
            replicate_ids=None if args.replicate is None else tuple(args.replicate),
            microscopy_base_url=args.base_url,
        )
    elif args.command == "replication-study-summary":
        result = summarize_replication_study(args.cassette_dir)
        write_canonical_json(args.cassette_dir / "summary.json", result)
    elif args.command == "independent-review-live":
        result = run_live_independent_review(
            args.output_dir,
            microscopy_base_url=args.base_url,
            dsv4_confirmatory_root=args.dsv4_confirmatory_root,
        )
    elif args.command == "independent-review-summary":
        result = summarize_independent_study(
            args.cassette_dir,
            dsv4_confirmatory_root=args.dsv4_confirmatory_root,
        )
    elif args.command == "engineering-burden":
        result = run_engineering_burden(args.output_dir)
    elif args.command == "history-repair-live":
        result = run_live_history_repair(args.candidate_dir, args.output_dir)
    elif args.command == "package-confirmatory-skills":
        result = package_confirmatory_skills(
            args.cassette_dir,
            args.root,
            args.output_dir,
        )
    elif args.command == "package-microscopy-skill":
        result = package_microscopy_skill(
            args.evolution_dir,
            args.root,
            args.output_dir,
        )
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
