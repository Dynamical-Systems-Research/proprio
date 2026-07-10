"""Pre-model development gates for the adaptive OpenFlexure method."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import random
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path
from typing import Any

from proprio.adaptive_agent import AdaptiveInstrumentAgent
from proprio.adaptive_microscopy import (
    FAMILY,
    INSTRUMENT_ID,
    evaluate_live_adaptive_microscopy,
    load_adaptive_microscopy_source,
)
from proprio.adaptive_search import (
    DebugCondition,
    DebugSuiteResult,
    Evaluator,
    FixturePreflightReport,
    PreflightCase,
    RepairOutcome,
    evaluate_debug_suite,
    run_archive_search,
    run_fixture_preflight,
)
from proprio.artifacts import source_sha256, write_canonical_json
from proprio.instrument_types import CandidatePackage, FeedbackArm, SimulationScenario
from proprio.policy import OPENROUTER_BASE_URL, DSV4Client

GOOD_FIXTURE = """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    first = controller.fast_autofocus(2000)
    if first["position_z"] > 100 or first["position_z"] < -100:
        controller.fast_autofocus(4000)
    controller.settle()
    measurement = controller.capture_focus_series(3)
    controller.release()
    return {"position_z": measurement["position_z"], "repeats": measurement["repeats"]}
"""

INVALID_FIXTURE = """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus(2000)
    controller.settle()
    measurement = controller.capture_focus_series(2)
    controller.release()
    return {"position_z": measurement["position_z"]}
"""

SKILL_MD = """---
name: microscope-autofocus
description: Calibrate focus, acquire repeated frames, and release resources.
---
# Run
Execute a bounded adaptive autofocus procedure using repeated image evidence.
"""

UNCERTAINTY_CHECK = "temporal-measurement-uncertainty"
ROOT = Path(__file__).resolve().parents[2]


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)

CAUSAL_PROTOCOL_INPUTS = (
    "src/proprio/instrument_agent.py",
    "src/proprio/adaptive_agent.py",
    "src/proprio/adaptive_microscopy.py",
    "src/proprio/adaptive_microscopy_study.py",
    "src/proprio/adaptive_microscopy_verifier.py",
    "src/proprio/instrument_qualification.py",
    "src/proprio/data/adaptive-method-preregistration.yaml",
    "src/proprio/data/adaptive-microscopy-thresholds.yaml",
    "sources/development/microscope-autofocus/source.md",
)


class CausalFault(StrEnum):
    TEMPORAL_PRECISION = "temporal_precision"
    SWEEP_COVERAGE = "sweep_coverage"
    STAGE_READBACK = "stage_readback"


CAUSAL_EXPECTED_CHECK = {
    CausalFault.TEMPORAL_PRECISION: "temporal-measurement-uncertainty",
    CausalFault.SWEEP_COVERAGE: "autofocus-reference-covered",
    CausalFault.STAGE_READBACK: "autofocus-peak-selected",
}

# Frozen method budget: one initial candidate followed by at most four
# evidence-conditioned repair episodes. Every causal arm receives the same
# maximum budget; deterministic admission may stop an arm early.
ADAPTIVE_REPAIR_EPISODES = 4

CAUSAL_EXPECTED_REPAIR = {
    CausalFault.TEMPORAL_PRECISION: "repeat-evidence",
    CausalFault.SWEEP_COVERAGE: "sweep-coverage",
    CausalFault.STAGE_READBACK: "stage-correction",
}

CAUSAL_GOLDEN_SKILLS = {
    CausalFault.TEMPORAL_PRECISION: """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus(4000)
    controller.settle()
    measurement = controller.capture_focus_series(5)
    controller.settle()
    measurement = controller.capture_focus_series(5)
    controller.release()
    return {"position_z": measurement["position_z"], "repeats": measurement["repeats"]}
""",
    CausalFault.SWEEP_COVERAGE: """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus(8000)
    controller.settle()
    measurement = controller.capture_focus_series(3)
    controller.release()
    return {"position_z": measurement["position_z"], "repeats": measurement["repeats"]}
""",
    CausalFault.STAGE_READBACK: """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    result = controller.fast_autofocus(4000)
    controller.move_z(0 - result["position_z"])
    controller.settle()
    measurement = controller.capture_focus_series(3)
    controller.release()
    return {"position_z": measurement["position_z"], "repeats": measurement["repeats"]}
""",
}


def fixture_candidate(source: str) -> CandidatePackage:
    _, source_hash = load_adaptive_microscopy_source(INSTRUMENT_ID)
    return CandidatePackage(
        instrument_id=INSTRUMENT_ID,
        skill_md=SKILL_MD,
        skill_py=source,
        self_judgment={"verdict": "ACCEPT", "basis": ["preregistered fixture"]},
        source_sha256=source_hash,
        prompt_sha256=hashlib.sha256(b"adaptive-microscopy-preflight").hexdigest(),
        model="preregistered-fixture",
        raw_response={},
    )


def adaptive_microscopy_preflight_cases() -> tuple[PreflightCase, ...]:
    good = fixture_candidate(GOOD_FIXTURE)
    bad = fixture_candidate(INVALID_FIXTURE)
    return (
        PreflightCase(
            case_id="known-valid-adaptive-autofocus",
            candidate=good,
            condition=DebugCondition(
                condition_id="preflight-valid",
                scenario=SimulationScenario.REPAIR,
                parameters=(("start_z", 1600.0),),
                repetitions=1,
            ),
            expected_verdict="ADMIT",
        ),
        PreflightCase(
            case_id="known-invalid-short-sweep-and-repeat-count",
            candidate=bad,
            condition=DebugCondition(
                condition_id="preflight-invalid",
                scenario=SimulationScenario.REPAIR,
                parameters=(("start_z", 1600.0),),
                repetitions=1,
            ),
            expected_verdict="REJECT",
            required_failed_checks=("calibrated-focus-reference", "repeat-count"),
        ),
        PreflightCase(
            case_id="known-unavailable-simulator",
            candidate=good,
            condition=DebugCondition(
                condition_id="preflight-unavailable",
                scenario=SimulationScenario.UNAVAILABLE,
                repetitions=1,
            ),
            expected_verdict="HOLD",
        ),
    )


def run_live_adaptive_microscopy_preflight(
    output_dir: Path,
    *,
    base_url: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    def evaluator(instrument_id: str, source: str, **kwargs: Any):
        return evaluate_live_adaptive_microscopy(
            instrument_id,
            source,
            base_url=base_url,
            **kwargs,
        )

    report = run_fixture_preflight(
        adaptive_microscopy_preflight_cases(),
        evaluator=evaluator,
    )
    write_canonical_json(output_dir / "preflight.json", report)
    summary = {
        "schema_version": "proprio.adaptive_microscopy_preflight_summary.v0.2",
        "instrument_id": INSTRUMENT_ID,
        "simulator_base_url": base_url,
        "cases": len(report.cases),
        "case_outcomes": {
            row.case_id: {
                "expected": row.expected_verdict,
                "observed": row.observed.verdict,
                "passed": row.passed,
            }
            for row in report.cases
        },
        "verdict": report.verdict,
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def run_live_adaptive_microscopy_reset_battery(
    output_dir: Path,
    *,
    base_urls: tuple[str, ...],
    cases_per_simulator: int = 5,
) -> dict[str, Any]:
    """Prove repeated reset converges from persisted upstream sample state."""

    if len(base_urls) != len(set(base_urls)) or not base_urls:
        raise ValueError("reset battery requires unique simulator base URLs")
    if cases_per_simulator < 5:
        raise ValueError("reset battery requires at least five cases per simulator")
    output_dir.mkdir(parents=True, exist_ok=True)

    def run_partition(base_url: str) -> list[dict[str, Any]]:
        rows = []
        simulator_id = hashlib.sha256(base_url.encode()).hexdigest()[:12]
        for index in range(cases_per_simulator):
            gate = evaluate_live_adaptive_microscopy(
                INSTRUMENT_ID,
                GOOD_FIXTURE,
                scenario=SimulationScenario.REPAIR,
                condition={"start_z": (400.0, 800.0, 1200.0, 1600.0, 1800.0)[index % 5]},
                base_url=base_url,
            )
            row = {
                "simulator_base_url": base_url,
                "index": index,
                "verdict": gate.verdict,
                "runtime_error": gate.runtime_error,
                "gate": gate.model_dump(mode="json"),
            }
            rows.append(row)
            write_canonical_json(
                output_dir / f"reset-{simulator_id}-{index:03d}.json",
                row,
            )
        return rows

    with ThreadPoolExecutor(max_workers=len(base_urls)) as pool:
        nested = tuple(pool.map(run_partition, base_urls))
    rows = [row for partition in nested for row in partition]
    failures = [row for row in rows if row["verdict"] != "ADMIT"]
    summary = {
        "schema_version": "proprio.adaptive_reset_battery.v0.2",
        "instrument_id": INSTRUMENT_ID,
        "simulator_base_urls": list(base_urls),
        "cases_per_simulator": cases_per_simulator,
        "cases": len(rows),
        "failures": len(failures),
        "verdict": "PASS" if not failures else "FAIL",
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def run_live_adaptive_microscopy_curve_metrology(
    output_dir: Path,
    *,
    base_urls: tuple[str, ...],
    cases_per_group: int = 20,
) -> dict[str, Any]:
    if cases_per_group < 20:
        raise ValueError("curve metrology requires at least twenty cases per group")
    if not base_urls or len(base_urls) != len(set(base_urls)):
        raise ValueError("curve metrology requires unique isolated simulator URLs")
    output_dir.mkdir(parents=True, exist_ok=True)
    valid_starts = (400.0, 800.0, 1200.0, 1600.0, 1800.0)
    invalid_starts = (1400.0, 1600.0, 1800.0, 2000.0)
    groups = (
        ("valid", GOOD_FIXTURE, valid_starts, "ADMIT"),
        ("invalid", INVALID_FIXTURE, invalid_starts, "REJECT"),
    )
    tasks = [
        (label, source, starts, expected, index)
        for label, source, starts, expected in groups
        for index in range(cases_per_group)
    ]

    def run_partition(base_url: str, partition) -> list[dict[str, Any]]:
        partition_rows = []
        for label, source, starts, expected, index in partition:
            start_z = starts[index % len(starts)]
            gate = evaluate_live_adaptive_microscopy(
                INSTRUMENT_ID,
                source,
                scenario=SimulationScenario.REPAIR,
                condition={"start_z": start_z},
                base_url=base_url,
            )
            row = {
                "label": label,
                "index": index,
                "simulator_base_url": base_url,
                "start_z": start_z,
                "expected": expected,
                "observed": gate.verdict,
                "failed_checks": [check.check_id for check in gate.checks if not check.passed],
                "gate": gate.model_dump(mode="json"),
            }
            partition_rows.append(row)
            write_canonical_json(output_dir / f"{label}-{index:03d}.json", row)
        return partition_rows

    partitions = tuple(tuple(tasks[index:: len(base_urls)]) for index in range(len(base_urls)))
    with ThreadPoolExecutor(max_workers=len(base_urls)) as pool:
        nested = tuple(pool.map(run_partition, base_urls, partitions))
    rows = [row for partition in nested for row in partition]
    valid_rows = [row for row in rows if row["label"] == "valid"]
    invalid_rows = [row for row in rows if row["label"] == "invalid"]
    false_reject = sum(row["observed"] != "ADMIT" for row in valid_rows)
    false_valid = sum(row["observed"] == "ADMIT" for row in invalid_rows)
    passed = false_valid == 0 and false_reject / len(valid_rows) <= 0.05
    summary = {
        "schema_version": "proprio.adaptive_microscopy_curve_metrology.v0.2",
        "instrument_id": INSTRUMENT_ID,
        "cases_per_group": cases_per_group,
        "simulator_base_urls": list(base_urls),
        "valid_starts": list(valid_starts),
        "invalid_starts": list(invalid_starts),
        "valid_admitted": sum(row["observed"] == "ADMIT" for row in valid_rows),
        "invalid_rejected": sum(row["observed"] == "REJECT" for row in invalid_rows),
        "false_reject_count": false_reject,
        "false_valid_count": false_valid,
        "verdict": "PASS" if passed else "FAIL",
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def run_live_adaptive_microscopy_uncertainty_battery(
    output_dir: Path,
    *,
    base_urls: tuple[str, ...],
    cases_per_group: int = 20,
) -> dict[str, Any]:
    """Measure the preregistered repeat-count operating point on fresh simulator runs."""

    if cases_per_group < 20:
        raise ValueError("uncertainty battery requires at least twenty cases per group")
    if not base_urls:
        raise ValueError("uncertainty battery requires at least one isolated simulator")
    if len(base_urls) != len(set(base_urls)):
        raise ValueError("simulator base URLs must be unique")
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = (
        ("valid-three-repeats", 2.0, (3,), "ADMIT"),
        ("invalid-three-repeats", 4.0, (3,), "REJECT"),
        ("repairable-ten-repeats", 4.0, (5, 5), "ADMIT"),
    )
    tasks: list[tuple[str, float, tuple[int, ...], str, int]] = []
    for group, noise_level, repeat_series, expected in groups:
        tasks.extend(
            (group, noise_level, repeat_series, expected, index)
            for index in range(cases_per_group)
        )

    def run_partition(
        base_url: str,
        partition: tuple[tuple[str, float, tuple[int, ...], str, int], ...],
    ) -> list[dict[str, Any]]:
        partition_rows: list[dict[str, Any]] = []
        for group, noise_level, repeat_series, expected, index in partition:
            acquisition = "\n".join(
                (
                    f"    measurement = controller.capture_focus_series({repeats})"
                    if series_index == 0
                    else "    controller.settle()\n"
                    f"    measurement = controller.capture_focus_series({repeats})"
                )
                for series_index, repeats in enumerate(repeat_series)
            )
            source = GOOD_FIXTURE.replace(
                "    measurement = controller.capture_focus_series(3)",
                acquisition,
            )
            start_z = (400.0, 800.0, 1200.0, 1600.0, 1800.0)[index % 5]
            gate = evaluate_live_adaptive_microscopy(
                INSTRUMENT_ID,
                source,
                scenario=SimulationScenario.REPAIR,
                condition={
                    "start_z": start_z,
                    "measurement_noise_level": noise_level,
                },
                base_url=base_url,
            )
            check = next(check for check in gate.checks if check.check_id == UNCERTAINTY_CHECK)
            row = {
                "group": group,
                "index": index,
                "simulator_base_url": base_url,
                "start_z": start_z,
                "measurement_noise_level": noise_level,
                "repeat_series": list(repeat_series),
                "total_repeats": sum(repeat_series),
                "expected": expected,
                "observed": gate.verdict,
                "uncertainty_check": check.model_dump(mode="json"),
                "gate": gate.model_dump(mode="json"),
            }
            partition_rows.append(row)
            write_canonical_json(output_dir / f"{group}-{index:03d}.json", row)
        return partition_rows

    partitions = tuple(
        tuple(tasks[index:: len(base_urls)]) for index in range(len(base_urls))
    )
    with ThreadPoolExecutor(max_workers=len(base_urls)) as pool:
        nested_rows = tuple(pool.map(run_partition, base_urls, partitions))
    rows = [row for partition in nested_rows for row in partition]
    group_summaries: dict[str, dict[str, Any]] = {}
    for group, _, _, expected in groups:
        selected = [row for row in rows if row["group"] == group]
        errors = sum(row["observed"] != expected for row in selected)
        group_summaries[group] = {
            "cases": len(selected),
            "expected": expected,
            "errors": errors,
            "error_rate": errors / len(selected),
            "observed_admit": sum(row["observed"] == "ADMIT" for row in selected),
            "observed_reject": sum(row["observed"] == "REJECT" for row in selected),
        }
    invalid = group_summaries["invalid-three-repeats"]
    valid_groups = (
        group_summaries["valid-three-repeats"],
        group_summaries["repairable-ten-repeats"],
    )
    passed = invalid["observed_admit"] == 0 and all(
        group["error_rate"] <= 0.05 for group in valid_groups
    )
    summary = {
        "schema_version": "proprio.adaptive_uncertainty_battery.v0.2",
        "instrument_id": INSTRUMENT_ID,
        "simulator_base_urls": list(base_urls),
        "cases_per_group": cases_per_group,
        "threshold_source": "src/proprio/data/adaptive-microscopy-thresholds.yaml",
        "groups": group_summaries,
        "false_valid_count": invalid["observed_admit"],
        "false_reject_count": sum(group["errors"] for group in valid_groups),
        "verdict": "PASS" if passed else "FAIL",
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def adaptive_microscopy_causal_conditions(
    fault: CausalFault,
    *,
    trial_index: int,
    locked: bool,
) -> tuple[DebugCondition, ...]:
    """Return one nominal replay and one source-underdetermined runtime challenge."""

    history = DebugCondition(
        condition_id=f"{'locked' if locked else 'visible'}-history",
        scenario=SimulationScenario.REPAIR,
        parameters=(("start_z", 600.0 if locked else 800.0),),
        repetitions=1,
    )
    sign = -1.0 if trial_index % 2 else 1.0
    if fault is CausalFault.TEMPORAL_PRECISION:
        parameters = (
            ("start_z", 600.0 if locked else 800.0),
            ("measurement_noise_level", 4.0),
        )
        repetitions = 3
    elif fault is CausalFault.SWEEP_COVERAGE:
        parameters = (("start_z", sign * (3400.0 if locked else 3500.0)),)
        repetitions = 1
    else:
        parameters = (
            ("start_z", 600.0 if locked else 800.0),
            ("stage_bias_steps", sign * (350.0 if locked else 300.0)),
        )
        repetitions = 1
    challenge = DebugCondition(
        condition_id=f"{'locked' if locked else 'visible'}-{fault.value}-{trial_index:03d}",
        scenario=SimulationScenario.REPAIR,
        parameters=parameters,
        repetitions=repetitions,
    )
    return history, challenge


def _repair_signature(parent_source: str, child_source: str) -> str:
    def calls(source: str) -> dict[str, list[float]]:
        tree = ast.parse(source)
        result: dict[str, list[float]] = {
            "capture_focus_series": [],
            "fast_autofocus": [],
            "move_z": [],
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in result:
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                result[node.func.attr].append(math.nan)
            else:
                result[node.func.attr].append(float(node.args[0].value))
        return result

    before = calls(parent_source)
    after = calls(child_source)
    repeated_evidence = max(after["capture_focus_series"], default=-math.inf) > max(
        before["capture_focus_series"], default=-math.inf
    )
    expanded_coverage = max(after["fast_autofocus"], default=-math.inf) > max(
        before["fast_autofocus"], default=-math.inf
    ) or len(after["fast_autofocus"]) > len(before["fast_autofocus"])
    stage_correction = len(after["move_z"]) > len(before["move_z"])
    # A second autofocus after bounded repositioning is a coverage-recovery
    # strategy, even though it also uses move_z.
    if repeated_evidence:
        return "repeat-evidence"
    if expanded_coverage:
        return "sweep-coverage"
    if stage_correction:
        return "stage-correction"
    return "other"


def _refresh_suite_if_stale(
    candidate: CandidatePackage,
    suite: DebugSuiteResult,
    conditions: tuple[DebugCondition, ...],
    *,
    evaluator: Evaluator,
) -> tuple[DebugSuiteResult, bool]:
    candidate_sha = hashlib.sha256(candidate.skill_py.encode()).hexdigest()
    if suite.candidate_sha256 == candidate_sha:
        return suite, False
    return evaluate_debug_suite(candidate, conditions, evaluator=evaluator), True


def _load_completed_causal_trial(
    trial_dir: Path,
    *,
    trial_index: int,
    fault: CausalFault,
    model_seed: int,
) -> dict[str, Any] | None:
    summary_path = trial_dir / "summary.json"
    if not summary_path.is_file():
        return None
    row = json.loads(summary_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": "proprio.causal_repair_trial.v0.2",
        "trial_index": trial_index,
        "model_seed": model_seed,
        "fault": fault.value,
        "maximum_repair_episodes_per_arm": ADAPTIVE_REPAIR_EPISODES,
    }
    observed = {key: row.get(key) for key in expected}
    if observed != expected:
        raise RuntimeError(
            f"completed causal trial does not match the active protocol: {summary_path}"
        )
    outcomes = row.get("outcomes") or {}
    if set(outcomes) != {arm.value for arm in FeedbackArm}:
        raise RuntimeError(f"completed causal trial has incomplete arms: {summary_path}")
    for arm in FeedbackArm:
        outcome = outcomes[arm.value]
        rounds = int(outcome.get("rounds_used", 0))
        if rounds < 1 or rounds > ADAPTIVE_REPAIR_EPISODES:
            raise RuntimeError(f"completed causal trial has invalid repair count: {summary_path}")
        if not (trial_dir / f"locked-{arm.value}.json").is_file():
            raise RuntimeError(f"completed causal trial omitted locked replay: {summary_path}")
        if any(
            not (trial_dir / f"repair-{arm.value}-round-{round_index}.json").is_file()
            for round_index in range(1, rounds + 1)
        ):
            raise RuntimeError(f"completed causal trial omitted repair episodes: {summary_path}")
    return row


def _causal_run_manifest(
    candidate: CandidatePackage,
    *,
    seed: int,
    trials: int,
    base_urls: tuple[str, ...],
    faults: list[CausalFault],
) -> dict[str, Any]:
    return {
        "schema_version": "proprio.causal_run_manifest.v0.2",
        "instrument_id": INSTRUMENT_ID,
        "model": "deepseek/deepseek-v4-flash",
        "provider": "GMICloud",
        "reasoning_effort": "high",
        "paired_seed_base": seed,
        "trials": trials,
        "fault_assignment": [fault.value for fault in faults],
        "base_urls": list(base_urls),
        "maximum_repair_episodes_per_arm": ADAPTIVE_REPAIR_EPISODES,
        "candidate_sha256": hashlib.sha256(candidate.skill_py.encode()).hexdigest(),
        "source_sha256": candidate.source_sha256,
        "protocol_inputs": {
            relative: source_sha256(ROOT / relative) for relative in CAUSAL_PROTOCOL_INPUTS
        },
    }


def _exact_mcnemar_one_sided(favorable: int, unfavorable: int) -> float:
    discordant = favorable + unfavorable
    if discordant == 0:
        return 1.0
    return sum(
        math.comb(discordant, value) * 0.5**discordant
        for value in range(favorable, discordant + 1)
    )


def summarize_causal_trials(rows: list[dict[str, Any]], *, required_trials: int) -> dict[str, Any]:
    arms = tuple(arm.value for arm in FeedbackArm)
    rates = {
        arm: sum(row["outcomes"][arm]["qualified"] for row in rows) / max(len(rows), 1)
        for arm in arms
    }
    favorable = sum(
        row["outcomes"][FeedbackArm.TRUTHFUL.value]["qualified"]
        and not row["outcomes"][FeedbackArm.NONE.value]["qualified"]
        for row in rows
    )
    unfavorable = sum(
        not row["outcomes"][FeedbackArm.TRUTHFUL.value]["qualified"]
        and row["outcomes"][FeedbackArm.NONE.value]["qualified"]
        for row in rows
    )
    by_fault: dict[str, dict[str, Any]] = {}
    for fault in CausalFault:
        selected = [row for row in rows if row["fault"] == fault.value]
        by_fault[fault.value] = {
            "trials": len(selected),
            "truthful_qualified": sum(
                row["outcomes"][FeedbackArm.TRUTHFUL.value]["qualified"]
                for row in selected
            ),
            "none_qualified": sum(
                row["outcomes"][FeedbackArm.NONE.value]["qualified"] for row in selected
            ),
        }
    truthful_concordance = sum(
        row["outcomes"][FeedbackArm.TRUTHFUL.value]["repair_signature"]
        == CAUSAL_EXPECTED_REPAIR[CausalFault(row["fault"])]
        for row in rows
    ) / max(len(rows), 1)
    mismatched_concordance = sum(
        row["outcomes"][FeedbackArm.MISMATCHED.value]["repair_signature"]
        == CAUSAL_EXPECTED_REPAIR[CausalFault(row["fault"])]
        for row in rows
    ) / max(len(rows), 1)
    risk_difference = rates[FeedbackArm.TRUTHFUL.value] - rates[FeedbackArm.NONE.value]
    mismatched_uplift = (
        rates[FeedbackArm.TRUTHFUL.value] - rates[FeedbackArm.MISMATCHED.value]
    )
    mcnemar_p = _exact_mcnemar_one_sided(favorable, unfavorable)
    enough_trials = len(rows) == required_trials and required_trials >= 30
    passed = (
        enough_trials
        and rates[FeedbackArm.TRUTHFUL.value] >= 0.8
        and risk_difference >= 0.25
        and mismatched_uplift >= 0.25
        and mcnemar_p < 0.05
        and truthful_concordance >= 0.8
        and mismatched_concordance <= 0.35
        and all(
            group["trials"] >= 10 and group["truthful_qualified"] / group["trials"] >= 0.7
            for group in by_fault.values()
        )
    )
    return {
        "trials": len(rows),
        "required_trials": required_trials,
        "arm_qualification_rates": rates,
        "truthful_minus_none": risk_difference,
        "truthful_minus_mismatched": mismatched_uplift,
        "mcnemar": {
            "truthful_only": favorable,
            "none_only": unfavorable,
            "one_sided_exact_p": mcnemar_p,
        },
        "truthful_trace_to_edit_concordance": truthful_concordance,
        "mismatched_actual_fault_concordance": mismatched_concordance,
        "by_fault": by_fault,
        "verdict": "PASS" if passed else ("INCOMPLETE" if not enough_trials else "FAIL"),
    }


def lock_causal_development_panel(
    attempt_dir: Path,
    output_dir: Path,
    *,
    completed_trials: int = 4,
) -> dict[str, Any]:
    """Seal a stopped causal panel without converting it into confirmatory evidence."""

    manifest_path = attempt_dir / "run-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"causal run manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "proprio.causal_run_manifest.v0.2":
        raise RuntimeError("causal run manifest has an unsupported schema")
    registered_trials = int(manifest.get("trials", 0))
    if completed_trials < 1 or completed_trials >= registered_trials:
        raise ValueError("development lock requires a strict subset of registered trials")
    seed = int(manifest.get("paired_seed_base", -1))
    fault_assignment = manifest.get("fault_assignment") or []
    if len(fault_assignment) != registered_trials:
        raise RuntimeError("causal run manifest has an incomplete fault assignment")

    rows: list[dict[str, Any]] = []
    trial_evidence: list[dict[str, Any]] = []
    for trial_index in range(completed_trials):
        fault = CausalFault(fault_assignment[trial_index])
        trial_dir = attempt_dir / "trials" / f"trial-{trial_index:03d}"
        row = _load_completed_causal_trial(
            trial_dir,
            trial_index=trial_index,
            fault=fault,
            model_seed=seed + trial_index,
        )
        if row is None:
            raise RuntimeError(f"causal development trial is incomplete: {trial_dir}")
        rows.append(row)
        summary_path = trial_dir / "summary.json"
        trial_evidence.append(
            {
                "trial_index": trial_index,
                "path": _display_path(summary_path),
                "sha256": source_sha256(summary_path),
            }
        )

    partial_indices = [
        trial_index
        for trial_index in range(completed_trials, registered_trials)
        if (attempt_dir / "trials" / f"trial-{trial_index:03d}").exists()
    ]
    analysis = summarize_causal_trials(rows, required_trials=registered_trials)
    if analysis["verdict"] != "INCOMPLETE":
        raise RuntimeError("stopped development panel must remain incomplete confirmatory evidence")
    payload = {
        "schema_version": "proprio.causal_development_lock.v0.2",
        "status": "EXPLORATORY_LOCKED",
        "confirmatory_status": "NOT_ESTABLISHED",
        "claim_boundary": (
            "The four completed trials are exploratory method-development evidence. They do not "
            "establish the preregistered 30-trial causal claim or cross-family generalization."
        ),
        "decision": (
            "Freeze the method configuration after four completed trials and allocate remaining "
            "live inference to the binding held-out-family study."
        ),
        "registered_trials": registered_trials,
        "completed_trials": completed_trials,
        "locked_trial_indices": list(range(completed_trials)),
        "excluded_partial_trial_indices": partial_indices,
        "source_manifest": {
            "path": _display_path(manifest_path),
            "sha256": source_sha256(manifest_path),
        },
        "trial_evidence": trial_evidence,
        "analysis": analysis,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_canonical_json(output_dir / "summary.json", payload)
    return payload


def _run_causal_confusion_preflight(
    candidate: CandidatePackage,
    *,
    evaluator: Any,
) -> dict[str, Any]:
    nominal = adaptive_microscopy_causal_conditions(
        CausalFault.TEMPORAL_PRECISION, trial_index=0, locked=False
    )[:1]
    parent_nominal = evaluate_debug_suite(candidate, nominal, evaluator=evaluator)
    matrix: dict[str, dict[str, str]] = {}
    cells: dict[str, dict[str, dict[str, Any]]] = {}
    for repair_fault, source in CAUSAL_GOLDEN_SKILLS.items():
        golden = fixture_candidate(source)
        matrix[repair_fault.value] = {}
        cells[repair_fault.value] = {}
        for challenge_fault in CausalFault:
            visible = adaptive_microscopy_causal_conditions(
                challenge_fault, trial_index=0, locked=False
            )
            locked = adaptive_microscopy_causal_conditions(
                challenge_fault, trial_index=0, locked=True
            )
            visible_result = evaluate_debug_suite(golden, visible, evaluator=evaluator)
            locked_result = evaluate_debug_suite(golden, locked, evaluator=evaluator)
            matrix[repair_fault.value][challenge_fault.value] = (
                "ADMIT"
                if visible_result.verdict == "ADMIT" and locked_result.verdict == "ADMIT"
                else "REJECT"
            )
            cells[repair_fault.value][challenge_fault.value] = {
                "visible": visible_result.model_dump(mode="json"),
                "locked": locked_result.model_dump(mode="json"),
            }
    diagonal = all(matrix[fault.value][fault.value] == "ADMIT" for fault in CausalFault)
    max_static_coverage = max(
        sum(verdict == "ADMIT" for verdict in row.values()) / len(CausalFault)
        for row in matrix.values()
    )
    passed = parent_nominal.verdict == "ADMIT" and diagonal and max_static_coverage <= 0.4
    return {
        "schema_version": "proprio.causal_confusion_preflight.v0.2",
        "parent_nominal": parent_nominal.verdict,
        "parent_nominal_suite": parent_nominal.model_dump(mode="json"),
        "matrix": matrix,
        "cells": cells,
        "golden_diagonal": diagonal,
        "maximum_static_repair_coverage": max_static_coverage,
        "verdict": "PASS" if passed else "FAIL",
    }


def run_live_adaptive_microscopy_causal_repair(
    output_dir: Path,
    *,
    candidate_path: Path,
    base_urls: tuple[str, ...],
    seed: int,
    trials: int = 30,
) -> dict[str, Any]:
    """Run a balanced, paired causal study over source-underdetermined runtime faults."""

    if trials < 1 or trials % len(CausalFault):
        raise ValueError("causal trial count must be a positive multiple of three")
    if len(base_urls) < len(FeedbackArm):
        raise ValueError("causal arms require four isolated simulator base URLs")
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = CandidatePackage.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    _, source_hash = load_adaptive_microscopy_source(INSTRUMENT_ID)
    if candidate.source_sha256 != source_hash:
        raise ValueError("causal parent source hash does not match the current neutral source")
    faults = [fault for fault in CausalFault for _ in range(trials // len(CausalFault))]
    random.Random(seed).shuffle(faults)
    run_manifest = _causal_run_manifest(
        candidate,
        seed=seed,
        trials=trials,
        base_urls=base_urls,
        faults=faults,
    )
    manifest_path = output_dir / "run-manifest.json"
    if manifest_path.is_file():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing_manifest != run_manifest:
            raise RuntimeError("causal run manifest does not match the active protocol")
    else:
        write_canonical_json(manifest_path, run_manifest)

    def evaluator_for(base_url: str):
        def evaluate(instrument_id: str, source: str, **kwargs: Any):
            return evaluate_live_adaptive_microscopy(
                instrument_id,
                source,
                base_url=base_url,
                **kwargs,
            )

        return evaluate

    preflight_summary = run_live_adaptive_microscopy_preflight(
        output_dir / "fixture-preflight",
        base_url=base_urls[0],
    )
    if preflight_summary["verdict"] != "PASS":
        raise RuntimeError("fixture preflight failed before causal model invocation")
    confusion = _run_causal_confusion_preflight(
        candidate,
        evaluator=evaluator_for(base_urls[0]),
    )
    write_canonical_json(output_dir / "confusion-preflight.json", confusion)
    if confusion["verdict"] != "PASS":
        raise RuntimeError("causal repair confusion preflight failed before model invocation")
    write_canonical_json(output_dir / "parent.json", candidate)

    rows: list[dict[str, Any]] = []
    resumed_trials = 0
    for trial_index, fault in enumerate(faults):
        trial_dir = output_dir / "trials" / f"trial-{trial_index:03d}"
        completed = _load_completed_causal_trial(
            trial_dir,
            trial_index=trial_index,
            fault=fault,
            model_seed=seed + trial_index,
        )
        if completed is not None:
            rows.append(completed)
            resumed_trials += 1
            continue
        visible = adaptive_microscopy_causal_conditions(
            fault, trial_index=trial_index, locked=False
        )
        locked = adaptive_microscopy_causal_conditions(
            fault, trial_index=trial_index, locked=True
        )
        opposite = list(CausalFault)[(list(CausalFault).index(fault) + 1) % len(CausalFault)]
        opposite_conditions = adaptive_microscopy_causal_conditions(
            opposite, trial_index=trial_index, locked=False
        )
        initial_suite = evaluate_debug_suite(
            candidate, visible, evaluator=evaluator_for(base_urls[0])
        )
        mismatched_suite = evaluate_debug_suite(
            candidate, opposite_conditions, evaluator=evaluator_for(base_urls[0])
        )
        failed_checks = {
            check.check_id
            for row in initial_suite.conditions
            for gate in row.gates
            for check in gate.checks
            if not check.passed
        }
        expected_check = CAUSAL_EXPECTED_CHECK[fault]
        if initial_suite.verdict != "REJECT" or expected_check not in failed_checks:
            raise RuntimeError(
                f"trial {trial_index} is ineligible for {fault.value}: {sorted(failed_checks)}"
            )
        arm_order = list(FeedbackArm)
        random.Random(seed + trial_index).shuffle(arm_order)
        trial_dir.mkdir(parents=True, exist_ok=True)
        write_canonical_json(trial_dir / "initial-suite.json", initial_suite)
        write_canonical_json(trial_dir / "mismatched-suite.json", mismatched_suite)

        def run_arm(
            item: tuple[int, FeedbackArm],
            *,
            trial_seed: int = seed + trial_index,
            visible_conditions: tuple[DebugCondition, ...] = visible,
            initial: Any = initial_suite,
            mismatched: Any = mismatched_suite,
            locked_conditions: tuple[DebugCondition, ...] = locked,
            opposite_visible: tuple[DebugCondition, ...] = opposite_conditions,
            artifact_dir: Path = trial_dir,
        ):
            position, arm = item
            evaluator = evaluator_for(base_urls[position])
            current = candidate
            current_suite = initial
            current_mismatched = mismatched
            episodes = []
            forced_replays = 0
            for round_index in range(ADAPTIVE_REPAIR_EPISODES):
                agent = AdaptiveInstrumentAgent(
                    client=_openrouter_client(),
                    source_loader=load_adaptive_microscopy_source,
                    evaluator=evaluator,
                    families={INSTRUMENT_ID: FAMILY},
                    sampling_temperature=0.0,
                    sampling_top_p=1.0,
                    sampling_seed=trial_seed + round_index * 1_000_000,
                )
                try:
                    episode = agent.repair_candidate(
                        current,
                        visible_conditions,
                        feedback_arm=arm,
                        initial_suite=current_suite,
                        mismatched_suite=(
                            current_mismatched if arm is FeedbackArm.MISMATCHED else None
                        ),
                        max_turns=8,
                    )
                finally:
                    agent.client.close()
                episodes.append(episode)
                write_canonical_json(
                    artifact_dir / f"repair-{arm.value}-round-{round_index + 1}.json",
                    episode,
                )
                current = episode.final_candidate
                current_suite, replayed = _refresh_suite_if_stale(
                    current,
                    episode.final_suite,
                    visible_conditions,
                    evaluator=evaluator,
                )
                if replayed:
                    forced_replays += 1
                    write_canonical_json(
                        artifact_dir
                        / f"post-episode-replay-{arm.value}-round-{round_index + 1}.json",
                        current_suite,
                    )
                if episode.agent_status == "CANDIDATE" and current_suite.verdict == "ADMIT":
                    break
                if arm is FeedbackArm.MISMATCHED:
                    current_mismatched = evaluate_debug_suite(
                        current,
                        opposite_visible,
                        evaluator=evaluator,
                    )
            locked_suite = evaluate_debug_suite(
                current,
                locked_conditions,
                evaluator=evaluator,
            )
            write_canonical_json(artifact_dir / f"locked-{arm.value}.json", locked_suite)
            return arm, tuple(episodes), current_suite, locked_suite, forced_replays

        with ThreadPoolExecutor(max_workers=len(FeedbackArm)) as pool:
            arm_results = list(pool.map(run_arm, enumerate(arm_order)))
        outcomes: dict[str, dict[str, Any]] = {}
        for arm, episodes, final_visible_suite, locked_suite, forced_replays in arm_results:
            final_episode = episodes[-1]
            changed = final_episode.final_candidate.skill_py != candidate.skill_py
            qualified = (
                changed
                and final_episode.agent_status == "CANDIDATE"
                and any(episode.submission is not None for episode in episodes)
                and final_visible_suite.verdict == "ADMIT"
                and locked_suite.verdict == "ADMIT"
            )
            outcome = {
                "agent_status": final_episode.agent_status,
                "changed": changed,
                "visible_verdict": final_visible_suite.verdict,
                "locked_verdict": locked_suite.verdict,
                "qualified": qualified,
                "rounds_used": len(episodes),
                "forced_post_episode_replays": forced_replays,
                "repair_signature": _repair_signature(
                    candidate.skill_py, final_episode.final_candidate.skill_py
                ),
            }
            outcomes[arm.value] = outcome
        row = {
            "schema_version": "proprio.causal_repair_trial.v0.2",
            "trial_index": trial_index,
            "model_seed": seed + trial_index,
            "fault": fault.value,
            "expected_check": expected_check,
            "expected_repair": CAUSAL_EXPECTED_REPAIR[fault],
            "mismatched_fault": opposite.value,
            "arm_order": [arm.value for arm in arm_order],
            "simulator_slot_by_arm": {
                arm.value: position for position, arm in enumerate(arm_order)
            },
            "maximum_repair_episodes_per_arm": ADAPTIVE_REPAIR_EPISODES,
            "initial_failed_checks": sorted(failed_checks),
            "outcomes": outcomes,
        }
        rows.append(row)
        write_canonical_json(trial_dir / "summary.json", row)

    analysis = summarize_causal_trials(rows, required_trials=trials)
    summary = {
        "schema_version": "proprio.adaptive_causal_repair.v0.2",
        "instrument_id": INSTRUMENT_ID,
        "parent_source": str(candidate_path),
        "paired_seed_base": seed,
        "fault_assignment": "balanced-and-seeded-before-model-calls",
        "maximum_repair_episodes_per_arm": ADAPTIVE_REPAIR_EPISODES,
        "resumed_completed_trials": resumed_trials,
        "promotion_authority": "deterministic-visible-and-locked-gates",
        "analysis": analysis,
        "verdict": analysis["verdict"],
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def adaptive_microscopy_debug_conditions(*, smoke: bool = False) -> tuple[DebugCondition, ...]:
    start_positions = (800.0,) if smoke else (400.0, 800.0, 1200.0, 1600.0, 1800.0)
    conditions = tuple(
        DebugCondition(
            condition_id=f"visible-start-z-{int(start_z)}",
            scenario=SimulationScenario.REPAIR,
            parameters=(("start_z", start_z),),
            repetitions=1,
        )
        for start_z in start_positions
    )
    if smoke:
        return conditions
    return (
        *conditions,
        DebugCondition(
            condition_id="visible-measurement-uncertainty",
            scenario=SimulationScenario.REPAIR,
            parameters=(("start_z", 800.0), ("measurement_noise_level", 4.0)),
            repetitions=3,
        ),
    )


def _openrouter_client() -> DSV4Client:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for live adaptive skill search")
    return DSV4Client(
        base_url=OPENROUTER_BASE_URL,
        api_key=api_key,
        model="deepseek/deepseek-v4-flash",
        provider="GMICloud",
        reasoning_effort="high",
        include_reasoning=True,
    )


def run_live_adaptive_microscopy_search(
    output_dir: Path,
    *,
    base_url: str,
    seed_base: int,
    smoke: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight_dir = output_dir / "preflight"
    preflight_summary = run_live_adaptive_microscopy_preflight(
        preflight_dir,
        base_url=base_url,
    )
    if preflight_summary["verdict"] != "PASS":
        raise RuntimeError("fixture preflight failed before model invocation")
    preflight = FixturePreflightReport.model_validate_json(
        (preflight_dir / "preflight.json").read_text(encoding="utf-8")
    )
    conditions = adaptive_microscopy_debug_conditions(smoke=smoke)

    def evaluator(instrument_id: str, source: str, **kwargs: Any):
        return evaluate_live_adaptive_microscopy(
            instrument_id,
            source,
            base_url=base_url,
            **kwargs,
        )

    def agent(seed: int) -> AdaptiveInstrumentAgent:
        return AdaptiveInstrumentAgent(
            client=_openrouter_client(),
            source_loader=load_adaptive_microscopy_source,
            evaluator=evaluator,
            families={INSTRUMENT_ID: FAMILY},
            sampling_temperature=0.7,
            sampling_top_p=0.95,
            sampling_seed=seed,
        )

    draft_dir = output_dir / "drafts"
    repair_dir = output_dir / "repairs"
    draft_dir.mkdir(parents=True, exist_ok=True)
    repair_dir.mkdir(parents=True, exist_ok=True)

    def draft(seed: int) -> CandidatePackage:
        candidate = agent(seed).draft(INSTRUMENT_ID, max_turns=6)
        write_canonical_json(draft_dir / f"seed-{seed}.json", candidate)
        return candidate

    def repair(parent, suite, seed: int) -> RepairOutcome:
        outcome = agent(seed).repair_for_search(
            parent,
            suite,
            seed,
            conditions=conditions,
            max_turns=12,
        )
        write_canonical_json(repair_dir / f"seed-{seed}.json", outcome)
        return outcome

    health_client = _openrouter_client()
    try:
        health = health_client.health()
    finally:
        health_client.close()
    write_canonical_json(output_dir / "model-health.json", health)
    report = run_archive_search(
        INSTRUMENT_ID,
        conditions=conditions,
        evaluator=evaluator,
        draft=draft,
        repair=repair,
        preflight=preflight,
        seed_base=seed_base,
        initial_width=1 if smoke else 4,
        survivor_count=1 if smoke else 2,
        repair_rounds=0 if smoke else ADAPTIVE_REPAIR_EPISODES,
    )
    write_canonical_json(output_dir / "search.json", report)
    responses = [
        response
        for entry in report.entries
        for response in entry.candidate.raw_response.get("responses", [])
    ]
    summary = {
        "schema_version": "proprio.adaptive_microscopy_search_summary.v0.2",
        "instrument_id": INSTRUMENT_ID,
        "mode": "smoke" if smoke else "method-development",
        "preflight": preflight.verdict,
        "visible_conditions": len(conditions),
        "model_candidates_generated": report.model_candidates_generated,
        "selected": report.selected is not None,
        "search_verdict": report.verdict,
        "reasoning_preserved": bool(responses)
        and all(
            any(
                key in response.get("preserved_assistant_message", {})
                for key in ("reasoning", "reasoning_details", "reasoning_content")
            )
            for response in responses
        ),
        "verdict": "PASS" if report.verdict == "CANDIDATE" else "FAIL",
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
