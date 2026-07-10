from pathlib import Path

from proprio.artifacts import write_canonical_json
from proprio.confirmatory_instruments import CONFIRMATORY_INSTRUMENTS
from proprio.confirmatory_qualification import (
    evaluate_confirmatory_skill,
    load_confirmatory_source,
)
from proprio.confirmatory_skills import (
    render_confirmatory_nominal,
    render_confirmatory_repair,
)
from proprio.confirmatory_study import replay_confirmatory_study, summarize_confirmatory_study
from proprio.confirmatory_validation import (
    evaluate_confirmatory_validation,
    seal_confirmatory_candidate,
)
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    RepairEpisode,
    RepairSubmission,
    SimulationScenario,
)

MODEL = "deepseek/deepseek-v4-flash"
RESOLVED = "deepseek/deepseek-v4-flash-20260423"
PROVIDER = "GMICloud"


def _response() -> dict:
    return {
        "model": RESOLVED,
        "provider": PROVIDER,
        "preserved_assistant_message": {"reasoning": "fixture"},
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "completion_tokens_details": {"reasoning_tokens": 3},
            "total_tokens": 15,
            "cost": 0.001,
        },
    }


def _candidate(instrument_id: str, source: str) -> CandidatePackage:
    _, source_hash = load_confirmatory_source(instrument_id)
    return CandidatePackage(
        instrument_id=instrument_id,
        skill_md=f"---\nname: {instrument_id}\ndescription: fixture\n---\n",
        skill_py=source,
        self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model=MODEL,
        raw_response={"responses": [_response()]},
    )


def _episode(
    initial: CandidatePackage,
    final: CandidatePackage,
    arm: FeedbackArm,
) -> RepairEpisode:
    initial_gate = evaluate_confirmatory_skill(
        initial.instrument_id,
        initial.skill_py,
        scenario=SimulationScenario.REPAIR,
    )
    final_gate = evaluate_confirmatory_skill(
        initial.instrument_id,
        final.skill_py,
        scenario=SimulationScenario.REPAIR,
    )
    failed = next(check.check_id for check in initial_gate.checks if not check.passed)
    submission = RepairSubmission(
        diagnosis="support changed",
        evidence_refs=(failed,),
        skill_md=final.skill_md,
        skill_py=final.skill_py,
        expected_effect="restore postconditions",
        risks=("hardware remains unqualified",),
        self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
    )
    return RepairEpisode(
        instrument_id=initial.instrument_id,
        family=CONFIRMATORY_INSTRUMENTS[initial.instrument_id].family,
        feedback_arm=arm,
        scenario=SimulationScenario.REPAIR,
        initial_candidate=initial,
        final_candidate=final,
        initial_gate=initial_gate,
        final_gate=final_gate,
        submissions=(submission,) if arm is FeedbackArm.TRUTHFUL else (),
        tool_events=(
            {
                "name": "run_simulator",
                "result": {
                    "evidence_ref": "gate:fixture:repair",
                    "checks": [check.model_dump(mode="json") for check in initial_gate.checks],
                },
            },
            {
                "name": "submit_repair",
                "arguments": {"evidence_refs": [failed]},
                "result": {"status": "captured"},
            },
            {
                "name": "run_simulator",
                "result": {"evidence_ref": "gate:repaired:repair", "checks": []},
            },
        )
        if arm is FeedbackArm.TRUTHFUL
        else (),
        raw_responses=(_response(),),
        agent_status="CANDIDATE" if arm is FeedbackArm.TRUTHFUL else "HOLD",
        agent_summary="fixture",
    )


def test_complete_confirmatory_fixture_passes_claim_gates(tmp_path: Path) -> None:
    write_canonical_json(
        tmp_path / "health.json",
        {"requested_model": MODEL, "provider": PROVIDER},
    )
    for instrument_id in sorted(CONFIRMATORY_INSTRUMENTS):
        initial = _candidate(instrument_id, render_confirmatory_nominal(instrument_id))
        repaired = _candidate(instrument_id, render_confirmatory_repair(instrument_id))
        write_canonical_json(tmp_path / instrument_id / "candidate.json", initial)
        for arm, final in (
            (FeedbackArm.TRUTHFUL, repaired),
            (FeedbackArm.NONE, initial),
        ):
            episode = _episode(initial, final, arm)
            write_canonical_json(
                tmp_path / instrument_id / f"repair-{arm.value}.json",
                episode,
            )
            validation = evaluate_confirmatory_validation(
                final,
                seal_confirmatory_candidate(final),
            )
            write_canonical_json(
                tmp_path / instrument_id / f"locked-validation-{arm.value}.json",
                validation,
            )

    summary = summarize_confirmatory_study(tmp_path)
    assert summary["verdict"] == "PASS"
    assert summary["initial_executable_rate"] == 1.0
    assert summary["arms"]["truthful"]["qualification_rate"] == 1.0
    assert summary["arms"]["truthful"]["admission_qualification_rate"] == 1.0
    assert summary["arms"]["none"]["qualification_rate"] == 0.0
    assert summary["arms"]["none"]["admission_qualification_rate"] == 0.0
    assert summary["causal_uplift_over_none"] == 1.0
    assert summary["unsafe_promotions"] == 0

    replay = replay_confirmatory_study(tmp_path, tmp_path / "replay")
    assert replay["verdict"] == "PASS"
    assert replay["episodes"] == 12
    assert replay["byte_identical"] == 12
    assert replay["reset_idempotent"] == 12
