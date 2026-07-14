"""Build the compact, installable, evidence-bound skill library."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from proprio.artifacts import write_canonical_json
from proprio.instrument_types import CandidatePackage
from proprio.instruments import INSTRUMENTS, evaluate_instrument_skill, instrument_kind
from proprio.schema import canonical_json
from proprio.skill_search import DebugSuiteResult, evaluate_debug_suite


@dataclass(frozen=True)
class PublishedSkill:
    skill_id: str
    version: str
    instrument: str
    status: Literal["reference", "simulation_qualified", "simulation_staged"]


PUBLISHED_SKILLS = (
    PublishedSkill("xrd-operate-observe", "0.1.0", "2D area-detector powder XRD", "reference"),
    PublishedSkill(
        "keithley-2450-measure-current",
        "1.0.0",
        "Keithley 2450-style SMU",
        "simulation_qualified",
    ),
    PublishedSkill(
        "absorbance-plate-read",
        "0.1.0",
        "reduced-order absorbance plate reader",
        "simulation_qualified",
    ),
    PublishedSkill(
        "calibrated-pump-dose",
        "0.1.0",
        "reduced-order calibrated peristaltic pump",
        "simulation_qualified",
    ),
    PublishedSkill(
        "dual-pump-blend",
        "0.1.0",
        "reduced-order dual-channel pump array",
        "simulation_qualified",
    ),
    PublishedSkill(
        "fluorescence-plate-read",
        "0.1.0",
        "reduced-order fluorescence plate reader",
        "simulation_qualified",
    ),
    PublishedSkill(
        "isothermal-hold",
        "0.1.0",
        "reduced-order temperature controller",
        "simulation_qualified",
    ),
    PublishedSkill(
        "thermal-cycle",
        "0.1.0",
        "reduced-order heating and cooling controller",
        "simulation_qualified",
    ),
    PublishedSkill(
        "north-pipette-calibration",
        "0.4.0",
        "North Cytation pipette calibration",
        "simulation_qualified",
    ),
    PublishedSkill(
        "helao-gamry-cv",
        "0.4.0",
        "HELAO Gamry cyclic voltammetry",
        "simulation_qualified",
    ),
    PublishedSkill(
        "clslab-light-spectrometer",
        "0.4.0",
        "CLSLab light spectrometer",
        "simulation_qualified",
    ),
    PublishedSkill(
        "openflexure-adaptive-autofocus",
        "0.1.0",
        "OpenFlexure adaptive autofocus",
        "simulation_staged",
    ),
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(root: Path, skill_id: str) -> CandidatePackage:
    from proprio.instruments import load_instrument_source

    package = root / "skills" / skill_id
    _, source_hash = load_instrument_source(skill_id)
    return CandidatePackage(
        instrument_id=skill_id,
        skill_md=(package / "SKILL.md").read_text(encoding="utf-8"),
        skill_py=(package / "scripts" / "operate.py").read_text(encoding="utf-8"),
        self_judgment={"verdict": "UNVERIFIED", "basis": ["publication replay"]},
        source_sha256=source_hash,
        prompt_sha256="publication-replay",
        model="publication-replay",
        raw_response={},
    )


def _suite_summary(suite: DebugSuiteResult) -> dict[str, Any]:
    return {
        "verdict": suite.verdict,
        "conditions": [
            {
                "condition_id": row.condition.condition_id,
                "scenario": row.condition.scenario.value,
                "repetitions": row.condition.repetitions,
                "admitted_repetitions": row.admitted_repetitions,
                "required_admissions": row.required_admissions,
                "verdict": row.verdict,
                "checks": sorted({check.check_id for gate in row.gates for check in gate.checks}),
            }
            for row in suite.conditions
        ],
    }


def _runtime_record(root: Path, skill: PublishedSkill) -> dict[str, Any]:
    definition = INSTRUMENTS[skill.skill_id]
    candidate = _candidate(root, skill.skill_id)
    visible = evaluate_debug_suite(
        candidate,
        definition.visible_conditions,
        evaluator=evaluate_instrument_skill,
    )
    locked = evaluate_debug_suite(
        candidate,
        definition.locked_conditions,
        evaluator=evaluate_instrument_skill,
    )
    evolution = evaluate_debug_suite(
        candidate,
        definition.evolution_conditions,
        evaluator=evaluate_instrument_skill,
    )
    gates = [
        gate
        for suite in (visible, locked)
        for condition in suite.conditions
        for gate in condition.gates
    ]
    hashes = {gate.verifier_sha256 for gate in gates}
    if len(hashes) != 1:
        raise RuntimeError(f"verifier identity changed within publication replay: {skill.skill_id}")
    verdict = "PASS" if visible.verdict == locked.verdict == "ADMIT" else "FAIL"
    return {
        "schema_version": "proprio.skill_verification.v0.1",
        "skill_id": skill.skill_id,
        "qualification_status": skill.status,
        "runtime_kind": instrument_kind(skill.skill_id),
        "skill_sha256": hashlib.sha256(candidate.skill_md.encode()).hexdigest(),
        "code_sha256": hashlib.sha256(candidate.skill_py.encode()).hexdigest(),
        "source_sha256": candidate.source_sha256,
        "verifier_sha256": next(iter(hashes)),
        "upstream_revision": definition.upstream_revision,
        "visible": _suite_summary(visible),
        "locked": _suite_summary(locked),
        "registered_evolution": _suite_summary(evolution),
        "hardware_validation_required": True,
        "claim_boundary": "Verified in simulation. Hardware validation remains separate.",
        "verdict": verdict,
    }


def _keithley_record(root: Path, skill: PublishedSkill) -> dict[str, Any]:
    evidence_path = root / "artifacts/evidence/skill-admission/summary.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    correct = evidence["cases"]["correct"]
    package = root / "skills" / skill.skill_id
    code_path = package / "scripts/operate.py"
    passed = (
        evidence.get("verdict") == "PASS"
        and correct["admission"] == "ADMIT"
        and correct["verified_skill_sha256"] == _hash(code_path)
    )
    return {
        "schema_version": "proprio.skill_verification.v0.1",
        "skill_id": skill.skill_id,
        "qualification_status": skill.status,
        "runtime_kind": "built-in-pyvisa-sim",
        "skill_sha256": _hash(package / "SKILL.md"),
        "code_sha256": _hash(code_path),
        "source_sha256": correct["source_sha256"],
        "verifier_sha256": correct["verifier_sha256"],
        "evidence": {
            "artifact": str(evidence_path.relative_to(root)),
            "admission": correct["admission"],
            "reject_control": evidence["cases"]["wrong-range"]["admission"],
        },
        "hardware_validation_required": True,
        "claim_boundary": "Verified in simulation. Hardware validation remains separate.",
        "verdict": "PASS" if passed else "FAIL",
    }


def _xrd_record(root: Path, skill: PublishedSkill) -> dict[str, Any]:
    evidence_path = root / "artifacts/evidence/composition/summary.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    package = root / "skills" / skill.skill_id
    return {
        "schema_version": "proprio.skill_verification.v0.1",
        "skill_id": skill.skill_id,
        "qualification_status": skill.status,
        "runtime_kind": "reference-workflow",
        "skill_sha256": _hash(package / "SKILL.md"),
        "code_sha256": None,
        "source_sha256": None,
        "verifier_sha256": None,
        "evidence": {
            "artifact": str(evidence_path.relative_to(root)),
            "artifact_verdict": evidence.get("verdict"),
        },
        "hardware_validation_required": True,
        "claim_boundary": "Reference workflow only. Hardware validation remains separate.",
        "verdict": "PASS" if evidence.get("verdict") == "PASS" else "FAIL",
    }


def _openflexure_record(root: Path, skill: PublishedSkill) -> dict[str, Any]:
    evidence_path = root / "public/proprio-demo.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    package = root / "skills" / skill.skill_id
    code_path = package / "scripts/operate.py"
    source_path = package / "references/controller.md"
    fresh = evidence["fresh_executions"]
    checks = {
        "initial-acquisition-rejected": fresh["initial_acquisition"] == "REJECT",
        "parent-admitted": fresh["parent_admission"]
        == {"visible": "1/1", "historical": "3/3", "locked": "5/5"},
        "drift-invalidated-parent": fresh["drift_parent"] == "REJECT",
        "first-evolution-rejected": fresh["magnitude_only_evolution"] == "REJECT",
        "proposal-replay-passed": fresh["proposal_replay"]
        == {"changed": "1/1", "historical": "3/3", "locked": "5/5"},
        "proposal-staged": fresh["final_decision"] == "STAGED",
        "parent-immutable": evidence["candidate_bindings"]["parent_immutable"] is True,
    }
    passed = (
        evidence["scope"]["status"] == "STAGED"
        and all(checks.values())
        and evidence["candidate_bindings"]["proposal_sha256"] == _hash(code_path)
        and evidence["source"]["sha256"] == _hash(source_path)
    )
    return {
        "schema_version": "proprio.skill_verification.v0.1",
        "skill_id": skill.skill_id,
        "qualification_status": skill.status,
        "runtime_kind": "external-openflexure-server",
        "skill_sha256": _hash(package / "SKILL.md"),
        "code_sha256": _hash(code_path),
        "source_sha256": _hash(source_path),
        "verifier_sha256": evidence["proprio_runtime"]["verifier_source_sha256"],
        "upstream_revision": evidence["simulator"]["revision"],
        "evidence": {
            "artifact": str(evidence_path.relative_to(root)),
            "status": evidence["scope"]["status"],
            "checks": checks,
        },
        "hardware_validation_required": True,
        "claim_boundary": "Staged in simulation. Hardware validation remains separate.",
        "verdict": "PASS" if passed else "FAIL",
    }


def build_skill_verification(root: Path, skill: PublishedSkill) -> dict[str, Any]:
    if skill.skill_id in INSTRUMENTS:
        return _runtime_record(root, skill)
    if skill.skill_id == "keithley-2450-measure-current":
        return _keithley_record(root, skill)
    if skill.skill_id == "xrd-operate-observe":
        return _xrd_record(root, skill)
    if skill.skill_id == "openflexure-adaptive-autofocus":
        return _openflexure_record(root, skill)
    raise KeyError(skill.skill_id)


def _catalog_entry(root: Path, skill: PublishedSkill, record: dict[str, Any]) -> dict[str, Any]:
    package = root / "skills" / skill.skill_id
    code_path = package / "scripts/operate.py"
    return {
        "id": skill.skill_id,
        "version": skill.version,
        "instrument": skill.instrument,
        "path": str((package / "SKILL.md").relative_to(root)),
        "code_path": str(code_path.relative_to(root)) if code_path.is_file() else None,
        "status": skill.status,
        "hardware_qualification_required": True,
        "verification": {
            "artifact": str((package / "references/verification.json").relative_to(root)),
            "artifact_verdict": "PASS",
            "skill_sha256": record["skill_sha256"],
            "code_sha256": record["code_sha256"],
            "source_sha256": record["source_sha256"],
            "verifier_sha256": record["verifier_sha256"],
        },
    }


def build_skill_library(
    root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    """Build the publication payload without changing the repository."""

    root = root.resolve()
    records = {}
    entries = []
    for skill in PUBLISHED_SKILLS:
        record = build_skill_verification(root, skill)
        records[skill.skill_id] = record
        entries.append(_catalog_entry(root, skill, record))
    catalog = {"schema_version": "proprio.skill_catalog.v0.2", "skills": entries}
    failed = [skill_id for skill_id, record in records.items() if record["verdict"] != "PASS"]
    publication = {
        "schema_version": "proprio.skill_library_publication.v0.1",
        "catalog": "catalog.json",
        "published_skills": len(records),
        "failed_skills": failed,
        "library_sha256": hashlib.sha256(canonical_json(catalog)).hexdigest(),
        "verdict": "PASS" if not failed else "FAIL",
    }
    return publication, records, catalog


def publish_skill_library(root: Path) -> dict[str, Any]:
    """Regenerate compact verification records and the content-addressed catalog."""

    root = root.resolve()
    publication, records, catalog = build_skill_library(root)
    for skill_id, record in records.items():
        output = root / "skills" / skill_id / "references/verification.json"
        write_canonical_json(output, record)
    write_canonical_json(root / "catalog.json", catalog)
    return publication
