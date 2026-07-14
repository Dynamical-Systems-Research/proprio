"""Unified access to installed simulator-backed providers."""

from __future__ import annotations

import hashlib
from typing import Any

from proprio.instrument_plugins import instrument_registry
from proprio.instrument_types import HardGateResult, SimulationScenario


def instrument_ids(*, kind: str | None = None) -> tuple[str, ...]:
    """Import every installed provider and return its instrument IDs."""

    registry = instrument_registry()
    return tuple(
        instrument_id
        for instrument_id in sorted(registry.bindings)
        if kind is None or registry.kind(instrument_id) == kind
    )


def has_instrument(instrument_id: str) -> bool:
    try:
        return instrument_id in instrument_registry(instrument_id).bindings
    except KeyError:
        return False


def get_instrument_definition(instrument_id: str) -> Any:
    return instrument_registry(instrument_id).definition(instrument_id)


def load_instrument_source(instrument_id: str) -> tuple[str, str]:
    definition = get_instrument_definition(instrument_id)
    text = definition.source_path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


def evaluate_instrument_skill(
    instrument_id: str,
    skill_py: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    condition: dict[str, float] | None = None,
) -> HardGateResult:
    return instrument_registry(instrument_id).evaluate(
        instrument_id,
        skill_py,
        scenario=scenario,
        condition=condition,
    )


def instrument_kind(instrument_id: str) -> str:
    return instrument_registry(instrument_id).kind(instrument_id)


def instrument_provider_identity(instrument_id: str) -> dict[str, str]:
    identity = instrument_registry(instrument_id).provider_identity(instrument_id)
    return {
        "api_version": identity.api_version,
        "provider_id": identity.provider_id,
        "provider_version": identity.provider_version,
        "distribution": identity.distribution,
        "distribution_version": identity.distribution_version,
        "entry_point": identity.entry_point,
    }


def instrument_summary(instrument_id: str) -> dict[str, Any]:
    definition = get_instrument_definition(instrument_id)
    return {
        "instrument_id": instrument_id,
        "family": definition.family,
        "kind": instrument_kind(instrument_id),
        "upstream_revision": definition.upstream_revision,
        "controller_methods": sorted(definition.allowed_methods),
        "provider": instrument_provider_identity(instrument_id),
    }
