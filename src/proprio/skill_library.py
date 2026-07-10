"""Package simulation-qualified model-authored skills into the public catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from proprio.artifacts import write_bytes, write_canonical_json
from proprio.catalog import validate_catalog
from proprio.confirmatory_qualification import CONFIRMATORY_FAMILIES
from proprio.confirmatory_study import summarize_confirmatory_study
from proprio.instrument_types import EvolutionProposal, RepairEpisode
from proprio.microscopy import INSTRUMENT_ID as MICROSCOPY_INSTRUMENT_ID
from proprio.microscopy_evolution import summarize_microscopy_evolution


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path must be inside repository root: {path}") from exc


def package_confirmatory_skills(
    cassette_dir: Path,
    root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Publish only candidates that cleared hard, provenance, and semantic gates."""

    summary = summarize_confirmatory_study(cassette_dir)
    write_canonical_json(cassette_dir / "summary.json", summary)
    if summary["verdict"] != "PASS":
        raise ValueError("confirmatory study has not passed every claim gate")

    truthful = {
        row["instrument_id"]: row for row in summary["rows"] if row["feedback_arm"] == "truthful"
    }
    instrument_ids = tuple(sorted(CONFIRMATORY_FAMILIES))
    if set(truthful) != set(instrument_ids):
        raise ValueError("confirmatory study is missing one or more truthful episodes")

    catalog_path = root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    retained = [entry for entry in catalog["skills"] if entry["id"] not in instrument_ids]
    artifact_path = _relative(cassette_dir / "summary.json", root)
    packaged: list[dict[str, Any]] = []

    for instrument_id in instrument_ids:
        row = truthful[instrument_id]
        if not (
            row["admission_qualified"]
            and row["provenance_complete"]
            and row["semantic_review_status"] == "completed"
            and row["semantic_verdict"] == "ACCEPT"
        ):
            raise ValueError(f"candidate is not simulation-qualified: {instrument_id}")

        episode_path = cassette_dir / instrument_id / "repair-truthful.json"
        episode = RepairEpisode.model_validate_json(episode_path.read_text(encoding="utf-8"))
        candidate = episode.final_candidate
        skill_dir = root / "skills" / "simulated" / instrument_id
        skill_ref = write_bytes(
            skill_dir / "SKILL.md",
            candidate.skill_md.rstrip().encode("utf-8") + b"\n",
            "text/markdown",
        )
        code_ref = write_bytes(
            skill_dir / "skill.py",
            candidate.skill_py.rstrip().encode("utf-8") + b"\n",
            "text/x-python",
        )
        packaged.append(
            {
                "id": instrument_id,
                "version": "0.1.0",
                "instrument": instrument_id.replace("-", " "),
                "path": _relative(skill_dir / "SKILL.md", root),
                "code_path": _relative(skill_dir / "skill.py", root),
                "status": "simulation_qualified",
                "hardware_qualification_required": True,
                "verification": {
                    "artifact": artifact_path,
                    "artifact_verdict": "PASS",
                    "skill_sha256": skill_ref.sha256,
                    "code_sha256": code_ref.sha256,
                    "verifier_sha256": episode.final_gate.verifier_sha256,
                    "source_sha256": candidate.source_sha256,
                },
            }
        )

    catalog["skills"] = [*retained, *packaged]
    write_canonical_json(catalog_path, catalog)
    validate_catalog(root)
    result = {
        "schema_version": "proprio.skill_library_package.v0.1",
        "verdict": "PASS",
        "packaged_skills": len(packaged),
        "hardware_qualification_required": True,
        "catalog": _relative(catalog_path, root),
        "skills": packaged,
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result


def package_microscopy_skill(
    evolution_dir: Path,
    root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Publish only the staged, simulation-qualified microscope proposal."""

    summary = summarize_microscopy_evolution(evolution_dir)
    if summary["verdict"] != "PASS":
        raise ValueError("microscope evolution has not passed every release gate")
    proposal = EvolutionProposal.model_validate_json(
        (evolution_dir / "evolution.json").read_text(encoding="utf-8")
    )
    if proposal.status != "STAGED" or not proposal.lineage.hardware_gate_required:
        raise ValueError("microscope proposal is not eligible for simulation-only packaging")
    candidate = proposal.proposed_candidate
    if candidate.instrument_id != MICROSCOPY_INSTRUMENT_ID:
        raise ValueError("evolution artifact does not contain the microscope skill")

    skill_dir = root / "skills" / "simulated" / MICROSCOPY_INSTRUMENT_ID
    skill_ref = write_bytes(
        skill_dir / "SKILL.md",
        candidate.skill_md.rstrip().encode("utf-8") + b"\n",
        "text/markdown",
    )
    code_ref = write_bytes(
        skill_dir / "skill.py",
        candidate.skill_py.rstrip().encode("utf-8") + b"\n",
        "text/x-python",
    )
    entry = {
        "id": MICROSCOPY_INSTRUMENT_ID,
        "version": "0.1.0",
        "instrument": "OpenFlexure simulated microscope autofocus",
        "path": _relative(skill_dir / "SKILL.md", root),
        "code_path": _relative(skill_dir / "skill.py", root),
        "status": "simulation_qualified",
        "hardware_qualification_required": True,
        "verification": {
            "artifact": _relative(evolution_dir / "summary.json", root),
            "artifact_verdict": "PASS",
            "skill_sha256": skill_ref.sha256,
            "code_sha256": code_ref.sha256,
            "verifier_sha256": proposal.qualification[-1].verifier_sha256,
            "source_sha256": candidate.source_sha256,
        },
    }
    catalog_path = root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["skills"] = [
        *[item for item in catalog["skills"] if item["id"] != MICROSCOPY_INSTRUMENT_ID],
        entry,
    ]
    write_canonical_json(catalog_path, catalog)
    validate_catalog(root)
    result = {
        "schema_version": "proprio.microscopy_skill_package.v0.1",
        "verdict": "PASS",
        "packaged_skills": 1,
        "hardware_qualification_required": True,
        "catalog": _relative(catalog_path, root),
        "skill": entry,
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result
