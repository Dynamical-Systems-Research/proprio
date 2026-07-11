"""Bounded search and qualification for scientific-instrument skills."""

from __future__ import annotations

import ast
import hashlib
import math
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from proprio.instrument_types import CandidatePackage, HardGateResult, SimulationScenario


class DebugCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: str
    scenario: SimulationScenario
    parameters: tuple[tuple[str, float], ...] = ()
    repetitions: int = Field(default=3, ge=1, le=7)

    def parameter_map(self) -> dict[str, float]:
        return dict(self.parameters)


class RepeatedConditionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: DebugCondition
    verdict: Literal["ADMIT", "REJECT", "HOLD"]
    gates: tuple[HardGateResult, ...]
    admitted_repetitions: int
    required_admissions: int
    failure_refs: tuple[str, ...]


class DebugSuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.debug_suite.v0.2"] = "proprio.debug_suite.v0.2"
    instrument_id: str
    candidate_sha256: str
    conditions: tuple[RepeatedConditionResult, ...]
    verdict: Literal["ADMIT", "REJECT", "HOLD"]


class PreflightCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    candidate: CandidatePackage
    condition: DebugCondition
    expected_verdict: Literal["ADMIT", "REJECT", "HOLD"]
    required_failed_checks: tuple[str, ...] = ()


class PreflightCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    expected_verdict: Literal["ADMIT", "REJECT", "HOLD"]
    observed: RepeatedConditionResult
    required_failed_checks: tuple[str, ...]
    missing_failed_checks: tuple[str, ...]
    passed: bool


class FixturePreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.fixture_preflight.v0.2"] = "proprio.fixture_preflight.v0.2"
    cases: tuple[PreflightCaseResult, ...]
    verdict: Literal["PASS", "FAIL"]


class ArchiveMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    safety_clean: bool
    admitted_conditions: int
    worst_repetition_rate: float
    check_pass_rate: float
    controller_calls: int


class SearchEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: CandidatePackage
    suite: DebugSuiteResult
    generation: int
    parent_sha256: str | None
    structural_sha256: str
    metrics: ArchiveMetrics
    promotion_eligible: bool
    promotion_blockers: tuple[str, ...] = ()


class RepairOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: CandidatePackage
    record: dict[str, Any]


class SearchReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.candidate_search.v0.2"] = "proprio.candidate_search.v0.2"
    instrument_id: str
    entries: tuple[SearchEntry, ...]
    repairs: tuple[RepairOutcome, ...]
    selected: CandidatePackage | None
    selected_suite: DebugSuiteResult | None
    initial_width: int
    survivor_count: int
    repair_rounds: int
    model_candidates_generated: int
    verdict: Literal["CANDIDATE", "HOLD"]


Evaluator = Callable[..., HardGateResult]
DraftFunction = Callable[[int], CandidatePackage]
RepairFunction = Callable[[CandidatePackage, DebugSuiteResult, int], RepairOutcome]

PROCEDURAL_CHECKS = frozenset(
    {
        "static-safety",
        "runtime-completed",
        "operation-order",
        "resource-release",
        "simulator-available",
    }
)


def _candidate_hash(candidate: CandidatePackage) -> str:
    return hashlib.sha256(candidate.skill_py.encode()).hexdigest()


def _failed_checks(gate: HardGateResult) -> tuple[str, ...]:
    return tuple(check.check_id for check in gate.checks if not check.passed)


def evaluate_repeated_condition(
    candidate: CandidatePackage,
    condition: DebugCondition,
    *,
    evaluator: Evaluator,
) -> RepeatedConditionResult:
    gates = tuple(
        evaluator(
            candidate.instrument_id,
            candidate.skill_py,
            scenario=condition.scenario,
            condition=condition.parameter_map(),
        )
        for _ in range(condition.repetitions)
    )
    admitted = sum(gate.verdict == "ADMIT" for gate in gates)
    required = math.ceil(condition.repetitions * 2 / 3)
    unavailable = any(gate.verdict == "HOLD" or gate.status == "unavailable" for gate in gates)
    procedural_failure = any(
        check.check_id in PROCEDURAL_CHECKS and not check.passed
        for gate in gates
        for check in gate.checks
    )
    if unavailable:
        verdict: Literal["ADMIT", "REJECT", "HOLD"] = "HOLD"
    elif procedural_failure:
        verdict = "REJECT"
    elif admitted >= required:
        verdict = "ADMIT"
    elif admitted == 0:
        verdict = "REJECT"
    else:
        verdict = "HOLD"
    refs = tuple(
        f"debug:{condition.condition_id}:{repetition}:{check_id}"
        for repetition, gate in enumerate(gates)
        for check_id in _failed_checks(gate)
    )
    return RepeatedConditionResult(
        condition=condition,
        verdict=verdict,
        gates=gates,
        admitted_repetitions=admitted,
        required_admissions=required,
        failure_refs=refs,
    )


def evaluate_debug_suite(
    candidate: CandidatePackage,
    conditions: Sequence[DebugCondition],
    *,
    evaluator: Evaluator,
) -> DebugSuiteResult:
    if not conditions:
        raise ValueError("debug suite requires at least one condition")
    identifiers = [condition.condition_id for condition in conditions]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("debug condition identifiers must be unique")
    results = tuple(
        evaluate_repeated_condition(candidate, condition, evaluator=evaluator)
        for condition in conditions
    )
    if any(result.verdict == "REJECT" for result in results):
        verdict: Literal["ADMIT", "REJECT", "HOLD"] = "REJECT"
    elif any(result.verdict == "HOLD" for result in results):
        verdict = "HOLD"
    else:
        verdict = "ADMIT"
    return DebugSuiteResult(
        instrument_id=candidate.instrument_id,
        candidate_sha256=_candidate_hash(candidate),
        conditions=results,
        verdict=verdict,
    )


def run_fixture_preflight(
    cases: Sequence[PreflightCase],
    *,
    evaluator: Evaluator,
) -> FixturePreflightReport:
    expected = {case.expected_verdict for case in cases}
    if expected != {"ADMIT", "REJECT", "HOLD"}:
        raise ValueError("fixture preflight requires explicit ADMIT, REJECT, and HOLD controls")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("preflight case identifiers must be unique")
    rows: list[PreflightCaseResult] = []
    for case in cases:
        observed = evaluate_repeated_condition(
            case.candidate,
            case.condition,
            evaluator=evaluator,
        )
        failed = {
            check.check_id for gate in observed.gates for check in gate.checks if not check.passed
        }
        missing = tuple(sorted(set(case.required_failed_checks) - failed))
        confounded_procedural = case.expected_verdict == "REJECT" and bool(
            (failed & PROCEDURAL_CHECKS) - set(case.required_failed_checks)
        )
        passed = (
            observed.verdict == case.expected_verdict and not missing and not confounded_procedural
        )
        rows.append(
            PreflightCaseResult(
                case_id=case.case_id,
                expected_verdict=case.expected_verdict,
                observed=observed,
                required_failed_checks=case.required_failed_checks,
                missing_failed_checks=missing,
                passed=passed,
            )
        )
    return FixturePreflightReport(
        cases=tuple(rows),
        verdict="PASS" if all(row.passed for row in rows) else "FAIL",
    )


def _structural_hash(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            node.value = 0
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()


def _archive_metrics(suite: DebugSuiteResult) -> ArchiveMetrics:
    all_gates = [gate for condition in suite.conditions for gate in condition.gates]
    all_checks = [check for gate in all_gates for check in gate.checks]
    procedural_failures = [
        check for check in all_checks if check.check_id in PROCEDURAL_CHECKS and not check.passed
    ]
    rates = [
        condition.admitted_repetitions / len(condition.gates) for condition in suite.conditions
    ]
    return ArchiveMetrics(
        safety_clean=not procedural_failures,
        admitted_conditions=sum(condition.verdict == "ADMIT" for condition in suite.conditions),
        worst_repetition_rate=min(rates),
        check_pass_rate=(
            sum(check.passed for check in all_checks) / len(all_checks) if all_checks else 0.0
        ),
        controller_calls=sum(len(gate.trace) for gate in all_gates),
    )


def make_search_entry(
    candidate: CandidatePackage,
    suite: DebugSuiteResult,
    *,
    generation: int,
    parent_sha256: str | None,
    promotion_eligible: bool = True,
    promotion_blockers: tuple[str, ...] = (),
) -> SearchEntry:
    return SearchEntry(
        candidate=candidate,
        suite=suite,
        generation=generation,
        parent_sha256=parent_sha256,
        structural_sha256=_structural_hash(candidate.skill_py),
        metrics=_archive_metrics(suite),
        promotion_eligible=promotion_eligible,
        promotion_blockers=promotion_blockers,
    )


def _quality_vector(entry: SearchEntry) -> tuple[float, ...]:
    metrics = entry.metrics
    return (
        float(metrics.safety_clean),
        float(metrics.admitted_conditions),
        metrics.worst_repetition_rate,
        metrics.check_pass_rate,
        -float(metrics.controller_calls),
    )


def _dominates(left: SearchEntry, right: SearchEntry) -> bool:
    left_vector = _quality_vector(left)
    right_vector = _quality_vector(right)
    return all(a >= b for a, b in zip(left_vector, right_vector, strict=True)) and any(
        a > b for a, b in zip(left_vector, right_vector, strict=True)
    )


def select_archive(entries: Sequence[SearchEntry], *, limit: int) -> tuple[SearchEntry, ...]:
    if limit < 1:
        raise ValueError("archive limit must be positive")
    frontier = [
        entry
        for entry in entries
        if not any(_dominates(other, entry) for other in entries if other is not entry)
    ]
    ranked = sorted(
        frontier,
        key=lambda entry: (*_quality_vector(entry), entry.suite.candidate_sha256),
        reverse=True,
    )
    selected: list[SearchEntry] = []
    structures: set[str] = set()
    for entry in ranked:
        if entry.structural_sha256 in structures:
            continue
        selected.append(entry)
        structures.add(entry.structural_sha256)
        if len(selected) == limit:
            return tuple(selected)
    for entry in ranked:
        if entry in selected:
            continue
        selected.append(entry)
        if len(selected) == limit:
            break
    return tuple(selected)


def run_archive_search(
    instrument_id: str,
    *,
    conditions: Sequence[DebugCondition],
    evaluator: Evaluator,
    draft: DraftFunction,
    repair: RepairFunction,
    preflight: FixturePreflightReport,
    seed_base: int,
    initial_width: int = 4,
    survivor_count: int = 2,
    repair_rounds: int = 4,
) -> SearchReport:
    if preflight.verdict != "PASS":
        raise RuntimeError("fixture preflight failed before model invocation")
    if initial_width < 1 or survivor_count < 1 or repair_rounds < 0:
        raise ValueError("search budgets must be non-negative and non-zero where applicable")
    with ThreadPoolExecutor(max_workers=initial_width) as pool:
        candidates = tuple(pool.map(draft, range(seed_base, seed_base + initial_width)))
    if any(candidate.instrument_id != instrument_id for candidate in candidates):
        raise ValueError("draft returned a candidate for a different instrument")
    entries = [
        make_search_entry(
            candidate,
            evaluate_debug_suite(candidate, conditions, evaluator=evaluator),
            generation=0,
            parent_sha256=None,
        )
        for candidate in candidates
    ]
    repairs: list[RepairOutcome] = []
    generated = len(entries)
    for round_index in range(1, repair_rounds + 1):
        if any(entry.suite.verdict == "ADMIT" and entry.promotion_eligible for entry in entries):
            break
        parents = select_archive(entries, limit=survivor_count)
        for parent_index, parent in enumerate(parents):
            outcome = repair(
                parent.candidate,
                parent.suite,
                seed_base + initial_width + (round_index - 1) * survivor_count + parent_index,
            )
            repairs.append(outcome)
            child = outcome.candidate
            if child.instrument_id != instrument_id:
                raise ValueError("repair returned a candidate for a different instrument")
            child_suite = evaluate_debug_suite(child, conditions, evaluator=evaluator)
            agent_status = outcome.record.get("agent_status")
            promotion_eligible = agent_status == "CANDIDATE"
            blockers = () if promotion_eligible else (f"agent-status:{agent_status or 'missing'}",)
            entries.append(
                make_search_entry(
                    child,
                    child_suite,
                    generation=round_index,
                    parent_sha256=parent.suite.candidate_sha256,
                    promotion_eligible=promotion_eligible,
                    promotion_blockers=blockers,
                )
            )
            generated += 1
    qualified = [
        entry for entry in entries if entry.suite.verdict == "ADMIT" and entry.promotion_eligible
    ]
    selected_entry = select_archive(qualified, limit=1)[0] if qualified else None
    return SearchReport(
        instrument_id=instrument_id,
        entries=tuple(entries),
        repairs=tuple(repairs),
        selected=None if selected_entry is None else selected_entry.candidate,
        selected_suite=None if selected_entry is None else selected_entry.suite,
        initial_width=initial_width,
        survivor_count=survivor_count,
        repair_rounds=repair_rounds,
        model_candidates_generated=generated,
        verdict="CANDIDATE" if selected_entry is not None else "HOLD",
    )
