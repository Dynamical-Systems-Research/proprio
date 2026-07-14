"""Build the compact, installable, evidence-bound skill library."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from proprio.artifacts import write_canonical_json
from proprio.instrument_types import CandidatePackage
from proprio.instruments import (
    get_instrument_definition,
    has_instrument,
    instrument_kind,
)
from proprio.interface import (
    execute_candidate,
    inspect_source,
    read_visible_evidence,
    stage_evolution,
    verify_locked,
)
from proprio.schema import canonical_json
from proprio.skill_search import DebugSuiteResult


@dataclass(frozen=True)
class PublishedSkill:
    skill_id: str
    version: str
    instrument: str
    status: Literal["simulation_qualified", "simulation_staged"]
    provider_instrument_id: str | None = None
    parent_code_path: str | None = None


PUBLISHED_SKILLS = (
    PublishedSkill(
        "xrd-operate-observe",
        "0.5.0",
        "2D area-detector powder XRD",
        "simulation_qualified",
        "proprio.xrd.xrd-operate-observe",
    ),
    PublishedSkill(
        "keithley-2450-measure-current",
        "1.0.0",
        "Keithley 2450-style SMU",
        "simulation_qualified",
        "proprio.keithley.keithley-2450-measure-current",
    ),
    PublishedSkill(
        "absorbance-plate-read",
        "0.1.0",
        "reduced-order absorbance plate reader",
        "simulation_qualified",
        "proprio.reduced_order.absorbance-plate-read",
    ),
    PublishedSkill(
        "calibrated-pump-dose",
        "0.1.0",
        "reduced-order calibrated peristaltic pump",
        "simulation_qualified",
        "proprio.reduced_order.calibrated-pump-dose",
    ),
    PublishedSkill(
        "dual-pump-blend",
        "0.1.0",
        "reduced-order dual-channel pump array",
        "simulation_qualified",
        "proprio.reduced_order.dual-pump-blend",
    ),
    PublishedSkill(
        "fluorescence-plate-read",
        "0.1.0",
        "reduced-order fluorescence plate reader",
        "simulation_qualified",
        "proprio.reduced_order.fluorescence-plate-read",
    ),
    PublishedSkill(
        "isothermal-hold",
        "0.1.0",
        "reduced-order temperature controller",
        "simulation_qualified",
        "proprio.reduced_order.isothermal-hold",
    ),
    PublishedSkill(
        "thermal-cycle",
        "0.1.0",
        "reduced-order heating and cooling controller",
        "simulation_qualified",
        "proprio.reduced_order.thermal-cycle",
    ),
    PublishedSkill(
        "north-pipette-calibration",
        "0.4.0",
        "North Cytation pipette calibration",
        "simulation_qualified",
        "proprio.external_reference.north-pipette-calibration",
    ),
    PublishedSkill(
        "helao-gamry-cv",
        "0.4.0",
        "HELAO Gamry cyclic voltammetry",
        "simulation_qualified",
        "proprio.external_reference.helao-gamry-cv",
    ),
    PublishedSkill(
        "clslab-light-spectrometer",
        "0.4.0",
        "CLSLab light spectrometer",
        "simulation_qualified",
        "proprio.external_reference.clslab-light-spectrometer",
    ),
    PublishedSkill(
        "openflexure-adaptive-autofocus",
        "0.2.0",
        "OpenFlexure adaptive autofocus",
        "simulation_staged",
        "proprio.openflexure.microscope-autofocus",
        "skills/openflexure-adaptive-autofocus/references/admitted-parent.py",
    ),
)


def _candidate(
    root: Path,
    skill_id: str,
    instrument_id: str,
    *,
    code_path: Path | None = None,
    model: str = "publication-replay",
) -> CandidatePackage:
    from proprio.instruments import load_instrument_source

    package = root / "skills" / skill_id
    _, source_hash = load_instrument_source(instrument_id)
    return CandidatePackage(
        instrument_id=instrument_id,
        skill_md=(package / "SKILL.md").read_text(encoding="utf-8"),
        skill_py=(code_path or package / "scripts" / "operate.py").read_text(encoding="utf-8"),
        self_judgment={"verdict": "UNVERIFIED", "basis": ["publication replay"]},
        source_sha256=source_hash,
        prompt_sha256="publication-replay",
        model=model,
        raw_response={},
    )


def _suite_summary(suite: DebugSuiteResult) -> dict[str, Any]:
    return {
        "verdict": suite.verdict,
        "conditions": [
            {
                "condition_id": row.condition.condition_id,
                "scenario": row.condition.scenario.value,
                "parameters": dict(row.condition.parameters),
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
    if skill.provider_instrument_id is None:
        raise ValueError(f"skill has no provider instrument: {skill.skill_id}")
    inspection = inspect_source(skill.provider_instrument_id)
    candidate = _candidate(root, skill.skill_id, skill.provider_instrument_id)
    if candidate.source_sha256 != inspection["source_sha256"]:
        raise RuntimeError(f"source identity changed during publication replay: {skill.skill_id}")

    with tempfile.TemporaryDirectory(prefix=f"proprio-publish-{skill.skill_id}-") as temporary:
        run_root = Path(temporary)
        execution = execute_candidate(
            skill.provider_instrument_id,
            candidate,
            output_dir=run_root / "execute",
        )
        visible_evidence = read_visible_evidence(run_root / "execute")
        visible = DebugSuiteResult.model_validate(visible_evidence["evidence"])
        locked_result = verify_locked(candidate, output_dir=run_root / "locked")
        locked = DebugSuiteResult.model_validate_json(
            (run_root / "locked" / "locked.json").read_text(encoding="utf-8")
        )
        replayed_visible = DebugSuiteResult.model_validate_json(
            (run_root / "locked" / "visible-replay.json").read_text(encoding="utf-8")
        )
        suites = [visible, replayed_visible, locked]
        evolution_record: dict[str, Any] | None = None

        if skill.status == "simulation_staged":
            assert skill.parent_code_path is not None
            parent = _candidate(
                root,
                skill.skill_id,
                skill.provider_instrument_id,
                code_path=root / skill.parent_code_path,
                model="publication-parent-replay",
            )
            parent_locked = verify_locked(parent, output_dir=run_root / "parent-locked")
            parent_visible_suite = DebugSuiteResult.model_validate_json(
                (run_root / "parent-locked" / "visible-replay.json").read_text(encoding="utf-8")
            )
            parent_locked_suite = DebugSuiteResult.model_validate_json(
                (run_root / "parent-locked" / "locked.json").read_text(encoding="utf-8")
            )
            evolution = stage_evolution(parent, candidate, output_dir=run_root / "evolution")
            staged_suites = {
                name: DebugSuiteResult.model_validate_json(
                    (run_root / "evolution" / f"{name}.json").read_text(encoding="utf-8")
                )
                for name in (
                    "parent-drift",
                    "candidate-acquisition",
                    "candidate-visible",
                    "candidate-drift",
                    "candidate-locked",
                )
            }
            suites.extend((parent_visible_suite, parent_locked_suite, *staged_suites.values()))
            evolution_record = {
                "status": evolution["status"],
                "verdict": evolution["verdict"],
                "parent_sha256": evolution["parent_sha256"],
                "candidate_sha256": evolution["candidate_sha256"],
                "candidate_changed": evolution["candidate_changed"],
                "drift_detected": evolution["drift_detected"],
                "parent_qualification": {
                    "visible": _suite_summary(parent_visible_suite),
                    "locked": _suite_summary(parent_locked_suite),
                    "verdict": parent_locked["verdict"],
                },
                "parent_drift": _suite_summary(staged_suites["parent-drift"]),
                "candidate_acquisition": _suite_summary(staged_suites["candidate-acquisition"]),
                "candidate_drift": _suite_summary(staged_suites["candidate-drift"]),
            }
        else:
            parent_locked = evolution = None

    gates = [gate for suite in suites for condition in suite.conditions for gate in condition.gates]
    verifier_hashes = {gate.verifier_sha256 for gate in gates}
    simulator_hashes = {gate.simulator_sha256 for gate in gates}
    if len(verifier_hashes) != 1 or len(simulator_hashes) != 1:
        raise RuntimeError(f"runtime identity changed within publication replay: {skill.skill_id}")
    common_pass = (
        execution["verdict"] == "PASS"
        and visible_evidence["verdict"] == "PASS"
        and locked_result["verdict"] == "PASS"
    )
    staged_pass = skill.status != "simulation_staged" or (
        parent_locked is not None
        and evolution is not None
        and parent_locked["verdict"] == "PASS"
        and evolution["status"] == "STAGED"
    )
    record = {
        "schema_version": "proprio.skill_verification.v0.1",
        "skill_id": skill.skill_id,
        "qualification_status": skill.status,
        "runtime_kind": instrument_kind(skill.provider_instrument_id),
        "provider": inspection["provider"],
        "skill_sha256": hashlib.sha256(candidate.skill_md.encode()).hexdigest(),
        "code_sha256": hashlib.sha256(candidate.skill_py.encode()).hexdigest(),
        "source_sha256": candidate.source_sha256,
        "simulator_sha256": next(iter(simulator_hashes)),
        "verifier_sha256": next(iter(verifier_hashes)),
        "upstream_revision": inspection["upstream_revision"],
        "source_inspection": {
            "instrument_id": inspection["instrument_id"],
            "family": inspection["family"],
            "controller_methods": inspection["controller_methods"],
            "source_sha256": inspection["source_sha256"],
        },
        "candidate_execution": {
            "decision": execution["decision"],
            "verdict": execution["verdict"],
            "visible_evidence_read": visible_evidence["candidate_sha256"]
            == execution["candidate_sha256"],
        },
        "visible": _suite_summary(visible),
        "locked": _suite_summary(locked),
        "evolution": evolution_record,
        "verified_skill_claim": True,
        "hardware_validation_required": True,
        "claim_boundary": (
            "Staged in simulation. Hardware validation remains separate."
            if skill.status == "simulation_staged"
            else "Verified in simulation. Hardware validation remains separate."
        ),
        "verdict": "PASS" if common_pass and staged_pass else "FAIL",
    }
    return record


def build_skill_verification(root: Path, skill: PublishedSkill) -> dict[str, Any]:
    if skill.provider_instrument_id is None:
        raise ValueError(f"verified skill has no provider instrument: {skill.skill_id}")
    if not has_instrument(skill.provider_instrument_id):
        raise KeyError(skill.provider_instrument_id)
    definition = get_instrument_definition(skill.provider_instrument_id)
    if skill.status == "simulation_staged":
        if skill.parent_code_path is None:
            raise ValueError(f"staged skill has no reproducible parent: {skill.skill_id}")
        if not (root / skill.parent_code_path).is_file():
            raise FileNotFoundError(root / skill.parent_code_path)
        if not definition.evolution_conditions:
            raise ValueError(
                f"staged skill has no registered evolution conditions: {skill.skill_id}"
            )
    elif skill.parent_code_path is not None:
        raise ValueError(f"qualified skill cannot declare a staged parent: {skill.skill_id}")
    return _runtime_record(root, skill)


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
    skill_ids = [skill.skill_id for skill in PUBLISHED_SKILLS]
    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("published skill IDs must be unique")
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
    if publication["verdict"] != "PASS":
        failures = []
        for skill_id in publication["failed_skills"]:
            record = records[skill_id]
            stages = [
                f"execute={record.get('candidate_execution', {}).get('verdict', 'n/a')}",
                f"visible={record.get('visible', {}).get('verdict', 'n/a')}",
                f"locked={record.get('locked', {}).get('verdict', 'n/a')}",
            ]
            evolution = record.get("evolution")
            if evolution is not None:
                stages.append(f"evolution={evolution.get('status', 'n/a')}")
                stages.append(
                    f"parent={evolution.get('parent_qualification', {}).get('verdict', 'n/a')}"
                )
            failures.append(f"{skill_id} ({', '.join(stages)})")
        raise RuntimeError(
            "skill publication failed; no files were written: " + "; ".join(failures)
        )
    outputs = {
        root / "skills" / skill_id / "references/verification.json": record
        for skill_id, record in records.items()
    }
    outputs[root / "catalog.json"] = catalog
    originals = {path: path.read_bytes() if path.is_file() else None for path in outputs}
    replaced: list[Path] = []
    with tempfile.TemporaryDirectory(prefix=".proprio-publication-", dir=root) as temporary:
        staged_root = Path(temporary)
        staged = {}
        for index, (path, value) in enumerate(outputs.items()):
            staged_path = staged_root / f"{index:02d}.json"
            write_canonical_json(staged_path, value)
            staged[path] = staged_path
        try:
            for path, staged_path in staged.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged_path, path)
                replaced.append(path)
        except Exception:
            for path in reversed(replaced):
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                    continue
                rollback = staged_root / f"rollback-{len(replaced):02d}.json"
                rollback.write_bytes(original)
                os.replace(rollback, path)
            raise
    return publication
