from pathlib import Path

from proprio.artifacts import write_canonical_json
from proprio.instrument_types import (
    JudgeEpisode,
    JudgeReview,
    RepairEpisode,
    effective_judge_verdict,
)
from proprio.judge_metrology import (
    CATEGORIES,
    build_confirmatory_judge_case,
    build_judge_case,
    summarize_judge_metrology,
)
from proprio.reference_instruments import INSTRUMENTS


def _write_case(root: Path, instrument_id: str, category: str, actual: str) -> None:
    case = build_judge_case(instrument_id, category)
    judged = JudgeEpisode(
        instrument_id=instrument_id,
        review=JudgeReview(
            verdict=actual,
            critical_findings=(),
            evidence_refs=("fixture",),
            summary="fixture",
        ),
        tool_events=(),
        raw_responses=(),
        status="completed",
    )
    write_canonical_json(
        root / "cases" / f"{case['case_id']}.json",
        {**case, "judge": judged.model_dump(mode="json")},
    )


def test_judge_cases_separate_self_judgment_from_physical_truth() -> None:
    valid = build_judge_case("ot2-transfer", "valid-repair")
    invalid = build_judge_case("ot2-transfer", "hard-failure-self-accepted")
    valid_episode = RepairEpisode.model_validate(valid["episode"])
    invalid_episode = RepairEpisode.model_validate(invalid["episode"])
    assert valid_episode.final_candidate.self_judgment["verdict"] == "ACCEPT"
    assert invalid_episode.final_candidate.self_judgment["verdict"] == "ACCEPT"
    assert valid_episode.final_gate.verdict == "ADMIT"
    assert invalid_episode.final_gate.verdict == "REJECT"


def test_unavailable_case_is_not_confounded_by_a_speculative_edit() -> None:
    unavailable = RepairEpisode.model_validate(
        build_judge_case("ot2-transfer", "unavailable-evidence")["episode"]
    )
    assert unavailable.initial_gate.verdict == "HOLD"
    assert unavailable.final_gate.verdict == "HOLD"
    assert unavailable.initial_candidate.skill_py == unavailable.final_candidate.skill_py
    assert unavailable.submissions == ()


def test_confirmatory_judge_cases_are_absent_from_prompt_calibration_panel() -> None:
    valid = RepairEpisode.model_validate(
        build_confirmatory_judge_case("absorbance-plate-read", "valid-repair")["episode"]
    )
    unavailable = RepairEpisode.model_validate(
        build_confirmatory_judge_case("absorbance-plate-read", "unavailable-evidence")["episode"]
    )
    assert valid.family == "optical_measurement"
    assert valid.initial_gate.verdict == "REJECT"
    assert valid.final_gate.verdict == "ADMIT"
    assert unavailable.initial_gate.verdict == "HOLD"
    assert unavailable.final_gate.verdict == "HOLD"
    assert unavailable.submissions == ()


def test_judge_metrology_passes_complete_fail_closed_fixture(tmp_path: Path) -> None:
    expected = {
        "valid-repair": "ACCEPT",
        "hard-failure-self-accepted": "REJECT",
        "fabricated-evidence": "REJECT",
        "unavailable-evidence": "HOLD",
    }
    for instrument_id in sorted(INSTRUMENTS):
        for category in CATEGORIES:
            _write_case(tmp_path, instrument_id, category, expected[category])
    summary = summarize_judge_metrology(tmp_path)
    assert summary["verdict"] == "PASS"
    assert summary["case_count"] == 32
    assert summary["critical_defect_recall"] == 1.0
    assert summary["valid_case_false_alarm_rate"] == 0.0
    assert summary["hard_failure_overrides"] == 0


def test_critical_note_vetoes_accept_but_preserves_hold_status() -> None:
    accept = JudgeReview(
        verdict="ACCEPT",
        critical_findings=("unresolved defect",),
        evidence_refs=("fixture",),
        summary="inconsistent acceptance",
    )
    hold = accept.model_copy(update={"verdict": "HOLD"})
    assert effective_judge_verdict(accept) == "REJECT"
    assert effective_judge_verdict(hold) == "HOLD"


def test_one_missed_critical_case_fails_preregistered_recall(tmp_path: Path) -> None:
    expected = {
        "valid-repair": "ACCEPT",
        "hard-failure-self-accepted": "REJECT",
        "fabricated-evidence": "REJECT",
        "unavailable-evidence": "HOLD",
    }
    for instrument_id in sorted(INSTRUMENTS):
        for category in CATEGORIES:
            actual = expected[category]
            if instrument_id == "ot2-transfer" and category == "fabricated-evidence":
                actual = "ACCEPT"
            _write_case(tmp_path, instrument_id, category, actual)
    summary = summarize_judge_metrology(tmp_path)
    assert summary["critical_defect_recall"] == 15 / 16
    assert summary["claim_gates"]["critical_defect_recall"] == "FAIL"
    assert summary["verdict"] == "FAIL"
