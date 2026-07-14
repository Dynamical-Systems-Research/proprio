from pathlib import Path

import pytest

from proprio.external_instruments import VALID_FIXTURES
from proprio.instrument_qualification import compile_instrument_skill
from proprio.instrument_types import CandidatePackage
from proprio.instruments import load_instrument_source
from proprio.interface import (
    candidate_from_directory,
    execute_candidate,
    inspect_source,
    read_visible_evidence,
    stage_evolution,
    verify_locked,
)

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT = "north-pipette-calibration"
EVOLUTION_FIXTURE = """def run(controller):
    controller.reset()
    info = controller.sample_info()
    target = info['target_volume_ml']
    liquid = info['liquid']
    controller.get_constraints(target)
    if liquid == 'water':
        overaspirate = 0.025 * target
    else:
        overaspirate = 0.0625 * target
    result = controller.measure(target, overaspirate, 20, 1, 3)
    for _ in range(5):
        if result['relative_error'] > 0.04:
            overaspirate = overaspirate * (target / result['mean_volume_ml'])
            result = controller.measure(target, overaspirate, 20, 1, 3)
    controller.cleanup()
    return result
"""


def _evolved_candidate() -> CandidatePackage:
    _, source_hash = load_instrument_source(INSTRUMENT)
    return CandidatePackage(
        instrument_id=INSTRUMENT,
        skill_md=(ROOT / "skills" / INSTRUMENT / "SKILL.md").read_text(encoding="utf-8"),
        skill_py=EVOLUTION_FIXTURE,
        self_judgment={"verdict": "ACCEPT", "basis": ["test evolution fixture"]},
        source_sha256=source_hash,
        prompt_sha256="test-evolution-fixture",
        model="test-fixture",
        raw_response={},
    )


def test_source_inspection_exposes_only_the_visible_controller_contract() -> None:
    record = inspect_source(INSTRUMENT)
    assert record["instrument_id"] == INSTRUMENT
    assert record["source_sha256"]
    assert record["controller_methods"] == [
        "cleanup",
        "get_constraints",
        "measure",
        "reset",
        "sample_info",
    ]
    assert "locked_conditions" not in record
    assert "evolution_conditions" not in record
    assert record["skill_contract"]["skill_py"]["entrypoint"] == "run(controller)"
    assert record["skill_contract"]["skill_py"]["bounded_for_loops_only"] == (
        "range(...) with literal integer bounds"
    )
    assert record["skill_contract"]["skill_md"]["frontmatter_required"] == [
        "name",
        "description",
    ]


def test_bounded_dsl_supports_safe_state_checks() -> None:
    source = """def run(controller):
    info = controller.sample_info()
    liquid = None
    if "liquid" in info:
        liquid = info["liquid"]
    if liquid is not None:
        controller.cleanup()
    return {"liquid": liquid}
"""
    compiled = compile_instrument_skill(source, frozenset({"sample_info", "cleanup"}))
    assert callable(compiled)


def test_bounded_dsl_supports_break_inside_literal_range() -> None:
    source = """def run(controller):
    result = {}
    for attempt in range(3):
        result = controller.measure()
        if result["passed"]:
            break
    return result
"""
    compiled = compile_instrument_skill(source, frozenset({"measure"}))
    assert callable(compiled)


def test_bounded_dsl_rejects_non_range_iteration_cleanly() -> None:
    source = """def run(controller):
    for attempt in [1, 2, 3]:
        controller.measure()
    return {}
"""
    with pytest.raises(ValueError, match=r"for loops must iterate over range\(\.\.\.\)"):
        compile_instrument_skill(source, frozenset({"measure"}))


def test_external_agent_candidate_runs_visible_and_locked_verification(tmp_path: Path) -> None:
    candidate = _evolved_candidate()
    visible = execute_candidate(INSTRUMENT, candidate, output_dir=tmp_path / "visible")
    evidence = read_visible_evidence(tmp_path / "visible")
    locked = verify_locked(candidate, output_dir=tmp_path / "locked")

    assert visible["decision"] == "ADMIT"
    assert evidence["candidate_sha256"] == visible["candidate_sha256"]
    assert locked["decision"] == "ADMIT"
    assert locked["hardware_validation_required"] is True

    with pytest.raises(FileExistsError, match="output directory is not empty"):
        execute_candidate(INSTRUMENT, candidate, output_dir=tmp_path / "visible")


def test_evolution_stages_only_after_drift_and_non_regressive_replay(tmp_path: Path) -> None:
    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    (parent_dir / "SKILL.md").write_text(
        "---\nname: north-pipette-calibration\n"
        "description: Fixed pipette calibration procedure.\n---\n\n# Run\nCalibrate once.\n",
        encoding="utf-8",
    )
    (parent_dir / "skill.py").write_text(VALID_FIXTURES[INSTRUMENT], encoding="utf-8")
    parent = candidate_from_directory(INSTRUMENT, parent_dir, agent="parent")
    candidate = _evolved_candidate()

    result = stage_evolution(parent, candidate, output_dir=tmp_path / "evolution")

    assert result["drift_detected"] is True
    assert result["candidate_changed"] is True
    assert result["status"] == "STAGED"
    assert set(result["candidate_verdicts"].values()) == {"ADMIT"}


def test_evolution_holds_when_parent_remains_valid(tmp_path: Path) -> None:
    parent = _evolved_candidate()
    result = stage_evolution(parent, parent, output_dir=tmp_path / "evolution")
    assert result["drift_detected"] is False
    assert result["status"] == "HOLD"
