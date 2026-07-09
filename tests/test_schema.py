from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from proprio.schema import (
    ArtifactRef,
    CheckResult,
    OperationAction,
    ProceduralRecord,
    Provenance,
    RawEventStreamLink,
    SelfObservationRecord,
    StatusLabel,
    SupportRecord,
    ValidityRecord,
    canonical_json,
)


def _provenance() -> Provenance:
    return Provenance(
        producer="test",
        producer_version="0",
        implementation_sha256="a" * 64,
    )


def _artifact(path: str) -> ArtifactRef:
    return ArtifactRef(path=path, sha256="b" * 64, media_type="application/json", bytes=1)


def _record() -> SelfObservationRecord:
    action = OperationAction(
        action_id="a1",
        action_type="move",
        command={"target": 1.0},
        observation={"readback": 1.0},
        status=StatusLabel.SUCCEEDED,
        reason="",
        started_logical_ns=0,
        ended_logical_ns=1,
        provenance=_provenance(),
    )
    check = CheckResult(
        check_id="c1",
        status=StatusLabel.SUCCEEDED,
        summary="within tolerance",
        metric_name="error",
        metric_value=0.001,
        threshold=0.01,
        comparator="le",
        units="degree",
        provenance=_provenance(),
    )
    return SelfObservationRecord(
        record_id="obs_" + "c" * 24,
        operation_id="op1",
        logical_clock_ns=10,
        raw_event_stream=RawEventStreamLink(path="raw.jsonl", operation_id="op1"),
        evidence_artifacts=(_artifact("frame.npy"),),
        procedural=ProceduralRecord(
            status=StatusLabel.SUCCEEDED,
            actions=(action,),
            checks=(check,),
        ),
        validity=ValidityRecord(
            status=StatusLabel.SUCCEEDED,
            measurement_kind="calibrant_qc",
            checks=(check,),
        ),
        support=SupportRecord(
            status=StatusLabel.SUCCEEDED,
            support_contract_id="synthetic-xrd-v0.1",
            checks=(check,),
            future_policy_distribution_hook="proprio.distribution.v1",
        ),
        provenance=_provenance(),
    )


def test_canonical_serialization_is_byte_identical() -> None:
    record = _record()
    assert canonical_json(record) == canonical_json(record)


def test_non_success_action_requires_reason() -> None:
    with pytest.raises(ValidationError, match="require a reason"):
        OperationAction(
            action_id="a1",
            action_type="move",
            command={},
            observation={},
            status=StatusLabel.FAILED,
            reason="",
            started_logical_ns=0,
            ended_logical_ns=1,
            provenance=_provenance(),
        )


def test_firewall_rejects_judgment_key_at_any_depth() -> None:
    raw = _record().model_dump(mode="json")
    raw["validity"]["checks"][0]["details"] = {"scientific_conclusion": "phase A"}
    with pytest.raises(ValidationError, match="firewall violation"):
        SelfObservationRecord.model_validate(raw)


def test_repository_path_has_no_trailing_space() -> None:
    assert not Path.cwd().name.endswith(" ")
