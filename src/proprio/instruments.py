"""Unified registry for published instrument skill qualification."""

from __future__ import annotations

import hashlib
from typing import Any

from proprio.external_instruments import EXTERNAL_INSTRUMENTS, evaluate_external_skill
from proprio.instrument_types import HardGateResult, SimulationScenario
from proprio.simulated_instruments import SIMULATED_INSTRUMENTS, evaluate_simulated_skill

INSTRUMENTS = {**EXTERNAL_INSTRUMENTS, **SIMULATED_INSTRUMENTS}


def load_instrument_source(instrument_id: str) -> tuple[str, str]:
    definition = INSTRUMENTS[instrument_id]
    text = definition.source_path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


def evaluate_instrument_skill(
    instrument_id: str,
    skill_py: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    condition: dict[str, float] | None = None,
) -> HardGateResult:
    if instrument_id in EXTERNAL_INSTRUMENTS:
        return evaluate_external_skill(
            instrument_id,
            skill_py,
            scenario=scenario,
            condition=condition,
        )
    return evaluate_simulated_skill(
        instrument_id,
        skill_py,
        scenario=scenario,
        condition=condition,
    )


def instrument_kind(instrument_id: str) -> str:
    return "external" if instrument_id in EXTERNAL_INSTRUMENTS else "built-in"


def instrument_summary(instrument_id: str) -> dict[str, Any]:
    definition = INSTRUMENTS[instrument_id]
    return {
        "instrument_id": instrument_id,
        "family": definition.family,
        "kind": instrument_kind(instrument_id),
        "upstream_revision": definition.upstream_revision,
        "controller_methods": sorted(definition.allowed_methods),
    }
