from pathlib import Path

from proprio.artifacts import write_canonical_json
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_sources import load_instrument_source
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    RepairEpisode,
    RepairSubmission,
    SimulationScenario,
)
from proprio.model_ablation import summarize_model_ablation
from proprio.reference_instruments import INSTRUMENTS
from proprio.reference_skills import render_nominal, render_repair_parent

MODEL = "fixture/model"
PROVIDER = "FixtureProvider"


def _candidate(instrument_id: str, source: str, model: str) -> CandidatePackage:
    _, source_hash = load_instrument_source(instrument_id)
    return CandidatePackage(
        instrument_id=instrument_id,
        skill_md=f"""---
name: {instrument_id}
description: Execute a simulated scientific instrument procedure.
---
# Run
Execute and preserve cleanup.
""",
        skill_py=source,
        self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model=model,
        raw_response={},
    )


def _response() -> dict:
    return {
        "provider": PROVIDER,
        "model": "fixture/model-revision",
        "preserved_assistant_message": {"reasoning_details": [{"type": "reasoning.text"}]},
    }


def _episode(instrument_id: str, arm: FeedbackArm) -> RepairEpisode:
    initial = _candidate(instrument_id, render_nominal(instrument_id), "primary/model")
    repaired = arm is FeedbackArm.TRUTHFUL
    final_source = render_repair_parent(instrument_id) if repaired else initial.skill_py
    final = _candidate(instrument_id, final_source, MODEL if repaired else "primary/model")
    initial_gate = evaluate_instrument_skill(
        instrument_id,
        initial.skill_py,
        scenario=SimulationScenario.REPAIR,
    )
    final_gate = evaluate_instrument_skill(
        instrument_id,
        final.skill_py,
        scenario=SimulationScenario.REPAIR,
    )
    submissions = ()
    events = ()
    if repaired:
        failed_ref = next(check.check_id for check in initial_gate.checks if not check.passed)
        submission = RepairSubmission(
            diagnosis="fixture repair",
            evidence_refs=(failed_ref,),
            skill_md=final.skill_md,
            skill_py=final.skill_py,
            expected_effect="pass",
            risks=(),
            self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
        )
        submissions = (submission,)
        events = (
            {
                "name": "run_simulator",
                "result": {
                    "evidence_ref": "gate:fixture:repair",
                    "checks": [check.model_dump(mode="json") for check in initial_gate.checks],
                },
            },
            {
                "name": "submit_repair",
                "arguments": submission.model_dump(mode="json"),
                "result": {"status": "captured"},
            },
            {
                "name": "run_simulator",
                "result": {
                    "evidence_ref": "gate:repaired:repair",
                    "checks": [check.model_dump(mode="json") for check in final_gate.checks],
                },
            },
        )
    return RepairEpisode(
        instrument_id=instrument_id,
        family=INSTRUMENTS[instrument_id].family,
        feedback_arm=arm,
        scenario=SimulationScenario.REPAIR,
        initial_candidate=initial,
        final_candidate=final,
        initial_gate=initial_gate,
        final_gate=final_gate,
        submissions=submissions,
        tool_events=events,
        raw_responses=(_response(), _response()),
        agent_status="CANDIDATE" if repaired else "HOLD",
        agent_summary="fixture",
    )


def test_shared_failure_ablation_reports_causal_separation(tmp_path: Path) -> None:
    for instrument_id in sorted(INSTRUMENTS):
        initial = _candidate(instrument_id, render_nominal(instrument_id), "primary/model")
        write_canonical_json(tmp_path / instrument_id / "candidate.json", initial)
        for arm in (FeedbackArm.TRUTHFUL, FeedbackArm.NONE):
            write_canonical_json(
                tmp_path / instrument_id / f"repair-{arm.value}.json",
                _episode(instrument_id, arm),
            )

    summary = summarize_model_ablation(
        tmp_path,
        target_model=MODEL,
        target_provider=PROVIDER,
        study="shared_failure_repair",
        prompt_condition="original",
    )
    assert summary["verdict"] == "PASS"
    assert summary["arms"]["truthful"]["repair_rate"] == 1.0
    assert summary["arms"]["none"]["repair_rate"] == 0.0
    assert summary["arms"]["truthful"]["qualified"] == 8
    assert summary["arms"]["truthful"]["qualification_rate"] == 1.0
    assert summary["arms"]["truthful"]["clean_qualification_rate"] == 1.0
    assert summary["causal_uplift_over_none"] == 1.0
    assert summary["transport_evidence"]["reasoning_state_missing"] == 0
