import pytest

from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_types import SimulationScenario
from proprio.reference_instruments import INSTRUMENTS

NOMINAL_SKILLS = {
    "ot2-transfer": """def run(controller):
    controller.reset()
    controller.pick_up_tip()
    controller.aspirate(120.0)
    controller.dispense(120.0)
    controller.drop_tip()
    return {"transferred_ul": 120.0}
""",
    "star-transfer": """def run(controller):
    controller.initialize_channel()
    controller.aspirate_channel(100.0)
    controller.dispense_channel(100.0)
    controller.aspirate_channel(20.0)
    controller.dispense_channel(20.0)
    controller.eject_tip()
    return {"transferred_ul": 120.0}
""",
    "constant-current-cycle": """def run(controller):
    controller.reset()
    controller.configure_limits(2.8, 4.2)
    controller.apply_current(-1.0)
    controller.run_for(1800.0)
    controller.stop()
    return {"target_capacity_ah": 0.5}
""",
    "pulse-characterization": """def run(controller):
    controller.reset()
    controller.configure_voltage_window(2.8, 4.2)
    controller.pulse_current(-1.5, 10.0)
    controller.rest_for(30.0)
    controller.stop()
    return {"pulse_complete": True}
""",
    "powder-bed-scan": """def run(controller):
    controller.reset()
    controller.configure_bed(0.1, 0.04)
    controller.configure_laser(120.0, 500.0)
    controller.start_gas(18.0)
    controller.scan(20.0)
    controller.stop()
    return {"scan_complete": True}
""",
    "directed-energy-deposition": """def run(controller):
    controller.reset()
    controller.configure_feed(0.15, 10.0)
    controller.configure_laser(250.0)
    controller.start_gas(20.0)
    controller.deposit(25.0)
    controller.stop()
    return {"deposit_complete": True}
""",
    "hall-sweep": """def run(controller):
    controller.reset()
    controller.set_temperature(10.0)
    controller.wait_stable(0.05)
    controller.set_current(0.001)
    controller.sweep_field(-1.0, 1.0, 9, 0.2)
    controller.disable_current()
    return {"sweep_complete": True}
""",
    "cryogenic-resistance": """def run(controller):
    controller.reset()
    controller.set_temperature(4.2)
    controller.wait_stable(0.02)
    controller.set_current(0.001)
    voltage = controller.measure_four_wire()
    controller.disable_current()
    return {"voltage_v": voltage}
""",
}


REPAIRED_SKILLS = {
    "ot2-transfer": NOMINAL_SKILLS["ot2-transfer"].replace(
        "controller.aspirate(120.0)\n    controller.dispense(120.0)",
        "controller.aspirate(60.0)\n    controller.dispense(60.0)\n"
        "    controller.aspirate(60.0)\n    controller.dispense(60.0)",
    ),
    "star-transfer": NOMINAL_SKILLS["star-transfer"]
    .replace("100.0", "60.0")
    .replace("20.0", "60.0"),
    "constant-current-cycle": NOMINAL_SKILLS["constant-current-cycle"]
    .replace("-1.0", "-0.8")
    .replace("1800.0", "2250.0"),
    "pulse-characterization": NOMINAL_SKILLS["pulse-characterization"].replace("-1.5", "-1.0"),
    "powder-bed-scan": NOMINAL_SKILLS["powder-bed-scan"].replace("120.0", "88.0"),
    "directed-energy-deposition": NOMINAL_SKILLS["directed-energy-deposition"].replace(
        "250.0", "180.0"
    ),
    "hall-sweep": NOMINAL_SKILLS["hall-sweep"].replace("9, 0.2", "9, 0.6"),
    "cryogenic-resistance": NOMINAL_SKILLS["cryogenic-resistance"].replace("0.001", "0.0004"),
}


@pytest.mark.parametrize("instrument_id", sorted(INSTRUMENTS))
def test_nominal_skill_is_admitted(instrument_id: str) -> None:
    result = evaluate_instrument_skill(instrument_id, NOMINAL_SKILLS[instrument_id])
    assert result.verdict == "ADMIT", result.model_dump(mode="json")


@pytest.mark.parametrize("instrument_id", sorted(INSTRUMENTS))
def test_environment_change_rejects_nominal_skill_and_admits_repair(
    instrument_id: str,
) -> None:
    rejected = evaluate_instrument_skill(
        instrument_id,
        NOMINAL_SKILLS[instrument_id],
        scenario=SimulationScenario.REPAIR,
    )
    admitted = evaluate_instrument_skill(
        instrument_id,
        REPAIRED_SKILLS[instrument_id],
        scenario=SimulationScenario.REPAIR,
    )
    assert rejected.verdict == "REJECT", rejected.model_dump(mode="json")
    assert admitted.verdict == "ADMIT", admitted.model_dump(mode="json")


@pytest.mark.parametrize("instrument_id", sorted(INSTRUMENTS))
def test_unavailable_simulator_holds_without_fabricated_success(instrument_id: str) -> None:
    result = evaluate_instrument_skill(
        instrument_id,
        NOMINAL_SKILLS[instrument_id],
        scenario=SimulationScenario.UNAVAILABLE,
    )
    assert result.verdict == "HOLD"
    assert result.status == "unavailable"


def test_static_safety_rejects_imports_and_verifier_bypass() -> None:
    source = """import os

def run(controller):
    return {"valid": True}
"""
    result = evaluate_instrument_skill("ot2-transfer", source)
    assert result.verdict == "REJECT"
    assert result.checks[0].check_id == "static-safety"
