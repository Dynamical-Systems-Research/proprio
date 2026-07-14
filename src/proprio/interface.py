"""Agent-neutral interface for simulator-verified instrument skills."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from proprio.artifacts import write_canonical_json
from proprio.catalog import parse_skill_markdown
from proprio.instrument_types import CandidatePackage
from proprio.instruments import INSTRUMENTS, evaluate_instrument_skill, load_instrument_source
from proprio.schema import canonical_json
from proprio.skill_search import DebugSuiteResult, evaluate_debug_suite


def _candidate_hash(candidate: CandidatePackage) -> str:
    return hashlib.sha256(candidate.skill_py.encode()).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _decision(verdict: str) -> str:
    return {"ADMIT": "PASS", "REJECT": "FAIL", "HOLD": "HOLD"}[verdict]


def _prepare_output(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"output directory is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _validate_candidate(candidate: CandidatePackage) -> None:
    if candidate.instrument_id not in INSTRUMENTS:
        raise KeyError(candidate.instrument_id)
    _, source_hash = load_instrument_source(candidate.instrument_id)
    if candidate.source_sha256 != source_hash:
        raise ValueError("candidate source hash does not match the current instrument source")
    parse_skill_markdown(candidate.skill_md)


def candidate_from_directory(
    instrument: str,
    directory: Path,
    *,
    agent: str = "external-agent",
) -> CandidatePackage:
    """Load the conventional SKILL.md and skill.py package produced by any agent."""

    source, source_hash = load_instrument_source(instrument)
    skill_md = (directory / "SKILL.md").read_text(encoding="utf-8")
    skill_py = (directory / "skill.py").read_text(encoding="utf-8")
    parse_skill_markdown(skill_md)
    provenance = hashlib.sha256(
        canonical_json(
            {
                "agent": agent,
                "instrument": instrument,
                "source_sha256": source_hash,
                "skill_md_sha256": hashlib.sha256(skill_md.encode()).hexdigest(),
                "skill_py_sha256": hashlib.sha256(skill_py.encode()).hexdigest(),
            }
        )
    ).hexdigest()
    return CandidatePackage(
        instrument_id=instrument,
        skill_md=skill_md,
        skill_py=skill_py,
        self_judgment={"verdict": "UNVERIFIED", "basis": ["external agent submission"]},
        source_sha256=source_hash,
        prompt_sha256=provenance,
        model=agent,
        raw_response={
            "origin": "external_agent_workspace",
            "prompt_captured": False,
            "source_bytes": len(source.encode()),
        },
    )


def inspect_source(instrument: str) -> dict[str, Any]:
    """Return the documentation and bounded controller surface for one instrument."""

    definition = INSTRUMENTS[instrument]
    source, source_hash = load_instrument_source(instrument)
    return {
        "schema_version": "proprio.source_inspection.v0.1",
        "instrument_id": instrument,
        "family": definition.family,
        "source": source,
        "source_sha256": source_hash,
        "controller_methods": sorted(definition.allowed_methods),
        "upstream_revision": definition.upstream_revision,
        "candidate_files": ["SKILL.md", "skill.py"],
        "skill_contract": {
            "skill_md": {
                "frontmatter_required": ["name", "description"],
                "frontmatter_optional": [],
                "additional_frontmatter": False,
                "instruction_body_required": True,
            },
            "skill_py": {
                "entrypoint": "run(controller)",
                "imports": False,
                "controller_calls_only": "controller methods plus bounded range(...) calls",
                "direct_controller_state_reads": False,
                "safe_state_access": "dictionary subscripts and membership or identity comparisons",
                "bounded_for_loops_only": "range(...) with literal integer bounds",
                "bounded_loop_control": ["break", "continue"],
                "maximum_loop_iterations": 16,
                "maximum_branch_depth": 4,
                "maximum_controller_calls": 96,
            },
        },
    }


def execute_candidate(
    instrument: str,
    candidate: CandidatePackage,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Execute a candidate on the visible conditions and persist the complete record."""

    if candidate.instrument_id != instrument:
        raise ValueError("candidate instrument does not match the requested instrument")
    _validate_candidate(candidate)
    definition = INSTRUMENTS[instrument]
    suite = evaluate_debug_suite(
        candidate,
        definition.visible_conditions,
        evaluator=evaluate_instrument_skill,
    )
    _prepare_output(output_dir)
    write_canonical_json(output_dir / "candidate.json", candidate)
    write_canonical_json(output_dir / "visible.json", suite)
    result = {
        "schema_version": "proprio.candidate_execution.v0.1",
        "instrument_id": instrument,
        "candidate_sha256": _candidate_hash(candidate),
        "visible_record": "visible.json",
        "decision": suite.verdict,
        "verdict": _decision(suite.verdict),
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result


def read_visible_evidence(run: Path) -> dict[str, Any]:
    """Read and validate the visible simulator evidence from a candidate execution."""

    candidate = CandidatePackage.model_validate(_read_object(run / "candidate.json"))
    suite = DebugSuiteResult.model_validate(_read_object(run / "visible.json"))
    if suite.instrument_id != candidate.instrument_id:
        raise ValueError("visible record belongs to a different instrument")
    if suite.candidate_sha256 != _candidate_hash(candidate):
        raise ValueError("visible record belongs to a different candidate")
    return {
        "schema_version": "proprio.visible_evidence.v0.1",
        "instrument_id": candidate.instrument_id,
        "candidate_sha256": suite.candidate_sha256,
        "decision": suite.verdict,
        "verdict": _decision(suite.verdict),
        "evidence": suite.model_dump(mode="json"),
    }


def verify_locked(
    candidate: CandidatePackage,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Replay visible behavior and evaluate the candidate on locked conditions."""

    _validate_candidate(candidate)
    definition = INSTRUMENTS[candidate.instrument_id]
    _prepare_output(output_dir)
    write_canonical_json(output_dir / "candidate.json", candidate)
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
    write_canonical_json(output_dir / "visible-replay.json", visible)
    write_canonical_json(output_dir / "locked.json", locked)
    if "HOLD" in {visible.verdict, locked.verdict}:
        decision = "HOLD"
    elif visible.verdict == locked.verdict == "ADMIT":
        decision = "ADMIT"
    else:
        decision = "REJECT"
    result = {
        "schema_version": "proprio.locked_verification.v0.1",
        "instrument_id": candidate.instrument_id,
        "candidate_sha256": _candidate_hash(candidate),
        "visible_verdict": visible.verdict,
        "locked_verdict": locked.verdict,
        "decision": decision,
        "verdict": _decision(decision),
        "hardware_validation_required": True,
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result


def stage_evolution(
    parent: CandidatePackage,
    candidate: CandidatePackage,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Stage a non-regressive candidate after registered simulated drift."""

    _validate_candidate(parent)
    _validate_candidate(candidate)
    if parent.instrument_id != candidate.instrument_id:
        raise ValueError("parent and candidate must target the same instrument")
    definition = INSTRUMENTS[parent.instrument_id]
    _prepare_output(output_dir)
    write_canonical_json(output_dir / "parent.json", parent)
    write_canonical_json(output_dir / "candidate.json", candidate)

    suites = {
        "parent-drift": evaluate_debug_suite(
            parent, definition.evolution_conditions, evaluator=evaluate_instrument_skill
        ),
        "candidate-acquisition": evaluate_debug_suite(
            candidate, definition.acquisition_conditions, evaluator=evaluate_instrument_skill
        ),
        "candidate-visible": evaluate_debug_suite(
            candidate, definition.visible_conditions, evaluator=evaluate_instrument_skill
        ),
        "candidate-drift": evaluate_debug_suite(
            candidate, definition.evolution_conditions, evaluator=evaluate_instrument_skill
        ),
        "candidate-locked": evaluate_debug_suite(
            candidate, definition.locked_conditions, evaluator=evaluate_instrument_skill
        ),
    }
    for name, suite in suites.items():
        write_canonical_json(output_dir / f"{name}.json", suite)

    drift_detected = suites["parent-drift"].verdict == "REJECT"
    candidate_changed = _candidate_hash(parent) != _candidate_hash(candidate)
    candidate_verdicts = {
        name: suite.verdict for name, suite in suites.items() if name != "parent-drift"
    }
    if any(suite.verdict == "HOLD" for suite in suites.values()) or not drift_detected:
        status = "HOLD"
    elif drift_detected and candidate_changed and set(candidate_verdicts.values()) == {"ADMIT"}:
        status = "STAGED"
    else:
        status = "REJECTED"
    result = {
        "schema_version": "proprio.evolution_staging.v0.1",
        "instrument_id": parent.instrument_id,
        "parent_sha256": _candidate_hash(parent),
        "candidate_sha256": _candidate_hash(candidate),
        "candidate_changed": candidate_changed,
        "drift_detected": drift_detected,
        "candidate_verdicts": candidate_verdicts,
        "status": status,
        "reason": {
            "STAGED": "drift detected and the changed candidate passed every replay",
            "REJECTED": "the changed candidate did not pass every replay",
            "HOLD": "registered drift did not invalidate the parent or evidence was unavailable",
        }[status],
        "verdict": {"STAGED": "PASS", "REJECTED": "FAIL", "HOLD": "HOLD"}[status],
        "hardware_validation_required": True,
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result
