"""Locked condition validation for the frozen confirmatory panel."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import source_sha256, write_canonical_json
from proprio.confirmatory_qualification import evaluate_confirmatory_skill
from proprio.instrument_types import (
    CandidatePackage,
    CandidateSelectionSeal,
    LockedConditionResult,
    LockedValidationReport,
    SimulationScenario,
)
from proprio.schema import canonical_json

PREREGISTRATION = Path(__file__).with_name("data") / "confirmatory-preregistration.yaml"


def _hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _candidate_hash(candidate: CandidatePackage) -> str:
    return hashlib.sha256(candidate.skill_py.encode()).hexdigest()


def seal_confirmatory_candidate(candidate: CandidatePackage) -> CandidateSelectionSeal:
    return CandidateSelectionSeal(
        instrument_id=candidate.instrument_id,
        candidate_sha256=_candidate_hash(candidate),
        source_sha256=candidate.source_sha256,
        model=candidate.model,
        validation_preregistration_sha256=source_sha256(PREREGISTRATION),
    )


def _fraction(instrument_id: str, index: int) -> float:
    payload = f"confirmatory:917431:{instrument_id}:{index}".encode()
    value = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return (value + 0.5) / 2**64


def generate_confirmatory_conditions(instrument_id: str) -> tuple[dict[str, Any], ...]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    spec = prereg["locked_conditions"][instrument_id]
    count = int(prereg["evaluation"]["locked_cases_per_instrument"])
    minimum = float(spec["minimum"])
    maximum = float(spec["maximum"])
    parameter = str(spec["parameter"])
    conditions = []
    for index in range(count):
        value = minimum + _fraction(instrument_id, index) * (maximum - minimum)
        digest = _hash(
            {
                "instrument_id": instrument_id,
                "index": index,
                "parameter": parameter,
                "value": value,
            }
        )[:20]
        conditions.append(
            {
                "condition_id": f"confirmatory_{digest}",
                "index": index,
                "parameter": parameter,
                "value": value,
            }
        )
    return tuple(conditions)


def evaluate_confirmatory_validation(
    candidate: CandidatePackage,
    seal: CandidateSelectionSeal,
) -> LockedValidationReport:
    if seal != seal_confirmatory_candidate(candidate):
        raise ValueError("candidate does not match its confirmatory selection seal")
    conditions = generate_confirmatory_conditions(candidate.instrument_id)
    cases = tuple(
        LockedConditionResult(
            **condition,
            gate=evaluate_confirmatory_skill(
                candidate.instrument_id,
                candidate.skill_py,
                scenario=SimulationScenario.REPAIR,
                condition={condition["parameter"]: condition["value"]},
            ),
        )
        for condition in conditions
    )
    passed = sum(case.gate.verdict == "ADMIT" for case in cases)
    return LockedValidationReport(
        instrument_id=candidate.instrument_id,
        candidate_sha256=seal.candidate_sha256,
        selection_seal_sha256=_hash(seal),
        validation_preregistration_sha256=seal.validation_preregistration_sha256,
        suite_sha256=_hash(conditions),
        cases=cases,
        passed_cases=passed,
        verdict="PASS" if passed == len(cases) else "FAIL",
    )


def run_confirmatory_validation_once(
    candidate: CandidatePackage,
    seal_path: Path,
    output_path: Path,
) -> LockedValidationReport:
    if output_path.exists():
        raise FileExistsError(f"confirmatory validation already executed: {output_path}")
    seal = seal_confirmatory_candidate(candidate)
    if seal_path.exists():
        captured = CandidateSelectionSeal.model_validate_json(seal_path.read_text(encoding="utf-8"))
        if captured != seal:
            raise ValueError("existing seal belongs to a different candidate")
    else:
        write_canonical_json(seal_path, seal)
    report = evaluate_confirmatory_validation(candidate, seal)
    write_canonical_json(output_path, report)
    return report
