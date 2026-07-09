"""Typed records for the self-observation contract."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StatusLabel(StrEnum):
    """Honest status vocabulary shared by operations and checks."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class Provenance(BaseModel):
    """Trace from a result to the implementation and inputs that produced it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    producer: str
    producer_version: str
    input_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    seed: int | None = None
    implementation_sha256: str


class ArtifactRef(BaseModel):
    """Content-addressed artifact reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str
    bytes: int = Field(ge=0)


class RawEventStreamLink(BaseModel):
    """Deterministic link to a nondeterministic raw Bluesky stream.

    The exact raw-stream hash lives in a sidecar so random UIDs and wall-clock
    timestamps cannot perturb the canonical observation record.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    operation_id: str
    correlation_field: Literal["start.proprio_operation_id"] = "start.proprio_operation_id"
    media_type: Literal["application/x-ndjson"] = "application/x-ndjson"


class OperationAction(BaseModel):
    """One declared instrument action and its observed outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str
    action_type: str
    command: dict[str, Any]
    observation: dict[str, Any]
    status: StatusLabel
    reason: str
    started_logical_ns: int = Field(ge=0)
    ended_logical_ns: int = Field(ge=0)
    raw_document_refs: tuple[str, ...] = ()
    provenance: Provenance

    @model_validator(mode="after")
    def validate_time_order(self) -> OperationAction:
        if self.ended_logical_ns < self.started_logical_ns:
            raise ValueError("action end precedes action start")
        if self.status is not StatusLabel.SUCCEEDED and not self.reason.strip():
            raise ValueError("non-success actions require a reason")
        return self


class CheckResult(BaseModel):
    """One verifier postcondition with its complete decision provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str
    status: StatusLabel
    summary: str
    metric_name: str | None = None
    metric_value: float | None = None
    threshold: float | None = None
    comparator: Literal["lt", "le", "gt", "ge", "between", "not_applicable"] = "not_applicable"
    units: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def validate_numeric_evidence(self) -> CheckResult:
        for name, value in (
            ("metric_value", self.metric_value),
            ("threshold", self.threshold),
        ):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.comparator != "not_applicable":
            if self.metric_name is None or self.metric_value is None or self.threshold is None:
                raise ValueError("numeric checks require metric, value, and threshold")
        return self


class ProceduralRecord(BaseModel):
    """Procedural execution record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: StatusLabel
    actions: tuple[OperationAction, ...]
    checks: tuple[CheckResult, ...]


class ValidityRecord(BaseModel):
    """Measurement-validity record, firewalled from scientific judgment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: StatusLabel
    measurement_kind: Literal["calibrant_qc", "unknown_sample"]
    checks: tuple[CheckResult, ...]


class SupportRecord(BaseModel):
    """Declared-support record for the evidence handed to a policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: StatusLabel
    support_contract_id: str
    checks: tuple[CheckResult, ...]
    future_policy_distribution_hook: str


FORBIDDEN_OPERATION_KEYS = frozenset(
    {
        "decision",
        "decision_correct",
        "judgment",
        "judgment_correct",
        "phase_correct",
        "recommended_action",
        "scientific_conclusion",
    }
)


class SelfObservationRecord(BaseModel):
    """Canonical record emitted before any policy judgment is made."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.self_observation.v0.1"] = "proprio.self_observation.v0.1"
    record_id: str = Field(pattern=r"^obs_[0-9a-f]{24}$")
    operation_id: str
    logical_clock_ns: int = Field(ge=0)
    raw_event_stream: RawEventStreamLink
    evidence_artifacts: tuple[ArtifactRef, ...]
    procedural: ProceduralRecord
    validity: ValidityRecord
    support: SupportRecord
    provenance: Provenance

    @model_validator(mode="after")
    def enforce_firewall(self) -> SelfObservationRecord:
        found = _find_forbidden_keys(self.model_dump(mode="json"))
        if found:
            raise ValueError(f"operation-record firewall violation: {sorted(found)}")
        return self


class JudgmentRecord(BaseModel):
    """Policy output stored separately from the operation record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.judgment.v0.1"] = "proprio.judgment.v0.1"
    observation_record_id: str
    policy_id: str
    policy_role: Literal["untrained_baseline", "trained_policy"]
    response: dict[str, Any]
    raw_response: ArtifactRef
    created_at: datetime


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_OPERATION_KEYS:
                found.add(normalized)
            found.update(_find_forbidden_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            found.update(_find_forbidden_keys(child))
    return found


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _normalize(child) for key, child in sorted(value.items())}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize(child) for child in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical records cannot contain non-finite floats")
        return float(format(value, ".12g"))
    return value


def canonical_json(value: Any) -> bytes:
    """Serialize a record deterministically after explicit float normalization."""

    normalized = _normalize(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def content_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def observation_record_id(payload_without_id: Any) -> str:
    return f"obs_{content_sha256(canonical_json(payload_without_id))[:24]}"
