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


class CandidateSelectionSeal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.candidate_selection_seal.v0.1"] = (
        "proprio.candidate_selection_seal.v0.1"
    )
    instrument_id: str
    candidate_sha256: str
    source_sha256: str
    model: str
    validation_preregistration_sha256: str
    feedback_after_seal_prohibited: Literal[True] = True


class LockedConditionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: str
    index: int
    parameter: str
    value: float
    gate: HardGateResult


class LockedValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.locked_validation.v0.1"] = "proprio.locked_validation.v0.1"
    instrument_id: str
    candidate_sha256: str
    selection_seal_sha256: str
    validation_preregistration_sha256: str
    suite_sha256: str
    cases: tuple[LockedConditionResult, ...]
    passed_cases: int
    verdict: Literal["PASS", "FAIL"]


class RepairSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    diagnosis: str
    evidence_refs: tuple[str, ...]
    skill_md: str
    skill_py: str
    expected_effect: str
    risks: tuple[str, ...]
    self_judgment: dict[str, Any]


class JudgeReview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Literal["ACCEPT", "REJECT", "HOLD"]
    critical_findings: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    summary: str


class HybridVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Literal["ADMIT", "REJECT", "HOLD"]
    hard_verdict: Literal["ADMIT", "REJECT", "HOLD"]
    judge_verdict: Literal["ACCEPT", "REJECT", "HOLD"] | None
    reason: str


class RepairEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.repair_episode.v0.2"] = "proprio.repair_episode.v0.2"
    instrument_id: str
    family: str
    feedback_arm: FeedbackArm
    scenario: SimulationScenario
    initial_candidate: CandidatePackage
    final_candidate: CandidatePackage
    initial_gate: HardGateResult
    final_gate: HardGateResult
    submissions: tuple[RepairSubmission, ...]
    tool_events: tuple[dict[str, Any], ...]
    raw_responses: tuple[dict[str, Any], ...]
    agent_status: Literal["CANDIDATE", "HOLD", "REJECT", "MAX_TURNS"]
    agent_summary: str


class JudgeEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.judge_episode.v0.2"] = "proprio.judge_episode.v0.2"
    instrument_id: str
    review: JudgeReview | None
    tool_events: tuple[dict[str, Any], ...]
    raw_responses: tuple[dict[str, Any], ...]
    status: Literal["completed", "unavailable", "max_turns"]


def effective_judge_verdict(
    judge: JudgeReview | None,
) -> Literal["ACCEPT", "REJECT", "HOLD"] | None:
    """Veto internally inconsistent acceptance without erasing an honest hold."""

    if judge is None:
        return None
    if judge.verdict == "ACCEPT" and judge.critical_findings:
        return "REJECT"
    return judge.verdict


class EvolutionLineage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parent_skill_sha256: str
    proposal_skill_sha256: str
    rollback_skill_sha256: str
    source_sha256: str
    simulator_sha256: str
    verifier_sha256: str
    validation_preregistration_sha256: str
    validation_suite_sha256: str
    evidence_sha256: tuple[str, ...]
    hardware_gate_required: Literal[True] = True


class EvolutionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.evolution_proposal.v0.3"] = "proprio.evolution_proposal.v0.3"
    instrument_id: str
    family: str
    status: Literal["STAGED", "REJECTED", "HOLD"]
    reason: str
    parent_candidate: CandidatePackage
    proposed_candidate: CandidatePackage
    baseline_qualification: tuple[HardGateResult, ...]
    drift_detection: HardGateResult
    qualification: tuple[HardGateResult, ...]
    locked_validation: LockedValidationReport
    repair_episode: RepairEpisode
    judge_episode: JudgeEpisode
    hybrid_verdict: HybridVerdict
    lineage: EvolutionLineage


def combine_hybrid_verdict(
    hard: HardGateResult,
    judge: JudgeReview | None,
) -> HybridVerdict:
    """Combine evidence fail-closed; semantic review can never rescue a hard failure."""

    judge_verdict = effective_judge_verdict(judge)
    if hard.verdict == "REJECT":
        return HybridVerdict(
            verdict="REJECT",
            hard_verdict=hard.verdict,
            judge_verdict=judge_verdict,
            reason="deterministic execution or physical gate rejected the candidate",
        )
    if hard.verdict == "HOLD":
        return HybridVerdict(
            verdict="HOLD",
            hard_verdict=hard.verdict,
            judge_verdict=judge_verdict,
            reason="deterministic evidence is unavailable or outside declared support",
        )
    if judge is None:
        return HybridVerdict(
            verdict="HOLD",
            hard_verdict=hard.verdict,
            judge_verdict=None,
            reason="agent judge unavailable",
        )
    if judge_verdict == "REJECT":
        return HybridVerdict(
            verdict="REJECT",
            hard_verdict=hard.verdict,
            judge_verdict=judge_verdict,
            reason="semantic review found a critical defect",
        )
    if judge_verdict == "HOLD":
        return HybridVerdict(
            verdict="HOLD",
            hard_verdict=hard.verdict,
            judge_verdict=judge_verdict,
            reason="semantic review found insufficient evidence",
        )
    return HybridVerdict(
        verdict="ADMIT",
        hard_verdict=hard.verdict,
        judge_verdict=judge_verdict,
        reason="hard gates passed and semantic review found no critical defect",
    )
