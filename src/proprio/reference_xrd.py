"""Composed XRD reference operation and canonical observation record."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from proprio.artifacts import source_sha256, write_canonical_json, write_npy
from proprio.policy import OpenAICompatibleClient, persist_judgment
from proprio.procedural import ProceduralFault, run_procedural
from proprio.schema import (
    Provenance,
    RawEventStreamLink,
    SelfObservationRecord,
    StatusLabel,
    observation_record_id,
)
from proprio.support import SubstrateSupportDetector
from proprio.xrd_generator import generate_calibrant_frame
from proprio.xrd_types import ValidityFault, load_preregistration
from proprio.xrd_verifier import verify_calibrant_frame


def _provenance(*, frame_sha256: str, seed: int) -> Provenance:
    return Provenance(
        producer="proprio.reference_xrd",
        producer_version="0.1.0",
        input_refs=(f"frame_sha256:{frame_sha256}",),
        seed=seed,
        implementation_sha256=source_sha256(Path(__file__)),
    )


def run_reference_xrd(
    *,
    output_dir: Path,
    validity_fault: ValidityFault = ValidityFault.VALID,
    live_judge: bool = False,
) -> dict[str, Any]:
    """Run the complete observability chain and optionally call a live baseline policy."""

    operation_id = f"proprio-xrd-reference-v0.1-{validity_fault.value}"
    raw_path = output_dir / "raw" / "bluesky.jsonl"
    procedural = run_procedural(
        fault=ProceduralFault.NONE,
        raw_output=raw_path,
        operation_id=operation_id,
    )
    prereg = load_preregistration()
    seed = int(prereg["battery"]["seed"])
    case = generate_calibrant_frame(fault=validity_fault, seed=seed)
    frame_ref_actual = write_npy(output_dir / "evidence" / "calibrant-frame.npy", case.frame)
    frame_ref = frame_ref_actual.model_copy(update={"path": "evidence/calibrant-frame.npy"})
    validity = verify_calibrant_frame(case).record
    support = SubstrateSupportDetector().evaluate(case, calibrant=case.truth.calibrant)

    payload = {
        "operation_id": operation_id,
        "logical_clock_ns": 1_000_000,
        "raw_event_stream": RawEventStreamLink(
            path="raw/bluesky.jsonl",
            operation_id=operation_id,
        ),
        "evidence_artifacts": (frame_ref,),
        "procedural": procedural.record,
        "validity": validity,
        "support": support,
        "provenance": _provenance(frame_sha256=frame_ref.sha256, seed=seed),
    }
    record_id = observation_record_id(payload)
    record = SelfObservationRecord(record_id=record_id, **payload)
    canonical_ref = write_canonical_json(output_dir / "self-observation.json", record)

    raw_documents = procedural.raw_documents
    start = next(row["doc"] for row in raw_documents if row["name"] == "start")
    stop = next(row["doc"] for row in raw_documents if row["name"] == "stop")
    raw_sidecar = {
        "schema_version": "proprio.raw_stream_binding.v0.1",
        "operation_id": operation_id,
        "canonical_record_id": record.record_id,
        "canonical_record_sha256": canonical_ref.sha256,
        "raw_stream_sha256": procedural.raw_event_stream.sha256,
        "raw_start_uid": start["uid"],
        "raw_stop_uid": stop["uid"],
        "correlation_verified": start["proprio_operation_id"] == operation_id,
    }
    write_canonical_json(output_dir / "raw" / "binding.json", raw_sidecar)

    judgment = None
    if live_judge:
        client = OpenAICompatibleClient()
        try:
            response = client.judge(record)
            judgment = persist_judgment(
                record=record,
                response=response,
                output_dir=output_dir / "judgment",
                model=client.model,
            )
        finally:
            client.close()
    summary = {
        "schema_version": "proprio.reference_xrd_run.v0.1",
        "operation_id": operation_id,
        "record_id": record.record_id,
        "canonical_record_sha256": canonical_ref.sha256,
        "raw_stream_sha256": procedural.raw_event_stream.sha256,
        "observability": {
            "procedural": procedural.record.status.value,
            "validity": validity.status.value,
            "support": support.status.value,
        },
        "all_observations_passed": all(
            component.status is StatusLabel.SUCCEEDED
            for component in (procedural.record, validity, support)
        ),
        "judgment": judgment.model_dump(mode="json") if judgment else None,
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def run_composition_battery(output_dir: Path) -> dict[str, Any]:
    valid = run_reference_xrd(output_dir=output_dir / "valid")
    invalid = run_reference_xrd(
        output_dir=output_dir / "procedural-success-invalid",
        validity_fault=ValidityFault.SATURATION,
    )
    summary = {
        "schema_version": "proprio.composition_battery.v0.1",
        "valid_path_passed": valid["all_observations_passed"],
        "procedural_success_invalid_caught": (
            invalid["observability"]["procedural"] == StatusLabel.SUCCEEDED
            and invalid["observability"]["validity"] == StatusLabel.FAILED
        ),
        "invalid_path_observability": invalid["observability"],
        "firewall_tested_in_unit_suite": True,
        "verdict": "PASS"
        if valid["all_observations_passed"]
        and invalid["observability"]["procedural"] == StatusLabel.SUCCEEDED
        and invalid["observability"]["validity"] == StatusLabel.FAILED
        else "FAIL",
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
