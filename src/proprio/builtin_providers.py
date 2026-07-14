"""Provider adapters for Proprio's validated simulator families."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from proprio.external_instruments import (
    EXTERNAL_INSTRUMENTS,
    ExternalController,
    ExternalInstrumentDefinition,
)
from proprio.instrument_plugins import InstrumentProvider, ProviderInstrument
from proprio.instrument_types import GateCheck, SimulationScenario
from proprio.simulated_controllers import build_simulated_controller
from proprio.simulated_instruments import SIMULATED_INSTRUMENTS
from proprio.simulated_verifiers import verify_simulated_instrument

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent


def _skill_root() -> Path:
    local = ROOT / "skills"
    return local if local.is_dir() else PACKAGE_ROOT / "skills"


def _source_root() -> Path:
    local = ROOT / "sources"
    return local if local.is_dir() else PACKAGE_ROOT / "sources"


def reduced_order_provider() -> InstrumentProvider:
    """Adapt the six reduced-order simulators without changing their verified runtime."""

    provider_id = "proprio.reduced_order"
    skill_root = _skill_root()
    instruments = {}
    for local_id, definition in SIMULATED_INSTRUMENTS.items():
        instrument_id = f"{provider_id}.{local_id}"

        def controller_factory(
            scenario: SimulationScenario,
            _parameters: Mapping[str, float],
            *,
            _local_id: str = local_id,
        ) -> Any:
            return build_simulated_controller(_local_id, scenario)

        def verifier(
            trace: Sequence[dict[str, Any]],
            telemetry: dict[str, Any],
            *,
            _local_id: str = local_id,
            _family: str = definition.family,
        ) -> tuple[GateCheck, ...]:
            return verify_simulated_instrument(_local_id, _family, trace, telemetry)

        instruments[instrument_id] = ProviderInstrument(
            instrument_id=instrument_id,
            family=definition.family,
            source_path=skill_root / local_id / "references" / "controller.md",
            upstream_revision=definition.upstream_revision,
            allowed_methods=definition.allowed_methods,
            controller_factory=controller_factory,
            verifier=verifier,
            simulator_path=lambda: Path(__file__).with_name("simulated_controllers.py"),
            verifier_path=definition.verifier_path,
            acquisition_conditions=definition.acquisition_conditions,
            visible_conditions=definition.visible_conditions,
            locked_conditions=definition.locked_conditions,
            evolution_conditions=definition.evolution_conditions,
        )
    return InstrumentProvider(
        api_version="1",
        provider_id=provider_id,
        provider_version="0.4.0",
        instruments=instruments,
        runtime_kind="built-in",
    )


def external_reference_provider() -> InstrumentProvider:
    """Adapt the three pinned upstream simulators without changing their verifier."""

    provider_id = "proprio.external_reference"
    source_root = _source_root()
    instruments = {}
    for local_id, definition in EXTERNAL_INSTRUMENTS.items():
        instrument_id = f"{provider_id}.{local_id}"

        def controller_factory(
            scenario: SimulationScenario,
            parameters: Mapping[str, float],
            *,
            _definition: ExternalInstrumentDefinition = definition,
        ) -> ExternalController:
            return _definition.controller_type(scenario, parameters)

        def verifier(
            trace: Sequence[dict[str, Any]],
            telemetry: dict[str, Any],
            *,
            _definition: ExternalInstrumentDefinition = definition,
            _local_id: str = local_id,
        ) -> tuple[GateCheck, ...]:
            return _definition.verifier(_local_id, _definition.family, trace, telemetry)

        instruments[instrument_id] = ProviderInstrument(
            instrument_id=instrument_id,
            family=definition.family,
            source_path=source_root / "instruments" / local_id / "source.md",
            upstream_revision=definition.upstream_revision,
            allowed_methods=definition.allowed_methods,
            controller_factory=controller_factory,
            verifier=verifier,
            simulator_path=definition.simulator_path,
            verifier_path=definition.verifier_path,
            acquisition_conditions=definition.acquisition_conditions,
            visible_conditions=definition.visible_conditions,
            locked_conditions=definition.locked_conditions,
            evolution_conditions=definition.evolution_conditions,
        )
    return InstrumentProvider(
        api_version="1",
        provider_id=provider_id,
        provider_version="0.4.0",
        instruments=instruments,
        runtime_kind="external",
    )
