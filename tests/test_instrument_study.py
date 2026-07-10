from pathlib import Path

from proprio.artifacts import write_canonical_json
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_sources import load_instrument_source
from proprio.instrument_study import replay_instrument_study, summarize_instrument_study
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    RepairEpisode,
    RepairSubmission,
    SimulationScenario,
)

INITIAL = """def run(controller):
    controller.reset()
    controller.pick_up_tip()
    controller.aspirate(120.0)
    controller.dispense(120.0)
    controller.drop_tip()
    return {"transferred_ul": 120.0}
"""

REPAIRED = """def run(controller):
    controller.reset()
    controller.pick_up_tip()
    controller.aspirate(60.0)
    controller.dispense(60.0)
    controller.aspirate(60.0)
    controller.dispense(60.0)
    controller.drop_tip()
    return {"transferred_ul": 120.0}
"""

SKILL_MD = """---
name: ot2-transfer
description: Transfer 120 microliters through a declared controller.
---
# Run
Execute the source-grounded transfer and preserve cleanup.
"""


def _candidate(source: str) -> CandidatePackage:
    _, source_hash = load_instrument_source("ot2-transfer")
    return CandidatePackage(
        instrument_id="ot2-transfer",
        skill_md=SKILL_MD,
        skill_py=source,
        self_judgment={"verdict": "ACCEPT", "basis": ["test fixture"]},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model="dsv4",
        raw_response={},
    )


def _episode(arm: FeedbackArm, final_source: str) -> RepairEpisode:
    initial = _candidate(INITIAL)
    final = _candidate(final_source)
    submission = RepairSubmission(
        diagnosis="stroke capacity changed",
        evidence_refs=("stroke-capacity",),
        skill_md=SKILL_MD,
        skill_py=final_source,
        expected_effect="split strokes",
        risks=(),
        self_judgment={"verdict": "ACCEPT", "basis": ["test fixture"]},
    )
    tool_events = ()
    raw_responses = ()
    if arm is FeedbackArm.TRUTHFUL and final_source == REPAIRED:
        tool_events = (
            {
                "name": "run_simulator",
                "arguments": {},
                "result": {
                    "evidence_ref": "gate:fixture:repair",
                    "checks": [{"check_id": "stroke-capacity", "passed": False}],
                },
            },
            {
                "name": "submit_repair",
                "arguments": submission.model_dump(mode="json"),
                "result": {"status": "captured"},
            },
            {
                "name": "run_simulator",
                "arguments": {},
                "result": {
                    "evidence_ref": "gate:fixture-repaired:repair",
                    "checks": [{"check_id": "stroke-capacity", "passed": True}],
                },
            },
        )
        raw_responses = ({"turn": 1}, {"turn": 2}, {"turn": 3})
    return RepairEpisode(
        instrument_id="ot2-transfer",
        family="liquid_handling",
        feedback_arm=arm,
        scenario=SimulationScenario.REPAIR,
        initial_candidate=initial,
        final_candidate=final,
        initial_gate=evaluate_instrument_skill(
            "ot2-transfer", INITIAL, scenario=SimulationScenario.REPAIR
        ),
        final_gate=evaluate_instrument_skill(
            "ot2-transfer", final_source, scenario=SimulationScenario.REPAIR
        ),
        submissions=(submission,) if final_source == REPAIRED else (),
        tool_events=tool_events,
        raw_responses=raw_responses,
        agent_status="CANDIDATE",
        agent_summary="fixture",
    )


def test_study_summary_measures_causal_feedback_and_replay(tmp_path: Path) -> None:
    instrument_dir = tmp_path / "ot2-transfer"
    write_canonical_json(instrument_dir / "candidate.json", _candidate(INITIAL))
    for arm in FeedbackArm:
        final = REPAIRED if arm is FeedbackArm.TRUTHFUL else INITIAL
        write_canonical_json(instrument_dir / f"repair-{arm.value}.json", _episode(arm, final))

    summary = summarize_instrument_study(tmp_path, instrument_ids=("ot2-transfer",))
    assert summary["claim_gates"]["causal_repair"] == "PASS"
    assert summary["causal_uplift_over_none"] == 1.0
    assert summary["hard_failure_overrides"] == 0

    replay = replay_instrument_study(tmp_path, tmp_path / "replay")
    assert replay["verdict"] == "PASS"
    assert replay["episodes"] == 4
