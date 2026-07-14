"""Complete third-party provider used by the installed-distribution test."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from proprio.instrument_plugins import InstrumentProvider, ProviderInstrument
from proprio.instrument_types import GateCheck, SimulationScenario
from proprio.skill_search import DebugCondition

HERE = Path(__file__).resolve().parent
INSTRUMENT_ID = "third_party.synthetic.counter"


class CounterController:
    def __init__(self, scenario: SimulationScenario) -> None:
        self.scenario = scenario
        self.trace: list[dict[str, Any]] = []
        self.measured = False

    def reset(self) -> None:
        self.trace.append({"sequence": 0, "operation": "reset"})

    def measure(self) -> dict[str, float]:
        self.measured = True
        self.trace.append({"sequence": 1, "operation": "measure", "value": 1.0})
        return {"value": 1.0}

    def telemetry(self) -> dict[str, bool]:
        return {"measured": self.measured}


def verify_trace(
    trace: tuple[dict[str, Any], ...], telemetry: dict[str, Any]
) -> tuple[GateCheck, ...]:
    operations = [row["operation"] for row in trace]
    return (
        GateCheck(
            check_id="reset-before-measurement",
            passed=operations == ["reset", "measure"],
            evidence={"operations": operations},
        ),
        GateCheck(
            check_id="measurement-produced",
            passed=telemetry.get("measured") is True,
            evidence={"measured": telemetry.get("measured")},
        ),
    )


def _condition(condition_id: str, scenario: SimulationScenario) -> DebugCondition:
    return DebugCondition(condition_id=condition_id, scenario=scenario, repetitions=1)


def instrument_provider() -> InstrumentProvider:
    instrument = ProviderInstrument(
        instrument_id=INSTRUMENT_ID,
        family="synthetic_measurement",
        source_path=HERE / "source.md",
        upstream_revision="synthetic-1.0.0",
        allowed_methods=frozenset({"reset", "measure"}),
        controller_factory=lambda scenario, _parameters: CounterController(scenario),
        verifier=verify_trace,
        simulator_path=lambda: Path(__file__),
        verifier_path=Path(__file__),
        acquisition_conditions=(_condition("acquisition", SimulationScenario.NOMINAL),),
        visible_conditions=(_condition("visible", SimulationScenario.NOMINAL),),
        locked_conditions=(_condition("locked", SimulationScenario.DRIFT),),
        evolution_conditions=(_condition("evolution", SimulationScenario.DRIFT),),
    )
    return InstrumentProvider(
        api_version="1",
        provider_id="third_party.synthetic",
        provider_version="1.0.0",
        instruments={INSTRUMENT_ID: instrument},
        runtime_kind="third-party",
    )
