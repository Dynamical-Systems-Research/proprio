"""Source loading and independent qualification for the confirmatory panel."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from pathlib import Path

from proprio.confirmatory_instruments import (
    CONFIRMATORY_INSTRUMENTS,
    build_confirmatory_controller,
)
from proprio.confirmatory_verifiers import verify_confirmatory_instrument
from proprio.instrument_qualification import evaluate_controller_skill
from proprio.instrument_types import HardGateResult, SimulationScenario

ROOT = Path(__file__).resolve().parents[2]


def _source_root() -> Path:
    checkout = ROOT / "sources" / "confirmatory"
    return checkout if checkout.is_dir() else Path(__file__).with_name("sources") / "confirmatory"


def confirmatory_source_path(instrument_id: str) -> Path:
    if instrument_id not in CONFIRMATORY_INSTRUMENTS:
        raise KeyError(instrument_id)
    return _source_root() / instrument_id / "source.md"


def load_confirmatory_source(instrument_id: str) -> tuple[str, str]:
    text = confirmatory_source_path(instrument_id).read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


def evaluate_confirmatory_skill(
    instrument_id: str,
    source: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    condition: Mapping[str, float] | None = None,
) -> HardGateResult:
    definition = CONFIRMATORY_INSTRUMENTS[instrument_id]
    controller = build_confirmatory_controller(instrument_id, scenario)
    condition_values = dict(condition or {})
    unknown = set(condition_values) - {definition.condition_field}
    if unknown:
        raise ValueError(f"unsupported condition fields for {instrument_id}: {sorted(unknown)}")
    for field, value in condition_values.items():
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"condition {field} must be positive and finite")
        setattr(controller, field, numeric)
    return evaluate_controller_skill(
        instrument_id,
        definition.family,
        source,
        scenario=scenario,
        allowed_methods=definition.allowed_methods,
        controller=controller,
        verifier=verify_confirmatory_instrument,
        simulator_path=Path(__file__).with_name("confirmatory_instruments.py"),
        verifier_path=Path(__file__).with_name("confirmatory_verifiers.py"),
        condition_evidence=condition_values,
    )


CONFIRMATORY_FAMILIES = {
    instrument_id: definition.family
    for instrument_id, definition in CONFIRMATORY_INSTRUMENTS.items()
}
