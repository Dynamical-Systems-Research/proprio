"""Hash-bound raw-image verifier entry point for the OpenFlexure provider."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any

from proprio.adaptive_microscopy_verifier import verify_adaptive_microscopy
from proprio.artifacts import source_sha256
from proprio.instrument_types import GateCheck
from proprio.microscopy_verifier import MicroscopyObservation

COMPONENT_SHA256 = {
    "adaptive_microscopy_verifier.py": (
        "16cb6d3a0d2c30086dc583f96b624425b231dbf09804aaf2bc853753a187effd"
    ),
    "microscopy_verifier.py": "10991edd5da367ee23f98be5a41417743108541ee590979d7137ddc1f871a09e",
    "adaptive-microscopy-thresholds.yaml": (
        "f7eac8d104223354d8d3a1d14a19bd71c714b5005a8808b125152bb2aed7a25b"
    ),
}


def _validate_components() -> None:
    module_root = Path(__file__).parent
    observed = {
        "adaptive_microscopy_verifier.py": source_sha256(
            module_root / "adaptive_microscopy_verifier.py"
        ),
        "microscopy_verifier.py": source_sha256(module_root / "microscopy_verifier.py"),
        "adaptive-microscopy-thresholds.yaml": source_sha256(
            Path(str(files("proprio").joinpath("data/adaptive-microscopy-thresholds.yaml")))
        ),
    }
    mismatches = [name for name, digest in observed.items() if COMPONENT_SHA256[name] != digest]
    if mismatches:
        raise RuntimeError(
            f"OpenFlexure verifier component identity changed: {', '.join(mismatches)}"
        )


def verify_openflexure(
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    """Consume private raw frames and retain only compact telemetry and gate evidence."""

    _validate_components()
    raw = telemetry.pop("_raw_evidence", None)
    if not isinstance(raw, dict):
        raise ValueError("OpenFlexure raw verifier evidence is unavailable")
    observation = raw.get("observation")
    frames = raw.get("frames")
    if not isinstance(observation, MicroscopyObservation) or not isinstance(frames, tuple):
        raise TypeError("OpenFlexure raw verifier evidence has an invalid schema")
    return verify_adaptive_microscopy(observation, frames, tuple(trace))
