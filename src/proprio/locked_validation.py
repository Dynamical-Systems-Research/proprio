"""One-shot condition validation after a skill candidate has been sealed."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import source_sha256, write_canonical_json
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_types import (
    CandidatePackage,
    CandidateSelectionSeal,
    LockedConditionResult,
    LockedValidationReport,
    SimulationScenario,
)
from proprio.schema import canonical_json

PREREGISTRATION = Path(__file__).with_name("data") / "locked-validation-preregistration.yaml"


def _candidate_hash(candidate: CandidatePackage) -> str:
    return hashlib.sha256(candidate.skill_py.encode()).hexdigest()


def _object_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(canonical_json(value)).hexdigest()


def seal_candidate(candidate: CandidatePackage) -> CandidateSelectionSeal:
    """Bind an immutable candidate to the already-frozen validation protocol."""

    return CandidateSelectionSeal(
        instrument_id=candidate.instrument_id,
        candidate_sha256=_candidate_hash(candidate),
        source_sha256=candidate.source_sha256,
        model=candidate.model,
        validation_preregistration_sha256=source_sha256(PREREGISTRATION),
    )


def _unit_interval(master_seed: int, instrument_id: str, index: int) -> float:
    payload = f"{master_seed}:{instrument_id}:{index}".encode()
    integer = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return (integer + 0.5) / 2**64


def generate_locked_conditions(instrument_id: str) -> tuple[dict[str, Any], ...]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    spec = prereg["conditions"][instrument_id]
    protocol = prereg["protocol"]
    count = int(protocol["cases_per_instrument"])
    minimum = float(spec["minimum"])
    maximum = float(spec["maximum"])
    parameter = str(spec["parameter"])
    conditions: list[dict[str, Any]] = []
    for index in range(count):
        fraction = _unit_interval(int(protocol["master_seed"]), instrument_id, index)
        value = minimum + fraction * (maximum - minimum)
        condition_id = hashlib.sha256(
            canonical_json(
                {
                    "instrument_id": instrument_id,
                    "index": index,
                    "parameter": parameter,
                    "value": value,
                }
            )
        ).hexdigest()[:20]
        conditions.append(
            {
                "condition_id": f"condition_{condition_id}",
                "index": index,
                "parameter": parameter,
                "value": value,
            }
        )
    return tuple(conditions)


def evaluate_locked_validation(
    candidate: CandidatePackage,
    seal: CandidateSelectionSeal,
) -> LockedValidationReport:
    """Evaluate a sealed candidate without exposing results to a repair loop."""

    expected_seal = seal_candidate(candidate)
    if seal != expected_seal:
        raise ValueError("candidate does not match its locked-validation selection seal")
    conditions = generate_locked_conditions(candidate.instrument_id)
    cases = tuple(
        LockedConditionResult(
            **condition,
            gate=evaluate_instrument_skill(
                candidate.instrument_id,
                candidate.skill_py,
                scenario=SimulationScenario.DRIFT,
                condition={condition["parameter"]: condition["value"]},
            ),
        )
        for condition in conditions
    )
    passed = sum(case.gate.verdict == "ADMIT" for case in cases)
    return LockedValidationReport(
        instrument_id=candidate.instrument_id,
        candidate_sha256=seal.candidate_sha256,
        selection_seal_sha256=_object_hash(seal),
        validation_preregistration_sha256=seal.validation_preregistration_sha256,
        suite_sha256=_object_hash(conditions),
        cases=cases,
        passed_cases=passed,
        verdict="PASS" if passed == len(cases) else "FAIL",
    )


def run_locked_validation_once(
    candidate: CandidatePackage,
    seal_path: Path,
    output_path: Path,
) -> LockedValidationReport:
    """Persist the seal, then refuse a second selection-time validation execution."""

    if output_path.exists():
        raise FileExistsError(f"locked validation already executed: {output_path}")
    seal = seal_candidate(candidate)
    if seal_path.exists():
        captured = CandidateSelectionSeal.model_validate_json(seal_path.read_text(encoding="utf-8"))
        if captured != seal:
            raise ValueError("existing selection seal belongs to a different candidate")
    else:
        write_canonical_json(seal_path, seal)
    report = evaluate_locked_validation(candidate, seal)
    write_canonical_json(output_path, report)
    return report
