from pathlib import Path

from proprio.independent_review import summarize_independent_study
from proprio.microscopy_evolution import (
    replay_microscopy_evolution,
    summarize_microscopy_evolution,
)
from proprio.replication_study import summarize_replication_study
from proprio.schema import canonical_json

ROOT = Path(__file__).resolve().parents[1]
CASSETTES = ROOT / "cassettes" / "replication-dsv4"
MICROSCOPY_EVOLUTION = ROOT / "cassettes" / "microscopy-evolution"
INDEPENDENT_REVIEW = ROOT / "cassettes" / "independent-review"


def test_expanded_replication_preserves_the_failed_external_family_gate() -> None:
    summary = summarize_replication_study(CASSETTES)
    assert canonical_json(summary) + b"\n" == (CASSETTES / "summary.json").read_bytes()
    assert summary["replicate_count"] == 70
    assert summary["overall"]["initial_executable"] == 68
    assert summary["overall"]["qualified"] == 64
    for instrument_id, row in summary["per_instrument"].items():
        if instrument_id == "microscope-autofocus":
            assert row["qualified"] == 4
            assert row["outcomes"] == {
                "locked_validation_failed": 2,
                "qualified": 4,
                "terminal_status_max_turns": 4,
            }
        else:
            assert row["qualified"] == 10
    assert summary["claim_gates"] == {
        "complete_capture": "PASS",
        "initial_executable_floor": "PASS",
        "qualification_floor": "FAIL",
        "unsafe_promotion_prevention": "PASS",
        "frozen_model_route": "PASS",
    }
    assert summary["verdict"] == "FAIL"


def test_external_microscopy_evolution_replays_as_rejected(tmp_path: Path) -> None:
    summary = summarize_microscopy_evolution(MICROSCOPY_EVOLUTION)
    assert canonical_json(summary) + b"\n" == (MICROSCOPY_EVOLUTION / "summary.json").read_bytes()
    assert summary["drift_detected"] is True
    assert summary["feedback_inspected_before_repair"] is True
    assert summary["repair_evidence_grounded"] is True
    assert summary["repair_status"] == "MAX_TURNS"
    assert summary["changed_condition_passed"] is False
    assert summary["historical_replay_complete"] is False
    assert summary["locked_validation_verdict"] == "FAIL"
    assert summary["independent_reviewer_verdict"] == "REJECT"
    assert summary["status"] == "REJECTED"
    assert summary["parent_immutable"] is True
    assert summary["verdict"] == "FAIL"

    replay = replay_microscopy_evolution(MICROSCOPY_EVOLUTION, tmp_path)
    assert replay == {
        "schema_version": "proprio.microscopy_evolution_replay.v0.1",
        "canonical_record_identical": True,
        "captured_summary_verdict": "FAIL",
        "verdict": "FAIL",
    }


def test_independent_review_preserves_external_fixture_failures() -> None:
    summary = summarize_independent_study(INDEPENDENT_REVIEW)
    assert canonical_json(summary) + b"\n" == (INDEPENDENT_REVIEW / "summary.json").read_bytes()
    assert summary["calibration"]["case_count"] == 56
    assert summary["calibration"]["verdict"] == "PASS"

    confirmatory = summary["confirmatory"]
    assert confirmatory["case_count"] == 49
    assert confirmatory["critical_defect_recall"] == 1.0
    assert confirmatory["valid_case_false_alarm_rate"] == 1 / 7
    assert confirmatory["unavailable_evidence_accuracy"] == 6 / 7
    assert confirmatory["hard_failure_overrides"] == 0
    assert confirmatory["claim_gates"] == {
        "complete_case_capture": "PASS",
        "critical_defect_recall": "PASS",
        "valid_case_false_alarm": "FAIL",
        "unavailable_evidence_honesty": "FAIL",
        "hard_gate_dominance": "PASS",
        "frozen_model_route": "PASS",
    }
    assert confirmatory["verdict"] == "FAIL"

    correlation = summary["correlation_with_dsv4"]
    assert correlation["shared_cases"] == 24
    assert correlation["exact_agreement_rate"] == 1.0
    assert correlation["cohen_kappa"] == 1.0
    assert summary["deterministic_gate_authority"] is True
    assert summary["verdict"] == "FAIL"
