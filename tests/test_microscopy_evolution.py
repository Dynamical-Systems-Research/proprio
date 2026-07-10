import hashlib
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from proprio.artifacts import write_canonical_json
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    JudgeEpisode,
    JudgeReview,
    LockedConditionResult,
    LockedValidationReport,
    RepairEpisode,
    RepairSubmission,
    SimulationScenario,
)
from proprio.microscopy import (
    FAMILY,
    INSTRUMENT_ID,
    MicroscopyController,
    evaluate_microscope_skill,
    load_microscopy_source,
)
from proprio.microscopy_evolution import (
    generate_microscopy_evolution_conditions,
    replay_microscopy_evolution,
    seal_microscopy_evolution_candidate,
    stage_microscopy_evolution,
)
from proprio.schema import canonical_json


class FakeBackend:
    def __init__(self) -> None:
        y, x = np.indices((256, 256))
        self.sharp = (((x // 8 + y // 8) % 2) * 180 + 40).astype(np.float64)
        self.z = 0
        self.calibration_required = True

    def clear_buffers(self) -> None: ...
    def prepare_sample(self) -> None: ...

    def set_noise_level(self, value: float) -> None:
        assert value == 2.0

    def move_to(self, x: int, y: int, z: int) -> None:
        assert (x, y) == (0, 0)
        self.z = z

    def calibrate(self) -> None:
        self.calibration_required = False

    def autofocus(self, dz_steps: int) -> dict:
        lower, upper = self.z - dz_steps // 2, self.z + dz_steps // 2
        self.z = 0 if lower <= 0 <= upper else min((lower, upper), key=abs)
        return {"selected_z": self.z, "sweep_steps": dz_steps}

    def settle(self) -> None: ...

    def capture(self) -> np.ndarray:
        return gaussian_filter(self.sharp, sigma=max(abs(self.z) / 100.0, 0.01))

    def position(self) -> tuple[int, int, int]:
        return (0, 0, self.z)

    def close(self) -> None: ...


def _source(sweep_steps: int) -> str:
    return f"""def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus({sweep_steps})
    controller.settle()
    controller.capture_frame()
    controller.release()
    return {{"capture": "focused"}}
"""


def _candidate(source: str) -> CandidatePackage:
    _, source_hash = load_microscopy_source(INSTRUMENT_ID)
    return CandidatePackage(
        instrument_id=INSTRUMENT_ID,
        skill_md=(
            "---\nname: microscope-autofocus\n"
            "description: Calibrate, focus, capture, and release.\n---\n# Run\nExecute.\n"
        ),
        skill_py=source,
        self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model="deepseek/deepseek-v4-flash",
        raw_response={},
    )


def _evaluator(instrument_id: str, source: str, *, scenario, condition=None):
    assert instrument_id == INSTRUMENT_ID
    defaults = {"nominal": 800, "repair": 1200, "drift": 1800}
    start_z = int((condition or {}).get("start_z", defaults[scenario.value]))
    return evaluate_microscope_skill(
        source,
        scenario=scenario,
        controller=MicroscopyController(FakeBackend(), start_z=start_z),
    )


def test_microscopy_evolution_conditions_are_frozen_and_inside_support() -> None:
    conditions = generate_microscopy_evolution_conditions()
    assert len(conditions) == 10
    assert all(1600 <= row["value"] <= 1950 for row in conditions)
    assert len({row["condition_id"] for row in conditions}) == 10


def test_microscopy_evolution_stages_and_replays_without_mutating_parent(
    tmp_path: Path,
) -> None:
    parent, proposed = _candidate(_source(3200)), _candidate(_source(4200))
    initial = _evaluator(INSTRUMENT_ID, parent.skill_py, scenario=SimulationScenario.DRIFT)
    final = _evaluator(INSTRUMENT_ID, proposed.skill_py, scenario=SimulationScenario.DRIFT)
    failed = tuple(check.check_id for check in initial.checks if not check.passed)
    repair = RepairEpisode(
        instrument_id=INSTRUMENT_ID,
        family=FAMILY,
        feedback_arm=FeedbackArm.TRUTHFUL,
        scenario=SimulationScenario.DRIFT,
        initial_candidate=parent,
        final_candidate=proposed,
        initial_gate=initial,
        final_gate=final,
        submissions=(
            RepairSubmission(
                diagnosis="the changed holder moved focus outside the centered sweep",
                evidence_refs=failed,
                skill_md=proposed.skill_md,
                skill_py=proposed.skill_py,
                expected_effect="cover the shifted focus plane",
                risks=("real hardware remains unqualified",),
                self_judgment={"verdict": "ACCEPT", "basis": list(failed)},
            ),
        ),
        tool_events=(
            {
                "name": "run_simulator",
                "result": {
                    "evidence_ref": "gate:initial",
                    "checks": [check.model_dump(mode="json") for check in initial.checks],
                },
            },
            {
                "name": "submit_repair",
                "arguments": {"evidence_refs": list(failed)},
                "result": {"status": "captured"},
            },
            {
                "name": "run_simulator",
                "result": {
                    "evidence_ref": "gate:final",
                    "checks": [check.model_dump(mode="json") for check in final.checks],
                },
            },
            {"name": "run_history", "result": {"all_admit": True}},
        ),
        raw_responses=(),
        agent_status="CANDIDATE",
        agent_summary="fixture",
    )
    review = JudgeEpisode(
        instrument_id=INSTRUMENT_ID,
        review=JudgeReview(
            verdict="ACCEPT",
            critical_findings=(),
            evidence_refs=("gate:final",),
            summary="fixture",
        ),
        tool_events=(),
        raw_responses=(),
        status="completed",
    )
    seal = seal_microscopy_evolution_candidate(proposed)
    conditions = generate_microscopy_evolution_conditions()
    cases = tuple(
        LockedConditionResult(
            **condition,
            gate=_evaluator(
                INSTRUMENT_ID,
                proposed.skill_py,
                scenario=SimulationScenario.DRIFT,
                condition={"start_z": condition["value"]},
            ),
        )
        for condition in conditions
    )
    locked = LockedValidationReport(
        instrument_id=INSTRUMENT_ID,
        candidate_sha256=seal.candidate_sha256,
        selection_seal_sha256=hashlib.sha256(canonical_json(seal)).hexdigest(),
        validation_preregistration_sha256=seal.validation_preregistration_sha256,
        suite_sha256=hashlib.sha256(canonical_json(conditions)).hexdigest(),
        cases=cases,
        passed_cases=len(cases),
        verdict="PASS",
    )
    proposal = stage_microscopy_evolution(
        parent,
        repair,
        review,
        locked,
        evaluator=_evaluator,
    )
    assert proposal.status == "STAGED"
    assert proposal.parent_candidate.skill_py == _source(3200)
    assert proposal.lineage.hardware_gate_required is True

    write_canonical_json(tmp_path / "evolution.json", proposal)
    write_canonical_json(tmp_path / "parent.json", {"replicate": "replicate-00"})
    replay = replay_microscopy_evolution(tmp_path, tmp_path / "replay")
    assert replay["verdict"] == "PASS"

    no_history = repair.model_copy(update={"tool_events": repair.tool_events[:-1]})
    rejected = stage_microscopy_evolution(
        parent,
        no_history,
        review,
        locked,
        evaluator=_evaluator,
    )
    assert rejected.status == "REJECTED"
    assert rejected.hybrid_verdict.hard_verdict == "REJECT"
