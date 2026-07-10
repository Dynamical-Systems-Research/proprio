"""Fail-closed aggregation for preregistered held-out simulator preflights."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import source_sha256, write_canonical_json


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"preflight evidence must be an object: {path}")
    return value


def _identity(payload: dict[str, Any]) -> tuple[str, str, str]:
    schema = payload.get("schema_version")
    if schema == "proprio.octoprint_preflight_evidence.v1":
        preregistration = payload["preregistration"]
        return (
            preregistration["family_id"],
            preregistration["instrument_id"],
            payload["scope"]["observed_revision"],
        )
    if schema == "proprio.pymodaq_preflight_evidence.v1":
        scope = payload["inspection_scope"]
        return "spectral_measurement", "pymodaq-mock-spectrometer", scope["revision"]
    if schema == "proprio.heldout_fixture_preflight_evidence.v0.2":
        return (
            payload["family_id"],
            payload["instrument_id"],
            payload["provenance"]["sinstruments"]["revision"],
        )
    raise ValueError(f"unsupported held-out preflight schema: {schema}")


def _overall(payload: dict[str, Any]) -> tuple[str, str, bool]:
    schema = payload["schema_version"]
    if schema == "proprio.octoprint_preflight_evidence.v1":
        overall = payload["overall"]
        return overall["verdict"], overall["honest_status"], overall["no_model_call"]
    if schema == "proprio.pymodaq_preflight_evidence.v1":
        overall = payload["overall"]
        return overall["status"], overall["disposition"], payload["no_model_call"]
    return payload["overall_result"], payload["promotion_status"], payload["no_model_call"]


def _results(payload: dict[str, Any]) -> list[str]:
    schema = payload["schema_version"]
    if schema == "proprio.octoprint_preflight_evidence.v1":
        contract = payload["contract_evaluation"]
        values = [
            *(row["result"] for row in contract["acquisition_requirements"]),
            *(row["result"] for row in contract["physical_requirements"]),
            *(row["result"] for row in contract["failure_class_capabilities"]),
            contract["repair_fault"]["result"],
            contract["drift_event"]["result"],
        ]
        return list(values)
    if schema == "proprio.pymodaq_preflight_evidence.v1":
        groups = payload["preregistered_requirement_results"].values()
        return [row["status"] for group in groups for row in group]
    return [
        *(
            row["result"]
            for row in payload["acquisition_contract_results"]
            + payload["physical_contract_results"]
            + payload["failure_class_results"]
            + payload["repair_and_drift_results"]
        )
    ]


def import_heldout_preflight_evidence(
    output_dir: Path,
    *,
    preregistration_path: Path,
    evidence_paths: tuple[Path, ...],
) -> dict[str, Any]:
    """Validate and canonically retain one raw preflight record per registered family."""

    preregistration = yaml.safe_load(preregistration_path.read_text(encoding="utf-8"))
    registered = {
        row["instrument_id"]: {
            "family_id": row["family_id"],
            "revision": row["upstream"]["revision"],
        }
        for row in preregistration["families"]
    }
    if len(evidence_paths) != len(registered):
        raise RuntimeError("preflight requires exactly one record per registered instrument")

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for evidence_path in evidence_paths:
        payload = _read_json(evidence_path)
        family_id, instrument_id, revision = _identity(payload)
        if instrument_id not in registered:
            raise RuntimeError(f"unregistered preflight instrument: {instrument_id}")
        expected = registered[instrument_id]
        if family_id != expected["family_id"] or revision != expected["revision"]:
            raise RuntimeError(f"preflight identity mismatch for {instrument_id}")
        verdict, honest_status, no_model_call = _overall(payload)
        if verdict != "FAIL" or honest_status != "HOLD" or no_model_call is not True:
            raise RuntimeError(f"preflight did not fail closed for {instrument_id}")
        statuses = _results(payload)
        if not statuses or not any(status == "FAIL" for status in statuses):
            raise RuntimeError(f"preflight omitted a binding failure for {instrument_id}")
        raw_path = raw_dir / f"{instrument_id}.json"
        write_canonical_json(raw_path, payload)
        rows.append(
            {
                "family_id": family_id,
                "instrument_id": instrument_id,
                "upstream_revision": revision,
                "fixture_preflight": verdict,
                "honest_status": honest_status,
                "no_model_call": no_model_call,
                "requirement_results": len(statuses),
                "passed_or_partially_supported": sum(
                    status.startswith("PASS") or status == "PARTIAL" for status in statuses
                ),
                "failed": sum(status == "FAIL" for status in statuses),
                "held": sum(status == "HOLD" for status in statuses),
                "raw_path": str(raw_path),
                "raw_sha256": source_sha256(raw_path),
            }
        )
    rows.sort(key=lambda row: row["instrument_id"])
    if {row["instrument_id"] for row in rows} != set(registered):
        raise RuntimeError("preflight evidence did not cover the complete registered panel")
    summary = {
        "schema_version": "proprio.heldout_fixture_preflight_summary.v0.2",
        "method_sha256": preregistration["frozen_method"]["method_sha256"],
        "registered_families": len(registered),
        "families_passing_preflight": 0,
        "families_failing_preflight": len(rows),
        "model_calls": 0,
        "model_generation_performed": False,
        "family_replacement_performed": False,
        "aggregate_rescue_performed": False,
        "rows": rows,
        "verdict": "FAIL",
        "decision": (
            "HOLD every family before model invocation because its pinned upstream simulator "
            "cannot execute the complete preregistered physical and drift contract."
        ),
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
