"""Published reduced-order instrument definitions and qualification runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proprio.instrument_qualification import evaluate_controller_skill
from proprio.instrument_types import HardGateResult, SimulationScenario
from proprio.simulated_controllers import SIMULATED_CONTROLLERS, build_simulated_controller
from proprio.simulated_verifiers import verify_simulated_instrument
from proprio.skill_search import DebugCondition

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_REVISION = "9a462d0dffaf39a281c1b48388c9efd81f72c82b"


@dataclass(frozen=True)
class SimulatedInstrumentDefinition:
    """Definition consumed by the agent-neutral qualification interface."""

    instrument_id: str
    family: str
    source_path: Path
    allowed_methods: frozenset[str]
    upstream_revision: str
    verifier_path: Path
    acquisition_conditions: tuple[DebugCondition, ...]
    visible_conditions: tuple[DebugCondition, ...]
    locked_conditions: tuple[DebugCondition, ...]
    evolution_conditions: tuple[DebugCondition, ...]


def _condition(condition_id: str, scenario: SimulationScenario) -> DebugCondition:
    return DebugCondition(condition_id=condition_id, scenario=scenario, repetitions=3)


def _definition(instrument_id: str) -> SimulatedInstrumentDefinition:
    controller = SIMULATED_CONTROLLERS[instrument_id]
    return SimulatedInstrumentDefinition(
        instrument_id=instrument_id,
        family=controller.family,
        source_path=ROOT / "skills" / instrument_id / "references" / "controller.md",
        allowed_methods=controller.allowed_methods,
        upstream_revision=HISTORICAL_REVISION,
        verifier_path=Path(__file__).with_name("simulated_verifiers.py"),
        acquisition_conditions=(_condition("nominal-acquisition", SimulationScenario.NOMINAL),),
        visible_conditions=(
            _condition("nominal-replay", SimulationScenario.NOMINAL),
            _condition("registered-support-change", SimulationScenario.REPAIR),
        ),
        locked_conditions=(_condition("locked-support-change", SimulationScenario.REPAIR),),
        evolution_conditions=(_condition("deployment-drift", SimulationScenario.DRIFT),),
    )


SIMULATED_INSTRUMENTS = {
    instrument_id: _definition(instrument_id) for instrument_id in SIMULATED_CONTROLLERS
}


def load_simulated_source(instrument_id: str) -> tuple[str, str]:
    """Load the source bundled with an independently installable skill package."""

    import hashlib

    text = SIMULATED_INSTRUMENTS[instrument_id].source_path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


def evaluate_simulated_skill(
    instrument_id: str,
    skill_py: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    condition: dict[str, float] | None = None,
) -> HardGateResult:
    """Execute one bounded procedure against the built-in simulator and verifier."""

    definition = SIMULATED_INSTRUMENTS[instrument_id]
    controller = build_simulated_controller(instrument_id, scenario)
    return evaluate_controller_skill(
        instrument_id,
        definition.family,
        skill_py,
        scenario=scenario,
        allowed_methods=definition.allowed_methods,
        controller=controller,
        verifier=verify_simulated_instrument,
        simulator_path=Path(__file__).with_name("simulated_controllers.py"),
        verifier_path=definition.verifier_path,
        condition_evidence=condition,
    )


def simulated_runtime_identity() -> dict[str, Any]:
    """Describe the compact built-in runtime retained from the validated release."""

    return {
        "kind": "built-in-reduced-order-simulator",
        "historical_revision": HISTORICAL_REVISION,
        "instrument_ids": sorted(SIMULATED_INSTRUMENTS),
    }
