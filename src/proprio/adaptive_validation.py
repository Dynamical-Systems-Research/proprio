"""Sealed, one-shot qualification for selected adaptive skills."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from proprio.adaptive_microscopy import INSTRUMENT_ID, evaluate_live_adaptive_microscopy
from proprio.adaptive_search import (
    DebugCondition,
    DebugSuiteResult,
    SearchReport,
    evaluate_repeated_condition,
)
from proprio.artifacts import source_sha256, write_canonical_json
from proprio.instrument_types import CandidatePackage, HardGateResult, SimulationScenario
from proprio.schema import canonical_json

PREREGISTRATION = Path(__file__).with_name("data") / "adaptive-method-preregistration.yaml"


class AdaptiveSelectionSeal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.adaptive_selection_seal.v0.2"] = (
        "proprio.adaptive_selection_seal.v0.2"
    )
    instrument_id: str
    candidate_sha256: str
    source_sha256: str
    visible_suite_sha256: str
    method_preregistration_sha256: str


class AdaptiveLockedCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: DebugCondition
    verdict: Literal["ADMIT", "REJECT", "HOLD"]
    gate: HardGateResult
    gate_sha256: str
    failed_checks: tuple[str, ...]


class AdaptiveLockedReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.adaptive_locked_qualification.v0.2"] = (
        "proprio.adaptive_locked_qualification.v0.2"
    )
    instrument_id: str
    candidate_sha256: str
    selection_seal_sha256: str
    cases: tuple[AdaptiveLockedCase, ...]
    verdict: Literal["PASS", "FAIL"]


def _object_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(canonical_json(value)).hexdigest()


def seal_adaptive_candidate(
    candidate: CandidatePackage,
    visible_suite: DebugSuiteResult,
) -> AdaptiveSelectionSeal:
    candidate_sha = hashlib.sha256(candidate.skill_py.encode()).hexdigest()
    if visible_suite.candidate_sha256 != candidate_sha:
        raise ValueError("visible suite belongs to a different candidate")
    return AdaptiveSelectionSeal(
        instrument_id=candidate.instrument_id,
        candidate_sha256=candidate_sha,
        source_sha256=candidate.source_sha256,
        visible_suite_sha256=_object_hash(visible_suite),
        method_preregistration_sha256=source_sha256(PREREGISTRATION),
    )


def generate_adaptive_microscopy_locked_conditions() -> tuple[DebugCondition, ...]:
    config = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    locked = config["locked_qualification"]["openflexure_development"]
    count = int(locked["cases"])
    seed = int(locked["seed"])
    start_min = float(locked["start_z_min"])
    start_max = float(locked["start_z_max"])
    noise_min = float(locked["measurement_noise_level_min"])
    noise_max = float(locked["measurement_noise_level_max"])
    conditions = []
    for index in range(count):
        digest = hashlib.sha256(f"{seed}:{INSTRUMENT_ID}:{index}".encode()).hexdigest()
        start_fraction = int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
        noise_fraction = int(digest[16:32], 16) / float(0xFFFFFFFFFFFFFFFF)
        conditions.append(
            DebugCondition(
                condition_id=f"locked-{digest[:20]}",
                scenario=SimulationScenario.REPAIR,
                parameters=(
                    ("start_z", round(start_min + (start_max - start_min) * start_fraction, 6)),
                    (
                        "measurement_noise_level",
                        round(noise_min + (noise_max - noise_min) * noise_fraction, 6),
                    ),
                ),
                repetitions=1,
            )
        )
    return tuple(conditions)


def evaluate_adaptive_locked(
    candidate: CandidatePackage,
    seal: AdaptiveSelectionSeal,
    *,
    evaluator: Callable[..., Any],
) -> AdaptiveLockedReport:
    candidate_sha = hashlib.sha256(candidate.skill_py.encode()).hexdigest()
    if candidate_sha != seal.candidate_sha256 or candidate.instrument_id != seal.instrument_id:
        raise ValueError("candidate does not match selection seal")
    if seal.method_preregistration_sha256 != source_sha256(PREREGISTRATION):
        raise ValueError("method preregistration changed after candidate selection")
    rows = []
    for condition in generate_adaptive_microscopy_locked_conditions():
        result = evaluate_repeated_condition(candidate, condition, evaluator=evaluator)
        failed = tuple(
            check.check_id
            for gate in result.gates
            for check in gate.checks
            if not check.passed
        )
        rows.append(
            AdaptiveLockedCase(
                condition=condition,
                verdict=result.verdict,
                gate=result.gates[0],
                gate_sha256=_object_hash(result.gates[0]),
                failed_checks=failed,
            )
        )
    return AdaptiveLockedReport(
        instrument_id=candidate.instrument_id,
        candidate_sha256=candidate_sha,
        selection_seal_sha256=_object_hash(seal),
        cases=tuple(rows),
        verdict="PASS" if all(row.verdict == "ADMIT" for row in rows) else "FAIL",
    )


def run_live_adaptive_microscopy_locked(
    output_dir: Path,
    *,
    search_path: Path,
    base_url: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    search = SearchReport.model_validate_json(search_path.read_text(encoding="utf-8"))
    if search.selected is None or search.selected_suite is None or search.verdict != "CANDIDATE":
        raise RuntimeError("locked qualification requires a selected search candidate")
    candidate = search.selected
    visible_suite = search.selected_suite
    seal = seal_adaptive_candidate(candidate, visible_suite)
    write_canonical_json(output_dir / "selection-seal.json", seal)

    def evaluator(instrument_id: str, source: str, **kwargs: Any):
        return evaluate_live_adaptive_microscopy(
            instrument_id,
            source,
            base_url=base_url,
            **kwargs,
        )

    report = evaluate_adaptive_locked(candidate, seal, evaluator=evaluator)
    write_canonical_json(output_dir / "locked-qualification.json", report)
    summary = {
        "schema_version": "proprio.adaptive_locked_summary.v0.2",
        "instrument_id": candidate.instrument_id,
        "cases": len(report.cases),
        "admitted": sum(case.verdict == "ADMIT" for case in report.cases),
        "verdict": report.verdict,
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
