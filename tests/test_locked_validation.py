from pathlib import Path

import pytest

from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_sources import load_instrument_source
from proprio.instrument_types import CandidatePackage
from proprio.locked_validation import (
    evaluate_locked_validation,
    generate_locked_conditions,
    run_locked_validation_once,
    seal_candidate,
)
from proprio.reference_instruments import INSTRUMENTS
from proprio.reference_skills import render_drift_candidate, render_repair_parent


def _candidate(instrument_id: str, source: str) -> CandidatePackage:
    _, source_hash = load_instrument_source(instrument_id)
    return CandidatePackage(
        instrument_id=instrument_id,
        skill_md=f"---\nname: {instrument_id}\ndescription: fixture\n---\n",
        skill_py=source,
        self_judgment={"verdict": "ACCEPT"},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model="fixture",
        raw_response={},
    )


@pytest.mark.parametrize("instrument_id", sorted(INSTRUMENTS))
def test_conservative_candidate_passes_locked_conditions(instrument_id: str) -> None:
    candidate = _candidate(instrument_id, render_drift_candidate(instrument_id))
    report = evaluate_locked_validation(candidate, seal_candidate(candidate))
    assert len(report.cases) == 50
    assert report.passed_cases == 50
    assert report.verdict == "PASS"
    assert generate_locked_conditions(instrument_id) == generate_locked_conditions(instrument_id)


def test_pre_drift_parent_fails_locked_conditions() -> None:
    candidate = _candidate("ot2-transfer", render_repair_parent("ot2-transfer"))
    report = evaluate_locked_validation(candidate, seal_candidate(candidate))
    assert report.verdict == "FAIL"
    assert report.passed_cases == 0


def test_direct_simulator_state_read_is_rejected() -> None:
    source = """def run(controller):
    limit = controller.max_transfer_ul
    return {"limit": limit}
"""
    gate = evaluate_instrument_skill("ot2-transfer", source)
    assert gate.verdict == "REJECT"
    assert "direct reads of simulator state are forbidden" in (gate.runtime_error or "")


def test_locked_validation_refuses_second_selection_execution(tmp_path: Path) -> None:
    candidate = _candidate("hall-sweep", render_drift_candidate("hall-sweep"))
    seal_path = tmp_path / "selection-seal.json"
    result_path = tmp_path / "locked-validation.json"
    first = run_locked_validation_once(candidate, seal_path, result_path)
    assert first.verdict == "PASS"
    with pytest.raises(FileExistsError, match="already executed"):
        run_locked_validation_once(candidate, seal_path, result_path)
