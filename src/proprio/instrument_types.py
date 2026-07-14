"""Typed contracts for simulator-grounded instrument skill qualification."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FeedbackArm(StrEnum):
    TRUTHFUL = "truthful"
    GENERIC = "generic"
    NONE = "none"
    MISMATCHED = "mismatched"


class SimulationScenario(StrEnum):
    NOMINAL = "nominal"
    REPAIR = "repair"
    DRIFT = "drift"
    UNAVAILABLE = "unavailable"


class InstrumentRuntimeUnavailable(RuntimeError):
    """Provider signal for simulator or instrument transport unavailability."""


class CandidatePackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.candidate_package.v0.2"] = "proprio.candidate_package.v0.2"
    instrument_id: str
    skill_md: str
    skill_py: str
    self_judgment: dict[str, Any]
    source_sha256: str
    prompt_sha256: str
    model: str
    raw_response: dict[str, Any]


class GateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    check_id: str
    passed: bool
    critical: bool = True
    evidence: dict[str, Any] = Field(default_factory=dict)


class HardGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.hard_gate.v0.2"] = "proprio.hard_gate.v0.2"
    instrument_id: str
    family: str
    scenario: SimulationScenario
    verdict: Literal["ADMIT", "REJECT", "HOLD"]
    status: Literal["succeeded", "failed", "unavailable"]
    checks: tuple[GateCheck, ...]
    trace: tuple[dict[str, Any], ...]
    telemetry: dict[str, Any]
    result: dict[str, Any] | None
    runtime_error: str | None
    skill_sha256: str
    simulator_sha256: str
    verifier_sha256: str


class RepairSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    diagnosis: str
    evidence_refs: tuple[str, ...]
    skill_md: str
    skill_py: str
    expected_effect: str
    risks: tuple[str, ...]
    self_judgment: dict[str, Any]
