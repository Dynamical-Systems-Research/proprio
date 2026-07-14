"""Lazy Python entry-point providers for simulator-backed instruments."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache, lru_cache
from importlib import metadata
from pathlib import Path
from types import MappingProxyType
from typing import Any

from proprio.artifacts import source_sha256
from proprio.instrument_qualification import evaluate_controller_skill
from proprio.instrument_types import GateCheck, HardGateResult, SimulationScenario
from proprio.skill_search import DebugCondition

ENTRY_POINT_GROUP = "proprio.instrument_providers"
PROVIDER_API_VERSION = "1"

ControllerFactory = Callable[[SimulationScenario, Mapping[str, float]], Any]
Verifier = Callable[
    [Sequence[dict[str, Any]], dict[str, Any]],
    tuple[GateCheck, ...],
]


@dataclass(frozen=True)
class ProviderInstrument:
    """One namespaced controller, simulator, and verifier contract."""

    instrument_id: str
    family: str
    source_path: Path
    upstream_revision: str
    allowed_methods: frozenset[str]
    controller_factory: ControllerFactory
    verifier: Verifier
    simulator_path: Callable[[], Path]
    verifier_path: Path
    acquisition_conditions: tuple[DebugCondition, ...]
    visible_conditions: tuple[DebugCondition, ...]
    locked_conditions: tuple[DebugCondition, ...]
    evolution_conditions: tuple[DebugCondition, ...]


@dataclass(frozen=True)
class InstrumentProvider:
    """Versioned provider exported through ``proprio.instrument_providers``."""

    api_version: str
    provider_id: str
    provider_version: str
    instruments: Mapping[str, ProviderInstrument]
    runtime_kind: str


@dataclass(frozen=True)
class ProviderMetadata:
    """Installed provider metadata read without importing provider code."""

    provider_id: str
    entry_point: str
    distribution: str
    distribution_version: str
    entry_point_object: metadata.EntryPoint


@dataclass(frozen=True)
class ProviderIdentity:
    api_version: str
    provider_id: str
    provider_version: str
    distribution: str
    distribution_version: str
    entry_point: str


@dataclass(frozen=True)
class LoadedProvider:
    provider: InstrumentProvider
    identity: ProviderIdentity


@dataclass(frozen=True)
class InstrumentBinding:
    definition: ProviderInstrument
    provider: LoadedProvider


@dataclass(frozen=True)
class InstrumentRegistry:
    providers: tuple[LoadedProvider, ...]
    bindings: Mapping[str, InstrumentBinding]

    @property
    def instruments(self) -> Mapping[str, ProviderInstrument]:
        return MappingProxyType(
            {instrument_id: binding.definition for instrument_id, binding in self.bindings.items()}
        )

    def definition(self, instrument_id: str) -> ProviderInstrument:
        return self.bindings[instrument_id].definition

    def kind(self, instrument_id: str) -> str:
        return self.bindings[instrument_id].provider.provider.runtime_kind

    def provider_identity(self, instrument_id: str) -> ProviderIdentity:
        return self.bindings[instrument_id].provider.identity

    def evaluate(
        self,
        instrument_id: str,
        skill_py: str,
        *,
        scenario: SimulationScenario = SimulationScenario.NOMINAL,
        condition: Mapping[str, float] | None = None,
    ) -> HardGateResult:
        binding = self.bindings[instrument_id]
        definition = binding.definition
        condition_values = dict(condition or {})
        if not definition.verifier_path.is_file():
            return _hold_result(
                definition,
                skill_py,
                scenario,
                FileNotFoundError(f"verifier source is missing: {definition.verifier_path}"),
            )
        try:
            simulator_path = definition.simulator_path()
            controller = definition.controller_factory(scenario, condition_values)
        except Exception as exc:
            return _hold_result(definition, skill_py, scenario, exc)

        evaluation_error: Exception | None = None
        close_error: Exception | None = None
        try:
            gate = evaluate_controller_skill(
                instrument_id,
                definition.family,
                skill_py,
                scenario=scenario,
                allowed_methods=definition.allowed_methods,
                controller=controller,
                verifier=lambda _instrument_id, _family, trace, telemetry: definition.verifier(
                    trace, telemetry
                ),
                simulator_path=simulator_path,
                verifier_path=definition.verifier_path,
                condition_evidence=condition_values,
            )
        except Exception as exc:
            evaluation_error = exc
        finally:
            close = getattr(controller, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    close_error = exc
        if close_error is not None:
            return _hold_result(definition, skill_py, scenario, close_error)
        if evaluation_error is not None:
            return _hold_result(definition, skill_py, scenario, evaluation_error)
        error = _evidence_error(gate, definition, skill_py, scenario, simulator_path)
        return _hold_result(definition, skill_py, scenario, RuntimeError(error)) if error else gate


def _hold_result(
    definition: ProviderInstrument,
    skill_py: str,
    scenario: SimulationScenario,
    error: Exception,
) -> HardGateResult:
    simulator_hash = "unavailable"
    try:
        simulator_hash = source_sha256(definition.simulator_path())
    except Exception:
        pass
    message = f"{type(error).__name__}: {error}"
    verifier_hash = "unavailable"
    try:
        verifier_hash = source_sha256(definition.verifier_path)
    except Exception:
        pass
    return HardGateResult(
        instrument_id=definition.instrument_id,
        family=definition.family,
        scenario=scenario,
        verdict="HOLD",
        status="unavailable",
        checks=(
            GateCheck(
                check_id="provider-runtime",
                passed=False,
                evidence={"error": message},
            ),
        ),
        trace=(),
        telemetry={},
        result=None,
        runtime_error=message,
        skill_sha256=hashlib.sha256(skill_py.encode()).hexdigest(),
        simulator_sha256=simulator_hash,
        verifier_sha256=verifier_hash,
    )


def _evidence_error(
    gate: HardGateResult,
    definition: ProviderInstrument,
    skill_py: str,
    scenario: SimulationScenario,
    simulator_path: Path,
) -> str | None:
    expected = {
        "instrument_id": definition.instrument_id,
        "family": definition.family,
        "scenario": scenario,
        "skill_sha256": hashlib.sha256(skill_py.encode()).hexdigest(),
        "simulator_sha256": source_sha256(simulator_path),
        "verifier_sha256": source_sha256(definition.verifier_path),
    }
    observed = {key: getattr(gate, key) for key in expected}
    mismatches = [key for key in expected if observed[key] != expected[key]]
    return f"provider evidence identity mismatch: {', '.join(mismatches)}" if mismatches else None


def _distribution_identity(entry_point: metadata.EntryPoint) -> tuple[str, str]:
    distribution = getattr(entry_point, "dist", None)
    if distribution is None:
        raise ValueError(f"entry point has no distribution identity: {entry_point.name}")
    name = distribution.metadata.get("Name")
    if not name or not distribution.version:
        raise ValueError(f"entry point has incomplete distribution identity: {entry_point.name}")
    return str(name), str(distribution.version)


def discover_provider_metadata(
    entry_points: Iterable[metadata.EntryPoint] | None = None,
) -> tuple[ProviderMetadata, ...]:
    """Enumerate installed providers without importing their modules."""

    candidates = (
        metadata.entry_points(group=ENTRY_POINT_GROUP) if entry_points is None else entry_points
    )
    discovered = []
    for entry_point in candidates:
        distribution, version = _distribution_identity(entry_point)
        discovered.append(
            ProviderMetadata(
                provider_id=entry_point.name,
                entry_point=entry_point.value,
                distribution=distribution,
                distribution_version=version,
                entry_point_object=entry_point,
            )
        )
    ordered = tuple(sorted(discovered, key=lambda item: (item.provider_id, item.entry_point)))
    if len({item.provider_id for item in ordered}) != len(ordered):
        raise ValueError("duplicate installed provider id")
    return ordered


def _validate_provider(provider: InstrumentProvider, installed: ProviderMetadata) -> None:
    if provider.api_version != PROVIDER_API_VERSION:
        raise ValueError(
            f"incompatible provider API for {provider.provider_id}: {provider.api_version}"
        )
    if provider.provider_id != installed.provider_id:
        raise ValueError(
            f"entry-point/provider id mismatch: {installed.provider_id} != {provider.provider_id}"
        )
    if provider.provider_version != installed.distribution_version:
        raise ValueError(
            f"provider/distribution version mismatch for {provider.provider_id}: "
            f"{provider.provider_version} != {installed.distribution_version}"
        )
    if not provider.runtime_kind or not provider.instruments:
        raise ValueError(f"provider is incomplete: {provider.provider_id}")
    for instrument_id, definition in provider.instruments.items():
        if instrument_id != definition.instrument_id:
            raise ValueError(f"instrument key does not match definition: {instrument_id}")
        if not instrument_id.startswith(f"{provider.provider_id}."):
            raise ValueError(f"instrument id is not provider-namespaced: {instrument_id}")
        if not definition.family or not definition.allowed_methods:
            raise ValueError(f"instrument definition is incomplete: {instrument_id}")
        if not definition.source_path.is_file():
            raise ValueError(f"instrument source does not exist: {instrument_id}")
        if not callable(definition.controller_factory) or not callable(definition.verifier):
            raise ValueError(f"instrument runtime is incomplete: {instrument_id}")
        if any(
            not getattr(definition, field)
            for field in ("acquisition_conditions", "visible_conditions", "locked_conditions")
        ):
            raise ValueError(f"instrument conditions are incomplete: {instrument_id}")


def _load_provider(installed: ProviderMetadata) -> LoadedProvider:
    loaded = installed.entry_point_object.load()
    provider = loaded if isinstance(loaded, InstrumentProvider) else loaded()
    if not isinstance(provider, InstrumentProvider):
        raise TypeError(f"entry point did not return InstrumentProvider: {installed.provider_id}")
    _validate_provider(provider, installed)
    return LoadedProvider(
        provider=provider,
        identity=ProviderIdentity(
            api_version=provider.api_version,
            provider_id=provider.provider_id,
            provider_version=provider.provider_version,
            distribution=installed.distribution,
            distribution_version=installed.distribution_version,
            entry_point=installed.entry_point,
        ),
    )


def build_instrument_registry(providers: Iterable[LoadedProvider]) -> InstrumentRegistry:
    ordered = tuple(sorted(providers, key=lambda item: item.provider.provider_id))
    if not ordered:
        raise RuntimeError("no instrument providers selected")
    bindings: dict[str, InstrumentBinding] = {}
    for loaded in ordered:
        for instrument_id, definition in sorted(loaded.provider.instruments.items()):
            if instrument_id in bindings:
                raise ValueError(f"duplicate instrument id: {instrument_id}")
            bindings[instrument_id] = InstrumentBinding(definition, loaded)
    return InstrumentRegistry(ordered, MappingProxyType(bindings))


@lru_cache(maxsize=1)
def _installed_metadata() -> tuple[ProviderMetadata, ...]:
    return discover_provider_metadata()


def _provider_for_instrument(instrument_id: str) -> ProviderMetadata:
    matches = [
        item for item in _installed_metadata() if instrument_id.startswith(f"{item.provider_id}.")
    ]
    if not matches:
        raise KeyError(instrument_id)
    if len(matches) != 1:
        raise ValueError(f"ambiguous provider namespace for instrument: {instrument_id}")
    return matches[0]


@cache
def instrument_registry(instrument_id: str | None = None) -> InstrumentRegistry:
    """Load only the provider selected by a namespaced instrument ID.

    Passing no ID is an explicit request to enumerate and load every provider.
    """

    selected = (
        _installed_metadata()
        if instrument_id is None
        else (_provider_for_instrument(instrument_id),)
    )
    return build_instrument_registry(_load_provider(item) for item in selected)


def refresh_instrument_providers() -> None:
    _installed_metadata.cache_clear()
    instrument_registry.cache_clear()
