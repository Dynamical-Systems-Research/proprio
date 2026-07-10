import hashlib

import pytest

from proprio.adaptive_search import DebugCondition, evaluate_debug_suite
from proprio.adaptive_validation import (
    evaluate_adaptive_locked,
    generate_adaptive_microscopy_locked_conditions,
    seal_adaptive_candidate,
)
from proprio.instrument_types import CandidatePackage, GateCheck, HardGateResult, SimulationScenario

SOURCE = "def run(controller):\n    controller.measure()\n    return {'ok': 1}\n"


def candidate(source: str = SOURCE) -> CandidatePackage:
    return CandidatePackage(
        instrument_id="microscope-autofocus",
        skill_md="---\nname: fixture\ndescription: Fixture.\n---\n# Run\nRun.\n",
        skill_py=source,
        self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
        source_sha256="1" * 64,
        prompt_sha256="2" * 64,
        model="fixture",
        raw_response={},
    )


def evaluator(instrument_id, source, *, scenario, condition=None):
    del condition
    return HardGateResult(
        instrument_id=instrument_id,
        family="fixture",
        scenario=scenario,
        verdict="ADMIT",
        status="succeeded",
        checks=(GateCheck(check_id="physical-validity", passed=True),),
        trace=(),
        telemetry={},
        result={},
        runtime_error=None,
        skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
        simulator_sha256="3" * 64,
        verifier_sha256="4" * 64,
    )


def visible_suite(item: CandidatePackage):
    condition = DebugCondition(
        condition_id="visible",
        scenario=SimulationScenario.REPAIR,
        repetitions=1,
    )
    return evaluate_debug_suite(item, (condition,), evaluator=evaluator)


def test_locked_conditions_are_deterministic_and_not_visible_ids() -> None:
    first = generate_adaptive_microscopy_locked_conditions()
    second = generate_adaptive_microscopy_locked_conditions()
    assert first == second
    assert len(first) == 12
    assert all(condition.condition_id.startswith("locked-") for condition in first)
    assert all("start_z" in condition.parameter_map() for condition in first)
    assert all("measurement_noise_level" in condition.parameter_map() for condition in first)


def test_locked_qualification_is_bound_to_sealed_candidate() -> None:
    item = candidate()
    seal = seal_adaptive_candidate(item, visible_suite(item))
    report = evaluate_adaptive_locked(item, seal, evaluator=evaluator)
    assert report.verdict == "PASS"
    assert len(report.cases) == 12
    changed = candidate(SOURCE.replace("1", "2"))
    with pytest.raises(ValueError, match="selection seal"):
        evaluate_adaptive_locked(changed, seal, evaluator=evaluator)
