from pathlib import Path

from proprio.artifacts import write_canonical_json
from proprio.independent_review import (
    build_independent_case,
    build_microscopy_case,
    reviewer_correlation,
)
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_types import (
    HardGateResult,
    JudgeEpisode,
    JudgeReview,
    RepairEpisode,
    SimulationScenario,
)
from proprio.reference_instruments import INSTRUMENTS


def _judge(verdict: str) -> JudgeEpisode:
    return JudgeEpisode(
        instrument_id="constant-current-cycle",
        review=JudgeReview(
            verdict=verdict,
            critical_findings=(),
            evidence_refs=("fixture",),
            summary="fixture",
        ),
        tool_events=(),
        raw_responses=(),
        status="completed",
    )


def test_independent_review_mutations_are_semantically_distinct() -> None:
    unsupported = build_independent_case("constant-current-cycle", "unsupported-diagnosis")
    omitted = build_independent_case("constant-current-cycle", "omitted-evidence")
    overclaim = build_independent_case("constant-current-cycle", "real-hardware-overclaim")
    unsupported_episode = RepairEpisode.model_validate(unsupported["episode"])
    omitted_episode = RepairEpisode.model_validate(omitted["episode"])
    overclaim_episode = RepairEpisode.model_validate(overclaim["episode"])
    assert "wavelength-calibration" in unsupported_episode.submissions[-1].diagnosis
    assert omitted_episode.submissions[-1].evidence_refs == ()
    assert "real-hardware" in overclaim_episode.submissions[-1].expected_effect
    assert {unsupported["expected_verdicts"][0], omitted["expected_verdicts"][0]} == {"REJECT"}


def test_unavailable_calibration_isolates_unavailability_from_skill_defects() -> None:
    for instrument_id in sorted(INSTRUMENTS):
        case = build_independent_case(instrument_id, "unavailable-evidence")
        episode = RepairEpisode.model_validate(case["episode"])
        nominal = evaluate_instrument_skill(
            instrument_id,
            episode.final_candidate.skill_py,
            scenario=SimulationScenario.NOMINAL,
        )
        assert nominal.verdict == "ADMIT"
        assert episode.initial_candidate.skill_py == episode.final_candidate.skill_py
        assert episode.submissions == ()
        assert episode.final_gate.verdict == "HOLD"


def test_microscopy_unavailable_fixture_keeps_the_skill_unchanged(monkeypatch) -> None:
    def unavailable_gate(instrument_id, source, *, scenario, **kwargs):
        del source, kwargs
        return HardGateResult(
            instrument_id=instrument_id,
            family="optical_microscopy",
            scenario=scenario,
            verdict="HOLD",
            status="unavailable",
            checks=(),
            trace=(),
            telemetry={},
            result=None,
            runtime_error="simulator unavailable",
            skill_sha256="0" * 64,
            simulator_sha256="1" * 64,
            verifier_sha256="2" * 64,
        )

    monkeypatch.setattr(
        "proprio.independent_review.evaluate_live_microscopy_skill",
        unavailable_gate,
    )
    case = build_microscopy_case(
        "unavailable-evidence",
        base_url="http://unavailable.invalid",
    )
    episode = RepairEpisode.model_validate(case["episode"])
    assert episode.initial_candidate.skill_py == episode.final_candidate.skill_py
    assert episode.submissions == ()
    assert episode.initial_gate.verdict == "HOLD"
    assert episode.final_gate.verdict == "HOLD"


def test_reviewer_correlation_uses_only_shared_case_ids(tmp_path: Path) -> None:
    independent = tmp_path / "independent"
    dsv4 = tmp_path / "dsv4"
    case = {
        "case_id": "constant-current-cycle--valid-repair",
        "category": "valid-repair",
        "judge": _judge("ACCEPT").model_dump(mode="json"),
    }
    write_canonical_json(independent / "cases" / "shared.json", case)
    write_canonical_json(dsv4 / "cases" / "shared.json", case)
    write_canonical_json(
        independent / "cases" / "not-shared.json",
        {**case, "case_id": "other--valid-repair"},
    )
    result = reviewer_correlation(independent, dsv4)
    assert result["shared_cases"] == 1
    assert result["exact_agreement_rate"] == 1.0
    assert result["cohen_kappa"] == 1.0
