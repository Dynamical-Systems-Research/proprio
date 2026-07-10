"""Hash-bind the adaptive method and preserve the status of every evidence gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from proprio.adaptive_agent import ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT
from proprio.artifacts import source_sha256, write_canonical_json
from proprio.schema import canonical_json

ROOT = Path(__file__).resolve().parents[2]
METHOD_INPUTS = (
    "src/proprio/instrument_qualification.py",
    "src/proprio/adaptive_agent.py",
    "src/proprio/adaptive_search.py",
    "src/proprio/adaptive_validation.py",
    "src/proprio/adaptive_microscopy.py",
    "src/proprio/adaptive_microscopy_verifier.py",
    "src/proprio/adaptive_microscopy_study.py",
    "src/proprio/data/adaptive-method-preregistration.yaml",
    "src/proprio/data/adaptive-method-freeze-decision.yaml",
    "src/proprio/data/adaptive-microscopy-thresholds.yaml",
)
REQUIRED_EVIDENCE = {
    "reset_idempotence": "adaptive-microscopy-reset/summary.json",
    "curve_metrology": "adaptive-microscopy-curve-metrology/summary.json",
    "verifier_metrology": "adaptive-microscopy-metrology/summary.json",
    "uncertainty_metrology": "adaptive-microscopy-uncertainty/summary.json",
    "adaptive_search": "adaptive-microscopy-development-v2/summary.json",
    "locked_qualification": "adaptive-microscopy-locked/summary.json",
}
CAUSAL_DEVELOPMENT_EVIDENCE = "adaptive-microscopy-causal-development/summary.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence must be a JSON object: {path}")
    return payload


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _evidence_gate(generated_root: Path) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for name, relative in REQUIRED_EVIDENCE.items():
        path = generated_root / relative
        if not path.is_file():
            raise RuntimeError(f"method freeze evidence is missing: {path}")
        payload = _read_json(path)
        if payload.get("verdict") != "PASS":
            raise RuntimeError(f"method freeze evidence did not pass: {path}")
        evidence[name] = {
            "path": _display_path(path),
            "sha256": source_sha256(path),
            "schema_version": payload.get("schema_version"),
        }
    causal_path = generated_root / CAUSAL_DEVELOPMENT_EVIDENCE
    causal = _read_json(causal_path)
    if (
        causal.get("schema_version") != "proprio.causal_development_lock.v0.2"
        or causal.get("status") != "EXPLORATORY_LOCKED"
        or causal.get("confirmatory_status") != "NOT_ESTABLISHED"
        or causal.get("completed_trials") != 4
        or causal.get("analysis", {}).get("verdict") != "INCOMPLETE"
    ):
        raise RuntimeError(
            "causal development evidence must be an honest four-trial exploratory lock"
        )
    evidence["causal_development"] = {
        "path": _display_path(causal_path),
        "sha256": source_sha256(causal_path),
        "schema_version": causal.get("schema_version"),
        "status": causal.get("status"),
        "confirmatory_status": causal.get("confirmatory_status"),
        "completed_trials": causal.get("completed_trials"),
        "registered_trials": causal.get("registered_trials"),
    }
    search_path = generated_root / "adaptive-microscopy-development-v2/search.json"
    search = _read_json(search_path)
    if search.get("verdict") != "CANDIDATE":
        raise RuntimeError("adaptive search must select a candidate")
    selected = search.get("selected") or {}
    selected_skill = selected.get("skill_py")
    if not isinstance(selected_skill, str):
        raise RuntimeError("adaptive search omitted the selected skill")
    selected_sha = hashlib.sha256(selected_skill.encode()).hexdigest()
    selected_entries = [
        entry
        for entry in search.get("entries", [])
        if entry.get("suite", {}).get("candidate_sha256") == selected_sha
    ]
    if len(selected_entries) != 1:
        raise RuntimeError("adaptive search selection does not identify exactly one entry")
    selected_entry = selected_entries[0]
    if (
        selected_entry.get("suite", {}).get("verdict") != "ADMIT"
        or selected_entry.get("promotion_eligible") is not True
        or selected_entry.get("promotion_blockers")
    ):
        raise RuntimeError("adaptive search selected an ineligible or blocked entry")
    qualified_repairs = [
        repair
        for repair in search.get("repairs", [])
        if repair.get("record", {}).get("agent_status") == "CANDIDATE"
        and repair.get("record", {}).get("initial_suite", {}).get("verdict") == "REJECT"
        and repair.get("record", {}).get("final_suite", {}).get("verdict") == "ADMIT"
    ]
    evidence["adaptive_search_record"] = {
        "path": _display_path(search_path),
        "sha256": source_sha256(search_path),
        "schema_version": search.get("schema_version"),
        "selection_mode": "repaired" if qualified_repairs else "direct-admit",
    }
    return evidence


def freeze_adaptive_method(
    output_dir: Path,
    *,
    generated_root: Path | None = None,
) -> dict[str, Any]:
    generated_root = generated_root or ROOT / "artifacts" / "generated"
    evidence = _evidence_gate(generated_root)
    inputs = {
        relative: source_sha256(ROOT / relative)
        for relative in METHOD_INPUTS
        if (ROOT / relative).is_file()
    }
    if set(inputs) != set(METHOD_INPUTS):
        missing = sorted(set(METHOD_INPUTS) - set(inputs))
        raise RuntimeError(f"method inputs are missing: {missing}")
    payload = {
        "schema_version": "proprio.adaptive_method_freeze.v0.2",
        "status": "FROZEN",
        "evidence_status": "DEVELOPMENT_COMPLETE_CAUSAL_CONFIRMATORY_NOT_ESTABLISHED",
        "claim_boundary": (
            "Simulation-validated pre-deployment qualification; real-hardware qualification "
            "remains a separate required gate. The four-trial causal panel is exploratory and "
            "does not establish the preregistered 30-trial claim."
        ),
        "inputs": inputs,
        "adaptive_prompt_sha256": hashlib.sha256(
            ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT.encode()
        ).hexdigest(),
        "evidence": evidence,
    }
    payload["method_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_canonical_json(output_dir / "manifest.json", payload)
    return payload


def verify_adaptive_method_freeze(manifest_path: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    expected_digest = manifest.pop("method_sha256", None)
    observed_digest = hashlib.sha256(canonical_json(manifest)).hexdigest()
    input_matches = {
        relative: (ROOT / relative).is_file()
        and source_sha256(ROOT / relative) == expected_sha
        for relative, expected_sha in manifest.get("inputs", {}).items()
    }
    prompt_matches = manifest.get("adaptive_prompt_sha256") == hashlib.sha256(
        ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT.encode()
    ).hexdigest()
    passed = (
        expected_digest == observed_digest
        and bool(input_matches)
        and all(input_matches.values())
        and prompt_matches
        and manifest.get("status") == "FROZEN"
    )
    return {
        "schema_version": "proprio.adaptive_method_freeze_verification.v0.2",
        "manifest": str(manifest_path),
        "method_sha256": expected_digest,
        "digest_matches": expected_digest == observed_digest,
        "input_matches": input_matches,
        "prompt_matches": prompt_matches,
        "verdict": "PASS" if passed else "FAIL",
    }
