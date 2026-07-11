"""Freeze and verify the v0.3 external-simulator acquisition method."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from proprio.artifacts import source_sha256, write_canonical_json
from proprio.generalization_instruments import (
    GENERALIZATION_INSTRUMENTS,
    external_simulator_identity,
)
from proprio.schema import canonical_json

ROOT = Path(__file__).resolve().parents[2]
METHOD_INPUTS = (
    "pyproject.toml",
    "uv.lock",
    "src/proprio/policy.py",
    "src/proprio/instrument_agent.py",
    "src/proprio/instrument_qualification.py",
    "src/proprio/adaptive_agent.py",
    "src/proprio/adaptive_search.py",
    "src/proprio/generalization_instruments.py",
    "src/proprio/generalization_method.py",
    "src/proprio/generalization_study.py",
    "src/proprio/data/generalization-v0.3-method.yaml",
    "sources/generalization/north-pipette-calibration/source.md",
    "sources/generalization/helao-gamry-cv/source.md",
    "sources/generalization/clslab-light-spectrometer/source.md",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected an object: {path}")
    return payload


def freeze_generalization_method(
    output_dir: Path,
    *,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    evidence_root = evidence_root or ROOT / "artifacts/evidence/generalization-v0.3"
    evidence: dict[str, Any] = {}
    for instrument_id in GENERALIZATION_INSTRUMENTS:
        preflight_path = evidence_root / "eligibility" / instrument_id / "preflight.json"
        metrology_path = evidence_root / "metrology" / instrument_id / "summary.json"
        preflight = _read_json(preflight_path)
        metrology = _read_json(metrology_path)
        if preflight.get("verdict") != "PASS":
            raise RuntimeError(f"eligibility preflight did not pass: {instrument_id}")
        if metrology.get("verdict") != "PASS":
            raise RuntimeError(f"verifier metrology did not pass: {instrument_id}")
        evidence[instrument_id] = {
            "preflight": {
                "path": str(preflight_path.relative_to(ROOT)),
                "sha256": source_sha256(preflight_path),
            },
            "metrology": {
                "path": str(metrology_path.relative_to(ROOT)),
                "sha256": source_sha256(metrology_path),
                "valid_false_reject_rate": metrology["valid"]["false_reject_rate"],
                "total_false_admits": metrology["total_false_admits"],
            },
        }
    registry_path = evidence_root / "eligibility" / "registry.json"
    inspection_path = evidence_root / "manual-inspection.md"
    provider_path = evidence_root / "provider-parity" / "provider-route.json"
    registry = _read_json(registry_path)
    if registry.get("selected_count") != 3 or registry.get("model_calls_during_screening") != 0:
        raise RuntimeError("eligibility registry does not describe a pre-model three-family panel")
    if not inspection_path.is_file():
        raise RuntimeError("manual evidence inspection is missing")
    provider = _read_json(provider_path)
    if (
        provider.get("verdict") != "PASS"
        or provider.get("provider_order") != ["DeepInfra", "GMICloud"]
        or provider.get("provider_allowlist") != ["DeepInfra", "GMICloud"]
        or any(
            row.get("resolved_model") != "deepseek/deepseek-v4-flash-20260423"
            for row in provider.get("providers", {}).values()
        )
    ):
        raise RuntimeError("binding provider parity did not pass")
    panel_evidence = {
        "eligibility_registry": {
            "path": str(registry_path.relative_to(ROOT)),
            "sha256": source_sha256(registry_path),
        },
        "manual_inspection": {
            "path": str(inspection_path.relative_to(ROOT)),
            "sha256": source_sha256(inspection_path),
        },
        "provider_parity": {
            "path": str(provider_path.relative_to(ROOT)),
            "sha256": source_sha256(provider_path),
        },
    }
    inputs = {relative: source_sha256(ROOT / relative) for relative in METHOD_INPUTS}
    external_simulators = {
        instrument_id: external_simulator_identity(instrument_id)
        for instrument_id in GENERALIZATION_INSTRUMENTS
    }
    if any(row["verdict"] != "PASS" for row in external_simulators.values()):
        raise RuntimeError("an external simulator does not match its pinned revision")
    payload = {
        "schema_version": "proprio.generalization_method_freeze.v0.3",
        "status": "FROZEN_BEFORE_BINDING_PANEL",
        "claim_boundary": (
            "Simulation-only pre-deployment qualification across eligible external simulator "
            "families; real-hardware qualification remains separate."
        ),
        "selected_instruments": sorted(GENERALIZATION_INSTRUMENTS),
        "inputs": inputs,
        "external_simulators": external_simulators,
        "evidence": evidence,
        "panel_evidence": panel_evidence,
    }
    payload["method_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_canonical_json(output_dir / "manifest.json", payload)
    return payload


def verify_generalization_method(manifest_path: Path) -> dict[str, Any]:
    payload = _read_json(manifest_path)
    expected = payload.pop("method_sha256", None)
    observed = hashlib.sha256(canonical_json(payload)).hexdigest()
    input_matches = {
        relative: (ROOT / relative).is_file()
        and source_sha256(ROOT / relative) == expected_sha
        for relative, expected_sha in payload.get("inputs", {}).items()
    }
    external_matches = {}
    for instrument_id, expected_identity in payload.get("external_simulators", {}).items():
        try:
            external_matches[instrument_id] = (
                external_simulator_identity(instrument_id) == expected_identity
            )
        except Exception:
            external_matches[instrument_id] = False
    passed = (
        expected == observed
        and payload.get("status") == "FROZEN_BEFORE_BINDING_PANEL"
        and bool(input_matches)
        and all(input_matches.values())
        and bool(external_matches)
        and all(external_matches.values())
    )
    return {
        "schema_version": "proprio.generalization_method_verification.v0.3",
        "method_sha256": expected,
        "digest_matches": expected == observed,
        "input_matches": input_matches,
        "external_simulator_matches": external_matches,
        "verdict": "PASS" if passed else "FAIL",
    }
