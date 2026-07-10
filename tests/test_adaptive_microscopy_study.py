import hashlib
import json
from pathlib import Path

import pytest

import proprio.adaptive_microscopy_study as study
from proprio.adaptive_microscopy import ALLOWED_METHODS
from proprio.adaptive_microscopy_study import (
    ADAPTIVE_REPAIR_EPISODES,
    CAUSAL_EXPECTED_REPAIR,
    GOOD_FIXTURE,
    INVALID_FIXTURE,
    CausalFault,
    adaptive_microscopy_causal_conditions,
    adaptive_microscopy_debug_conditions,
    adaptive_microscopy_preflight_cases,
    lock_causal_development_panel,
    run_live_adaptive_microscopy_curve_metrology,
    run_live_adaptive_microscopy_reset_battery,
    run_live_adaptive_microscopy_uncertainty_battery,
    summarize_causal_trials,
)
from proprio.instrument_qualification import compile_instrument_skill
from proprio.instrument_types import GateCheck, HardGateResult, SimulationScenario


def test_adaptive_microscopy_preflight_is_complete_before_model_use() -> None:
    cases = adaptive_microscopy_preflight_cases()
    assert {case.expected_verdict for case in cases} == {"ADMIT", "REJECT", "HOLD"}
    assert len({case.case_id for case in cases}) == 3
    assert next(case for case in cases if case.expected_verdict == "REJECT").required_failed_checks


def test_preflight_skills_compile_under_the_frozen_adaptive_executor() -> None:
    compile_instrument_skill(GOOD_FIXTURE, ALLOWED_METHODS)
    compile_instrument_skill(INVALID_FIXTURE, ALLOWED_METHODS)


def test_debug_distribution_covers_nominal_boundary_and_shifted_starts() -> None:
    conditions = adaptive_microscopy_debug_conditions()
    assert [condition.parameter_map()["start_z"] for condition in conditions[:-1]] == [
        400.0,
        800.0,
        1200.0,
        1600.0,
        1800.0,
    ]
    assert conditions[-1].condition_id == "visible-measurement-uncertainty"
    assert conditions[-1].parameter_map() == {
        "start_z": 800.0,
        "measurement_noise_level": 4.0,
    }
    assert all(condition.repetitions == 1 for condition in conditions[:-1])
    assert conditions[-1].repetitions == 3


def test_causal_conditions_are_balanced_across_three_competing_repairs() -> None:
    uncertainty = adaptive_microscopy_causal_conditions(
        CausalFault.TEMPORAL_PRECISION, trial_index=0, locked=False
    )[-1]
    coverage = adaptive_microscopy_causal_conditions(
        CausalFault.SWEEP_COVERAGE, trial_index=0, locked=False
    )[-1]
    readback = adaptive_microscopy_causal_conditions(
        CausalFault.STAGE_READBACK, trial_index=1, locked=False
    )[-1]
    assert uncertainty.parameter_map()["measurement_noise_level"] == 4.0
    assert coverage.parameter_map()["start_z"] == 3500.0
    assert readback.parameter_map()["stage_bias_steps"] == -300.0
    assert set(CAUSAL_EXPECTED_REPAIR.values()) == {
        "repeat-evidence",
        "sweep-coverage",
        "stage-correction",
    }


def test_causal_protocol_allows_four_evidence_conditioned_repairs() -> None:
    preregistration = (
        Path("src/proprio/data/adaptive-method-preregistration.yaml")
        .read_text(encoding="utf-8")
    )
    assert ADAPTIVE_REPAIR_EPISODES == 4
    assert "repair_rounds: 4" in preregistration
    assert "repair_rounds_per_arm: 4" in preregistration


def test_repair_signature_recognizes_composite_coverage_recovery() -> None:
    parent = """def run(controller):
    controller.fast_autofocus(4000)
    controller.capture_focus_series(3)
"""
    coverage_recovery = """def run(controller):
    first = controller.fast_autofocus(4000)
    controller.move_z(0 - first["position_z"])
    controller.fast_autofocus(2000)
    controller.capture_focus_series(3)
"""
    assert study._repair_signature(parent, coverage_recovery) == "sweep-coverage"


def test_changed_candidate_forces_fresh_suite_before_next_episode() -> None:
    old = study.fixture_candidate(GOOD_FIXTURE)
    changed = study.fixture_candidate(GOOD_FIXTURE.replace("2000", "2400", 1))
    conditions = (
        study.DebugCondition(
            condition_id="fixture",
            scenario=SimulationScenario.REPAIR,
        ),
    )
    calls = 0

    def evaluator(instrument_id, source, *, scenario, condition):
        nonlocal calls
        del condition
        calls += 1
        return HardGateResult(
            instrument_id=instrument_id,
            family="fixture",
            scenario=scenario,
            verdict="ADMIT",
            status="succeeded",
            checks=(GateCheck(check_id="fixture", passed=True),),
            trace=(),
            telemetry={},
            result={},
            runtime_error=None,
            skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
            simulator_sha256="1" * 64,
            verifier_sha256="2" * 64,
        )

    old_suite = study.evaluate_debug_suite(old, conditions, evaluator=evaluator)
    calls_for_one_suite = calls
    refreshed, replayed = study._refresh_suite_if_stale(
        changed,
        old_suite,
        conditions,
        evaluator=evaluator,
    )
    assert replayed
    assert calls == 2 * calls_for_one_suite
    assert refreshed.candidate_sha256 == hashlib.sha256(changed.skill_py.encode()).hexdigest()


def test_completed_causal_trial_resumes_only_with_complete_matching_artifacts(
    tmp_path: Path,
) -> None:
    trial_dir = tmp_path / "trial-000"
    trial_dir.mkdir()
    outcomes = {}
    for arm in ("truthful", "generic", "mismatched", "none"):
        outcomes[arm] = {
            "qualified": arm == "truthful",
            "rounds_used": 1,
            "repair_signature": "repeat-evidence" if arm == "truthful" else "other",
        }
        (trial_dir / f"repair-{arm}-round-1.json").write_text("{}\n", encoding="utf-8")
        (trial_dir / f"locked-{arm}.json").write_text("{}\n", encoding="utf-8")
    row = {
        "schema_version": "proprio.causal_repair_trial.v0.2",
        "trial_index": 0,
        "model_seed": 990000,
        "fault": CausalFault.TEMPORAL_PRECISION.value,
        "maximum_repair_episodes_per_arm": ADAPTIVE_REPAIR_EPISODES,
        "outcomes": outcomes,
    }
    (trial_dir / "summary.json").write_text(json.dumps(row), encoding="utf-8")
    loaded = study._load_completed_causal_trial(
        trial_dir,
        trial_index=0,
        fault=CausalFault.TEMPORAL_PRECISION,
        model_seed=990000,
    )
    assert loaded == row

    (trial_dir / "locked-none.json").unlink()
    with pytest.raises(RuntimeError, match="omitted locked replay"):
        study._load_completed_causal_trial(
            trial_dir,
            trial_index=0,
            fault=CausalFault.TEMPORAL_PRECISION,
            model_seed=990000,
        )


def test_causal_summary_requires_repeated_paired_uplift_and_mechanism_match() -> None:
    rows = []
    faults = list(CausalFault)
    for index in range(30):
        fault = faults[index % len(faults)]
        outcomes = {
            arm: {
                "qualified": arm == "truthful",
                "repair_signature": (
                    CAUSAL_EXPECTED_REPAIR[fault] if arm == "truthful" else "other"
                ),
            }
            for arm in ("truthful", "generic", "mismatched", "none")
        }
        rows.append({"fault": fault.value, "outcomes": outcomes})
    summary = summarize_causal_trials(rows, required_trials=30)
    assert summary["verdict"] == "PASS"
    assert summary["truthful_minus_none"] == 1.0
    assert summary["mcnemar"]["one_sided_exact_p"] < 0.05
    assert summary["truthful_trace_to_edit_concordance"] == 1.0

    for row in rows:
        row["outcomes"]["none"]["qualified"] = True
    confounded = summarize_causal_trials(rows, required_trials=30)
    assert confounded["verdict"] == "FAIL"
    assert confounded["truthful_minus_none"] == 0.0


def test_causal_development_lock_preserves_incomplete_claim(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt"
    faults = [fault.value for fault in CausalFault] * 10
    manifest = {
        "schema_version": "proprio.causal_run_manifest.v0.2",
        "paired_seed_base": 990000,
        "trials": 30,
        "fault_assignment": faults,
    }
    attempt.mkdir()
    (attempt / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for trial_index in range(4):
        trial_dir = attempt / "trials" / f"trial-{trial_index:03d}"
        trial_dir.mkdir(parents=True)
        fault = CausalFault(faults[trial_index])
        outcomes = {}
        for arm in ("truthful", "generic", "mismatched", "none"):
            outcomes[arm] = {
                "qualified": arm == "truthful" and trial_index != 1,
                "rounds_used": 1,
                "repair_signature": (
                    CAUSAL_EXPECTED_REPAIR[fault] if arm == "truthful" else "other"
                ),
            }
            (trial_dir / f"repair-{arm}-round-1.json").write_text("{}\n", encoding="utf-8")
            (trial_dir / f"locked-{arm}.json").write_text("{}\n", encoding="utf-8")
        row = {
            "schema_version": "proprio.causal_repair_trial.v0.2",
            "trial_index": trial_index,
            "model_seed": 990000 + trial_index,
            "fault": fault.value,
            "maximum_repair_episodes_per_arm": ADAPTIVE_REPAIR_EPISODES,
            "outcomes": outcomes,
        }
        (trial_dir / "summary.json").write_text(json.dumps(row), encoding="utf-8")
    (attempt / "trials" / "trial-004").mkdir()

    locked = lock_causal_development_panel(attempt, tmp_path / "locked")
    assert locked["status"] == "EXPLORATORY_LOCKED"
    assert locked["confirmatory_status"] == "NOT_ESTABLISHED"
    assert locked["analysis"]["verdict"] == "INCOMPLETE"
    assert locked["analysis"]["arm_qualification_rates"]["truthful"] == 0.75
    assert locked["excluded_partial_trial_indices"] == [4]


def test_uncertainty_battery_reports_failure_classes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def evaluator(instrument_id, source, *, scenario, condition, base_url):
        del base_url
        repeats = 5 if "capture_focus_series(5)" in source else 3
        passed = condition["measurement_noise_level"] == 2.0 or repeats == 5
        check = GateCheck(
            check_id="temporal-measurement-uncertainty",
            passed=passed,
            evidence={"repeats": repeats},
        )
        return HardGateResult(
            instrument_id=instrument_id,
            family="fixture",
            scenario=scenario,
            verdict="ADMIT" if passed else "REJECT",
            status="succeeded" if passed else "failed",
            checks=(check,),
            trace=(),
            telemetry={},
            result={},
            runtime_error=None,
            skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
            simulator_sha256="1" * 64,
            verifier_sha256="2" * 64,
        )

    monkeypatch.setattr(study, "evaluate_live_adaptive_microscopy", evaluator)
    summary = run_live_adaptive_microscopy_uncertainty_battery(
        tmp_path,
        base_urls=("sim://a", "sim://b"),
        cases_per_group=20,
    )
    assert summary["verdict"] == "PASS"
    assert summary["false_valid_count"] == 0
    assert summary["false_reject_count"] == 0
    assert summary["groups"]["invalid-three-repeats"]["observed_reject"] == 20
    assert summary["groups"]["repairable-ten-repeats"]["observed_admit"] == 20


def test_curve_metrology_reports_false_valid_and_false_reject(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def evaluator(instrument_id, source, *, scenario, condition, base_url):
        del condition, base_url
        passed = source == GOOD_FIXTURE
        check = GateCheck(check_id="autofocus-reference-covered", passed=passed)
        return HardGateResult(
            instrument_id=instrument_id,
            family="fixture",
            scenario=scenario,
            verdict="ADMIT" if passed else "REJECT",
            status="succeeded" if passed else "failed",
            checks=(check,),
            trace=(),
            telemetry={},
            result={},
            runtime_error=None,
            skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
            simulator_sha256="1" * 64,
            verifier_sha256="2" * 64,
        )

    monkeypatch.setattr(study, "evaluate_live_adaptive_microscopy", evaluator)
    summary = run_live_adaptive_microscopy_curve_metrology(
        tmp_path,
        base_urls=("sim://a", "sim://b"),
        cases_per_group=20,
    )
    assert summary["verdict"] == "PASS"
    assert summary["valid_admitted"] == 20
    assert summary["invalid_rejected"] == 20


def test_reset_battery_requires_every_repeated_transaction_to_admit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def evaluator(instrument_id, source, *, scenario, condition, base_url):
        del source, condition
        return HardGateResult(
            instrument_id=instrument_id,
            family="fixture",
            scenario=scenario,
            verdict="ADMIT",
            status="succeeded",
            checks=(GateCheck(check_id="runtime-completed", passed=True),),
            trace=(),
            telemetry={"base_url": base_url},
            result={},
            runtime_error=None,
            skill_sha256="1" * 64,
            simulator_sha256="2" * 64,
            verifier_sha256="3" * 64,
        )

    monkeypatch.setattr(study, "evaluate_live_adaptive_microscopy", evaluator)
    summary = run_live_adaptive_microscopy_reset_battery(
        tmp_path,
        base_urls=("sim://a", "sim://b"),
        cases_per_simulator=5,
    )
    assert summary == {
        "schema_version": "proprio.adaptive_reset_battery.v0.2",
        "instrument_id": "microscope-autofocus",
        "simulator_base_urls": ["sim://a", "sim://b"],
        "cases_per_simulator": 5,
        "cases": 10,
        "failures": 0,
        "verdict": "PASS",
    }
