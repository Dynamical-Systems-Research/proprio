"""Provider adapters for Proprio's validated simulator families."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from proprio.external_instruments import (
    EXTERNAL_INSTRUMENTS,
    ExternalController,
    ExternalInstrumentDefinition,
)
from proprio.instrument_plugins import InstrumentProvider, ProviderInstrument
from proprio.instrument_types import GateCheck, InstrumentRuntimeUnavailable, SimulationScenario
from proprio.simulated_controllers import build_simulated_controller
from proprio.simulated_instruments import SIMULATED_INSTRUMENTS
from proprio.simulated_verifiers import verify_simulated_instrument
from proprio.skill_search import DebugCondition

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
        provider_version="0.5.0",
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
        provider_version="0.5.0",
        instruments=instruments,
        runtime_kind="external",
    )


def _condition(
    condition_id: str,
    scenario: SimulationScenario,
    **parameters: float,
) -> DebugCondition:
    return DebugCondition(
        condition_id=condition_id,
        scenario=scenario,
        parameters=tuple(parameters.items()),
        repetitions=1,
    )


def keithley_provider() -> InstrumentProvider:
    """Expose the validated pyvisa-sim SMU through the common provider runtime."""

    from proprio.skill_gate import ALLOWED_METHODS
    from proprio.smu import SimulatedSMUController
    from proprio.smu_verifier import verify_keithley

    provider_id = "proprio.keithley"
    instrument_id = f"{provider_id}.keithley-2450-measure-current"

    def controller_factory(
        scenario: SimulationScenario,
        parameters: Mapping[str, float],
    ) -> SimulatedSMUController:
        if parameters:
            raise ValueError(f"unsupported Keithley condition fields: {sorted(parameters)}")
        if scenario is SimulationScenario.UNAVAILABLE:
            raise InstrumentRuntimeUnavailable("pyvisa-sim transport is unavailable")
        return SimulatedSMUController()

    nominal = _condition("certified-fixture", SimulationScenario.NOMINAL)
    instrument = ProviderInstrument(
        instrument_id=instrument_id,
        family="electrical_source_measurement",
        source_path=_source_root() / "instruments" / "keithley-2450-measure-current" / "source.md",
        upstream_revision="Keithley 2450 Reference Manual 2450-901-01 Rev. D",
        allowed_methods=ALLOWED_METHODS,
        controller_factory=controller_factory,
        verifier=verify_keithley,
        simulator_path=lambda: PACKAGE_ROOT / "data" / "keithley-2450-sim.yaml",
        verifier_path=PACKAGE_ROOT / "smu_verifier.py",
        acquisition_conditions=(nominal,),
        visible_conditions=(
            nominal.model_copy(update={"condition_id": "visible-certified-fixture"}),
        ),
        locked_conditions=(nominal.model_copy(update={"condition_id": "locked-circuit-replay"}),),
        evolution_conditions=(),
    )
    return InstrumentProvider(
        api_version="1",
        provider_id=provider_id,
        provider_version="0.5.0",
        instruments={instrument_id: instrument},
        runtime_kind="built-in-pyvisa-sim",
    )


OPENFLEXURE_REVISION = "d26b93e1be1093e9d696b634dd1f7dde3bb7142a"
OPENFLEXURE_TREE = "a8e138b993aababbbb77ef371446d986e117ae67"


def _validate_openflexure_checkout() -> None:
    root = Path(
        os.environ.get(
            "PROPRIO_OPENFLEXURE_ROOT",
            "/tmp/proprio-candidates/openflexure-microscope-server",
        )
    ).expanduser()
    if not root.is_dir():
        raise InstrumentRuntimeUnavailable("PROPRIO_OPENFLEXURE_ROOT is not a simulator checkout")

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    revision = git("rev-parse", "HEAD")
    if revision != OPENFLEXURE_REVISION:
        raise InstrumentRuntimeUnavailable(
            f"OpenFlexure checkout revision mismatch: {revision} != {OPENFLEXURE_REVISION}"
        )
    tree = git("rev-parse", "HEAD^{tree}")
    if tree != OPENFLEXURE_TREE:
        raise InstrumentRuntimeUnavailable(
            f"OpenFlexure checkout tree mismatch: {tree} != {OPENFLEXURE_TREE}"
        )
    if dirty := git("status", "--porcelain=v1", "--untracked-files=all"):
        raise InstrumentRuntimeUnavailable(
            f"OpenFlexure checkout has uncommitted files: {dirty.splitlines()[0]}"
        )


def openflexure_provider() -> InstrumentProvider:
    """Expose the pinned native OpenFlexure simulator and raw-image verifier."""

    from proprio.adaptive_microscopy import (
        ALLOWED_METHODS,
        AdaptiveMicroscopyController,
        AdaptiveOpenFlexureBackend,
    )
    from proprio.openflexure_verifier import verify_openflexure

    provider_id = "proprio.openflexure"
    instrument_id = f"{provider_id}.microscope-autofocus"

    def controller_factory(
        scenario: SimulationScenario,
        parameters: Mapping[str, float],
    ) -> AdaptiveMicroscopyController:
        if scenario is SimulationScenario.UNAVAILABLE:
            raise InstrumentRuntimeUnavailable("OpenFlexure simulator is unavailable")
        _validate_openflexure_checkout()
        unknown = set(parameters) - {
            "start_z",
            "measurement_noise_level",
            "stage_bias_steps",
            "correction_direction",
        }
        if unknown:
            raise ValueError(f"unsupported OpenFlexure condition fields: {sorted(unknown)}")
        defaults = {
            SimulationScenario.NOMINAL: 800,
            SimulationScenario.REPAIR: 1200,
            SimulationScenario.DRIFT: 1800,
        }
        return AdaptiveMicroscopyController(
            AdaptiveOpenFlexureBackend(
                os.environ.get("PROPRIO_OPENFLEXURE_URL", "http://127.0.0.1:5100")
            ),
            start_z=int(parameters.get("start_z", defaults[scenario])),
            measurement_noise_level=float(parameters.get("measurement_noise_level", 2.0)),
            stage_bias_steps=int(parameters.get("stage_bias_steps", 0)),
            correction_direction=int(parameters.get("correction_direction", 1)),
        )

    visible = _condition(
        "changed-visible",
        SimulationScenario.REPAIR,
        start_z=-3300,
        measurement_noise_level=2,
        stage_bias_steps=400,
        correction_direction=1,
    )
    historical = (
        _condition(
            "historical-800",
            SimulationScenario.REPAIR,
            start_z=800,
            measurement_noise_level=2,
        ),
        _condition(
            "historical-1200-bias-250",
            SimulationScenario.REPAIR,
            start_z=1200,
            measurement_noise_level=2,
            stage_bias_steps=250,
            correction_direction=1,
        ),
        visible.model_copy(update={"condition_id": "historical-changed-visible"}),
    )
    acquisition_locked = tuple(
        _condition(
            f"acquisition-locked-{index}",
            SimulationScenario.REPAIR,
            start_z=start_z,
            measurement_noise_level=2,
            stage_bias_steps=bias,
            correction_direction=1,
        )
        for index, (start_z, bias) in enumerate(
            ((-3200, 320), (-1700, 380), (0, 440), (1700, 360), (3200, 420))
        )
    )
    changed = _condition(
        "registered-drift",
        SimulationScenario.DRIFT,
        start_z=1800,
        measurement_noise_level=2,
        stage_bias_steps=400,
        correction_direction=-1,
    )
    evolution_locked = tuple(
        _condition(
            f"evolution-locked-{index}",
            SimulationScenario.DRIFT,
            start_z=start_z,
            measurement_noise_level=2,
            stage_bias_steps=bias,
            correction_direction=-1,
        )
        for index, (start_z, bias) in enumerate(
            ((-3200, 300), (-1600, 460), (100, 350), (1700, 500), (3200, 410))
        )
    )
    instrument = ProviderInstrument(
        instrument_id=instrument_id,
        family="optical_microscopy",
        source_path=_skill_root()
        / "openflexure-adaptive-autofocus"
        / "references"
        / "controller.md",
        upstream_revision=OPENFLEXURE_REVISION,
        allowed_methods=ALLOWED_METHODS,
        controller_factory=controller_factory,
        verifier=verify_openflexure,
        simulator_path=lambda: PACKAGE_ROOT / "data" / "openflexure-simulator.yaml",
        verifier_path=PACKAGE_ROOT / "openflexure_verifier.py",
        acquisition_conditions=(visible,),
        visible_conditions=(visible,),
        locked_conditions=(*historical, *acquisition_locked),
        evolution_conditions=(changed, *evolution_locked),
    )
    return InstrumentProvider(
        api_version="1",
        provider_id=provider_id,
        provider_version="0.5.0",
        instruments={instrument_id: instrument},
        runtime_kind="external-openflexure-server",
    )
