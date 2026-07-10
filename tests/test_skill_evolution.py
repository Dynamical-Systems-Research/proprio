from pathlib import Path

import pytest

from proprio.artifacts import write_canonical_json
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_sources import load_instrument_source
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    JudgeEpisode,
    JudgeReview,
    RepairEpisode,
    RepairSubmission,
    SimulationScenario,
)
from proprio.locked_validation import evaluate_locked_validation, seal_candidate
from proprio.reference_instruments import INSTRUMENTS
from proprio.reference_skills import render_drift_candidate, render_repair_parent
from proprio.skill_evolution import (
    replay_evolution_study,
    stage_skill_evolution,
    summarize_evolution_study,
)


def _candidate(instrument_id: str, source: str) -> CandidatePackage:
    _, source_hash = load_instrument_source(instrument_id)
    skill_md = f"""---
name: {instrument_id}
description: Execute a source-grounded simulated instrument procedure.
---
# Run
Execute the declared procedure and preserve cleanup.
"""
    return CandidatePackage(
        instrument_id=instrument_id,
        skill_md=skill_md,
        skill_py=source,
        self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model="dsv4",
        raw_response={},
    )


def _repair(
    instrument_id: str,
    proposed_source: str,
    *,
    scenario: SimulationScenario = SimulationScenario.DRIFT,
) -> RepairEpisode:
    parent = _candidate(instrument_id, render_repair_parent(instrument_id))
    proposed = _candidate(instrument_id, proposed_source)
    initial_gate = evaluate_instrument_skill(
        instrument_id,
        parent.skill_py,
        scenario=scenario,
    )
    evidence_ref = next(
        (check.check_id for check in initial_gate.checks if not check.passed),
        "gate:unavailable",
    )
    submission = RepairSubmission(
        diagnosis="simulated operating support changed",
        evidence_refs=(evidence_ref,),
        skill_md=proposed.skill_md,
        skill_py=proposed.skill_py,
        expected_effect="restore physical postconditions",
        risks=("real hardware remains unqualified",),
        self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
    )
    return RepairEpisode(
        instrument_id=instrument_id,
        family=INSTRUMENTS[instrument_id].family,
        feedback_arm=FeedbackArm.TRUTHFUL,
        scenario=scenario,
        initial_candidate=parent,
        final_candidate=proposed,
        initial_gate=initial_gate,
        final_gate=evaluate_instrument_skill(
            instrument_id,
            proposed.skill_py,
            scenario=scenario,
        ),
        submissions=(submission,),
        tool_events=(
            {
                "name": "run_simulator",
                "result": {
                    "evidence_ref": "gate:initial:drift",
                    "checks": [check.model_dump(mode="json") for check in initial_gate.checks],
                },
            },
            {
                "name": "submit_repair",
                "arguments": {"evidence_refs": [evidence_ref]},
                "result": {"status": "captured"},
            },
            {
                "name": "run_simulator",
                "result": {"evidence_ref": "gate:replayed:drift", "checks": []},
            },
        ),
        raw_responses=(),
        agent_status="CANDIDATE",
        agent_summary="fixture",
    )


def _judge(instrument_id: str, verdict: str = "ACCEPT") -> JudgeEpisode:
    review = JudgeReview(
        verdict=verdict,
        critical_findings=(),
        evidence_refs=("replay",),
        summary="fixture review",
    )
    return JudgeEpisode(
        instrument_id=instrument_id,
        review=review,
        tool_events=(),
        raw_responses=(),
        status="completed",
    )


def _locked(candidate: CandidatePackage):
    return evaluate_locked_validation(candidate, seal_candidate(candidate))


@pytest.mark.parametrize("instrument_id", sorted(INSTRUMENTS))
def test_drift_proposal_stages_without_replacing_parent(instrument_id: str) -> None:
    repair = _repair(instrument_id, render_drift_candidate(instrument_id))
    parent = repair.initial_candidate
    proposal = stage_skill_evolution(
        parent,
        repair,
        _judge(instrument_id),
        _locked(repair.final_candidate),
    )

    assert proposal.drift_detection.verdict == "REJECT"
    assert all(gate.verdict == "ADMIT" for gate in proposal.qualification)
    assert proposal.status == "STAGED"
    assert proposal.lineage.parent_skill_sha256 != proposal.lineage.proposal_skill_sha256
    assert proposal.lineage.rollback_skill_sha256 == proposal.lineage.parent_skill_sha256
    assert proposal.lineage.hardware_gate_required is True
    assert proposal.parent_candidate.skill_py == parent.skill_py


def test_accepting_judge_cannot_stage_hard_failure() -> None:
    instrument_id = "ot2-transfer"
    repair = _repair(instrument_id, render_repair_parent(instrument_id))
    proposal = stage_skill_evolution(
        repair.initial_candidate,
        repair,
        _judge(instrument_id),
        _locked(repair.final_candidate),
    )
    assert proposal.hybrid_verdict.hard_verdict == "REJECT"
    assert proposal.status == "REJECTED"


def test_untraceable_repair_evidence_cannot_stage() -> None:
    instrument_id = "ot2-transfer"
    repair = _repair(instrument_id, render_drift_candidate(instrument_id))
    invalid = repair.model_copy(
        update={
            "tool_events": (
                repair.tool_events[0],
                {
                    **repair.tool_events[1],
                    "arguments": {"evidence_refs": ["fabricated:evidence"]},
                },
                repair.tool_events[2],
            )
        }
    )
    proposal = stage_skill_evolution(
        invalid.initial_candidate,
        invalid,
        _judge(instrument_id),
        _locked(invalid.final_candidate),
    )
    assert proposal.status == "REJECTED"
    assert proposal.hybrid_verdict.hard_verdict == "REJECT"
    assert "provenance" in proposal.reason


def test_locked_condition_failure_blocks_development_point_pass() -> None:
    instrument_id = "ot2-transfer"
    source = """def run(controller):
    controller.reset()
    controller.pick_up_tip()
    controller.aspirate(45.0)
    controller.dispense(45.0)
    controller.aspirate(45.0)
    controller.dispense(45.0)
    controller.aspirate(30.0)
    controller.dispense(30.0)
    controller.drop_tip()
    return {"transferred_ul": 120.0}
"""
    repair = _repair(instrument_id, source)
    assert repair.final_gate.verdict == "ADMIT"
    locked = _locked(repair.final_candidate)
    assert locked.verdict == "FAIL"
    proposal = stage_skill_evolution(
        repair.initial_candidate,
        repair,
        _judge(instrument_id),
        locked,
    )
    assert proposal.status == "REJECTED"
    assert proposal.hybrid_verdict.hard_verdict == "REJECT"


def test_unavailable_drift_evidence_holds() -> None:
    instrument_id = "ot2-transfer"
    repair = _repair(
        instrument_id,
        render_drift_candidate(instrument_id),
        scenario=SimulationScenario.UNAVAILABLE,
    )
    proposal = stage_skill_evolution(
        repair.initial_candidate,
        repair,
        _judge(instrument_id),
        _locked(repair.final_candidate),
    )
    assert proposal.drift_detection.verdict == "HOLD"
    assert proposal.status == "HOLD"


def test_evolution_summary_and_replay_cover_all_families(tmp_path: Path) -> None:
    for instrument_id in sorted(INSTRUMENTS):
        repair = _repair(instrument_id, render_drift_candidate(instrument_id))
        proposal = stage_skill_evolution(
            repair.initial_candidate,
            repair,
            _judge(instrument_id),
            _locked(repair.final_candidate),
        )
        write_canonical_json(tmp_path / instrument_id / "evolution.json", proposal)

    summary = summarize_evolution_study(tmp_path)
    assert summary["verdict"] == "PASS"
    assert summary["family_count"] == 4
    assert summary["staged_proposals"] == 8
    assert summary["unsafe_promotions"] == 0

    replay = replay_evolution_study(tmp_path, tmp_path / "replay")
    assert replay["verdict"] == "PASS"
    assert replay["identical"] == 8
