import pytest

from proprio.confirmatory_instruments import CONFIRMATORY_INSTRUMENTS
from proprio.confirmatory_qualification import evaluate_confirmatory_skill, load_confirmatory_source
from proprio.confirmatory_skills import (
    render_confirmatory_invalid,
    render_confirmatory_nominal,
    render_confirmatory_repair,
)
from proprio.confirmatory_validation import (
    evaluate_confirmatory_validation,
    seal_confirmatory_candidate,
)
from proprio.instrument_types import CandidatePackage, SimulationScenario


@pytest.mark.parametrize("instrument_id", sorted(CONFIRMATORY_INSTRUMENTS))
def test_nominal_skill_exposes_repairable_support_shift(instrument_id: str) -> None:
    source = render_confirmatory_nominal(instrument_id)
    assert evaluate_confirmatory_skill(instrument_id, source).verdict == "ADMIT"
    assert (
        evaluate_confirmatory_skill(
            instrument_id,
            source,
            scenario=SimulationScenario.REPAIR,
        ).verdict
        == "REJECT"
    )


@pytest.mark.parametrize("instrument_id", sorted(CONFIRMATORY_INSTRUMENTS))
def test_conservative_repair_preserves_history(instrument_id: str) -> None:
    source = render_confirmatory_repair(instrument_id)
    for scenario in (SimulationScenario.NOMINAL, SimulationScenario.REPAIR):
        assert (
            evaluate_confirmatory_skill(instrument_id, source, scenario=scenario).verdict == "ADMIT"
        )


@pytest.mark.parametrize("instrument_id", sorted(CONFIRMATORY_INSTRUMENTS))
@pytest.mark.parametrize(
    "failure_class",
    ["unsafe_setting", "wrong_target", "cleanup_omitted", "wrong_order"],
)
def test_confirmatory_gate_rejects_each_failure_class(
    instrument_id: str,
    failure_class: str,
) -> None:
    source = render_confirmatory_invalid(instrument_id, failure_class)
    gate = evaluate_confirmatory_skill(
        instrument_id,
        source,
        scenario=SimulationScenario.REPAIR,
    )
    assert gate.verdict == "REJECT"
    assert any(not check.passed for check in gate.checks)


def test_confirmatory_simulator_unavailable_holds() -> None:
    gate = evaluate_confirmatory_skill(
        "absorbance-plate-read",
        render_confirmatory_repair("absorbance-plate-read"),
        scenario=SimulationScenario.UNAVAILABLE,
    )
    assert gate.verdict == "HOLD"
    assert gate.status == "unavailable"


def test_confirmatory_skill_cannot_read_simulator_internals() -> None:
    source = """def run(controller):
    maximum = controller.max_gain
    return {"maximum": maximum}
"""
    gate = evaluate_confirmatory_skill("fluorescence-plate-read", source)
    assert gate.verdict == "REJECT"
    assert "direct reads of simulator state are forbidden" in (gate.runtime_error or "")


@pytest.mark.parametrize("instrument_id", sorted(CONFIRMATORY_INSTRUMENTS))
def test_conservative_candidate_passes_fifty_locked_conditions(instrument_id: str) -> None:
    _, source_hash = load_confirmatory_source(instrument_id)
    candidate = CandidatePackage(
        instrument_id=instrument_id,
        skill_md=f"---\nname: {instrument_id}\ndescription: fixture\n---\n",
        skill_py=render_confirmatory_repair(instrument_id),
        self_judgment={"verdict": "ACCEPT"},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model="fixture",
        raw_response={},
    )
    report = evaluate_confirmatory_validation(candidate, seal_confirmatory_candidate(candidate))
    assert len(report.cases) == 50
    assert report.passed_cases == 50
    assert report.verdict == "PASS"
