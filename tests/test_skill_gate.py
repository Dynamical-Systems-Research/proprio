from __future__ import annotations

from proprio.instrument_types import SimulationScenario
from proprio.instruments import evaluate_instrument_skill
from proprio.skill_gate import evaluate_skill
from proprio.smu import SimulatedSMUController

CORRECT_SKILL = """
def run(controller):
    controller.identify()
    controller.reset()
    controller.set_current_limit(0.002)
    controller.set_measurement_range(0.01)
    controller.set_voltage(1.0)
    controller.enable_output()
    current = controller.measure_current()
    controller.disable_output()
    return {"current_a": current}
"""

WRONG_RANGE_SKILL = """
def run(controller):
    controller.identify()
    controller.reset()
    controller.set_current_limit(0.0002)
    controller.set_measurement_range(0.0001)
    controller.set_voltage(1.0)
    controller.enable_output()
    current = controller.measure_current()
    controller.disable_output()
    return {"current_a": current}
"""

WRONG_ORDER_SKILL = """
def run(controller):
    controller.identify()
    controller.set_voltage(1.0)
    controller.enable_output()
    controller.set_current_limit(0.002)
    controller.set_measurement_range(0.01)
    current = controller.measure_current()
    controller.disable_output()
    return {"current_a": current}
"""


def test_pyvisa_sim_transport_identifies_keithley() -> None:
    with SimulatedSMUController() as controller:
        assert "MODEL 2450" in controller.identify()


def test_correct_skill_is_admitted() -> None:
    result = evaluate_skill(CORRECT_SKILL)
    assert result.verdict == "ADMIT"


def test_wrong_range_and_compliance_are_rejected() -> None:
    result = evaluate_skill(WRONG_RANGE_SKILL)
    assert result.verdict == "REJECT"
    assert {check["check_id"] for check in result.checks if check["status"].value == "failed"} >= {
        "range-contract",
        "compliance-contract",
    }


def test_wrong_command_order_is_rejected() -> None:
    result = evaluate_skill(WRONG_ORDER_SKILL)
    assert result.verdict == "REJECT"
    assert "compliance-before-output" in {
        check["check_id"] for check in result.checks if check["status"].value == "failed"
    }


def test_imports_are_rejected_without_execution() -> None:
    result = evaluate_skill("import os\ndef run(controller):\n    return {}\n")
    assert result.verdict == "REJECT"
    assert result.trace == ()


def test_provider_preserves_keithley_negative_control() -> None:
    gate = evaluate_instrument_skill(
        "proprio.keithley.keithley-2450-measure-current",
        WRONG_RANGE_SKILL,
    )
    failed = {check.check_id for check in gate.checks if not check.passed}
    assert gate.verdict == "REJECT"
    assert {"range-contract", "compliance-contract"} <= failed


def test_provider_holds_when_keithley_simulator_is_unavailable() -> None:
    gate = evaluate_instrument_skill(
        "proprio.keithley.keithley-2450-measure-current",
        CORRECT_SKILL,
        scenario=SimulationScenario.UNAVAILABLE,
    )
    assert gate.verdict == "HOLD"
    assert gate.status == "unavailable"
