"""Live drift qualification for the externally simulated microscope skill."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import source_sha256, write_canonical_json
from proprio.instrument_agent import (
    DISCLOSED_EXECUTOR_CONTRACT,
    HISTORY_REPLAY_CONTRACT,
    INDEPENDENT_REVIEWER_SYSTEM_PROMPT,
    SKILL_ENGINEER_SYSTEM_PROMPT,
    InstrumentSkillAgent,
)
from proprio.instrument_study import _repair_protocol_evidence, _response_transport_evidence
from proprio.instrument_types import (
    CandidatePackage,
    CandidateSelectionSeal,
    EvolutionProposal,
    FeedbackArm,
    HybridVerdict,
    JudgeEpisode,
    LockedConditionResult,
    LockedValidationReport,
    RepairEpisode,
    SimulationScenario,
)
from proprio.microscopy import (
    FAMILY,
    INSTRUMENT_ID,
    evaluate_live_microscopy_skill,
    load_microscopy_source,
)
from proprio.policy import OPENROUTER_BASE_URL, DSV4Client
from proprio.schema import canonical_json
from proprio.skill_evolution import stage_skill_evolution

PREREGISTRATION = Path(__file__).with_name("data") / "expanded-confirmatory-preregistration.yaml"


def _object_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _candidate_hash(candidate: CandidatePackage) -> str:
    return hashlib.sha256(candidate.skill_py.encode()).hexdigest()


def _history_replayed_after_latest_repair(events: tuple[dict[str, Any], ...]) -> bool:
    submission_indexes = [
        index
        for index, event in enumerate(events)
        if event.get("name") == "submit_repair"
        and event.get("result", {}).get("status") == "captured"
    ]
    last_submission = max(submission_indexes, default=-1)
    return any(
        index > last_submission
        and event.get("name") == "run_history"
        and event.get("result", {}).get("all_admit") is True
        for index, event in enumerate(events)
    )


def generate_microscopy_evolution_conditions() -> tuple[dict[str, Any], ...]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    config = prereg["microscopy_evolution"]["locked_validation"]
    count = int(config["cases"])
    minimum = float(config["start_z_min"])
    maximum = float(config["start_z_max"])
    seed = int(config["seed"])
    rows = []
    for index in range(count):
        digest = hashlib.sha256(f"{seed}:{INSTRUMENT_ID}:{index}".encode()).hexdigest()
        fraction = int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
        value = minimum + (maximum - minimum) * fraction
        rows.append(
            {
                "condition_id": f"condition_{digest[:20]}",
                "index": index,
                "parameter": "start_z",
                "value": round(value, 6),
            }
        )
    return tuple(rows)


def seal_microscopy_evolution_candidate(candidate: CandidatePackage) -> CandidateSelectionSeal:
    return CandidateSelectionSeal(
        instrument_id=INSTRUMENT_ID,
        candidate_sha256=_candidate_hash(candidate),
        source_sha256=candidate.source_sha256,
        model=candidate.model,
        validation_preregistration_sha256=source_sha256(PREREGISTRATION),
    )


def evaluate_microscopy_evolution_locked(
    candidate: CandidatePackage,
    seal: CandidateSelectionSeal,
    *,
    base_url: str,
) -> LockedValidationReport:
    if seal != seal_microscopy_evolution_candidate(candidate):
        raise ValueError("candidate does not match the microscopy evolution selection seal")
    conditions = generate_microscopy_evolution_conditions()
    cases = tuple(
        LockedConditionResult(
            **condition,
            gate=evaluate_live_microscopy_skill(
                INSTRUMENT_ID,
                candidate.skill_py,
                scenario=SimulationScenario.DRIFT,
                condition={"start_z": condition["value"]},
                base_url=base_url,
            ),
        )
        for condition in conditions
    )
    passed = sum(case.gate.verdict == "ADMIT" for case in cases)
    return LockedValidationReport(
        instrument_id=INSTRUMENT_ID,
        candidate_sha256=seal.candidate_sha256,
        selection_seal_sha256=_object_hash(seal),
        validation_preregistration_sha256=seal.validation_preregistration_sha256,
        suite_sha256=_object_hash(conditions),
        cases=cases,
        passed_cases=passed,
        verdict="PASS" if passed == len(cases) else "FAIL",
    )


def stage_microscopy_evolution(
    parent: CandidatePackage,
    repair: RepairEpisode,
    judge: JudgeEpisode,
    locked: LockedValidationReport,
    *,
    evaluator: Any,
) -> EvolutionProposal:
    """Apply the common gate plus the microscope evolution history requirement."""

    proposal = stage_skill_evolution(
        parent,
        repair,
        judge,
        locked,
        evaluator=evaluator,
    )
    if _history_replayed_after_latest_repair(repair.tool_events):
        return proposal
    return proposal.model_copy(
        update={
            "status": "REJECTED",
            "reason": "historical behavior was not replayed after the latest repair",
            "hybrid_verdict": HybridVerdict(
                verdict="REJECT",
                hard_verdict="REJECT",
                judge_verdict=proposal.hybrid_verdict.judge_verdict,
                reason="historical replay is a deterministic promotion requirement",
            ),
        }
    )


def _select_parent(replication_root: Path) -> tuple[str, CandidatePackage]:
    directory = replication_root / INSTRUMENT_ID
    for replicate in range(10):
        prefix = directory / f"replicate-{replicate:02d}"
        repair_path = prefix / "repair.json"
        validation_path = prefix / "validation.json"
        if not repair_path.is_file() or not validation_path.is_file():
            continue
        repair = json.loads(repair_path.read_text(encoding="utf-8"))
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        if (
            repair.get("agent_status") == "CANDIDATE"
            and repair.get("final_gate", {}).get("verdict") == "ADMIT"
            and validation.get("verdict") == "PASS"
        ):
            return f"replicate-{replicate:02d}", CandidatePackage.model_validate(
                repair["final_candidate"]
            )
    raise RuntimeError("no qualified microscope replication candidate is available")


def summarize_microscopy_evolution(root: Path) -> dict[str, Any]:
    proposal_path = root / "evolution.json"
    if not proposal_path.is_file():
        raise FileNotFoundError(proposal_path)
    proposal = EvolutionProposal.model_validate_json(proposal_path.read_text(encoding="utf-8"))
    protocol = _repair_protocol_evidence(proposal.repair_episode)
    responses = [
        *proposal.repair_episode.raw_responses,
        *proposal.judge_episode.raw_responses,
    ]
    history_replayed = _history_replayed_after_latest_repair(proposal.repair_episode.tool_events)
    transport = _response_transport_evidence(responses)
    result = {
        "schema_version": "proprio.microscopy_evolution_summary.v0.1",
        "instrument_id": proposal.instrument_id,
        "family": proposal.family,
        "parent_replicate": json.loads((root / "parent.json").read_text())["replicate"],
        "drift_detected": proposal.drift_detection.verdict == "REJECT",
        "repair_status": proposal.repair_episode.agent_status,
        "changed_condition_passed": proposal.repair_episode.final_gate.verdict == "ADMIT",
        "historical_replay_complete": history_replayed,
        "feedback_inspected_before_repair": protocol["feedback_inspected_before_repair"],
        "repair_evidence_grounded": protocol["repair_evidence_grounded"],
        "replayed_after_repair": protocol["replayed_after_repair"],
        "locked_validation_verdict": proposal.locked_validation.verdict,
        "locked_validation_cases": len(proposal.locked_validation.cases),
        "independent_reviewer_verdict": proposal.hybrid_verdict.judge_verdict,
        "status": proposal.status,
        "hardware_gate_required": proposal.lineage.hardware_gate_required,
        "parent_skill_sha256": proposal.lineage.parent_skill_sha256,
        "proposal_skill_sha256": proposal.lineage.proposal_skill_sha256,
        "parent_immutable": (
            proposal.lineage.parent_skill_sha256 == proposal.lineage.rollback_skill_sha256
            and proposal.parent_candidate.skill_py != proposal.proposed_candidate.skill_py
        ),
        "transport": transport,
    }
    passed = (
        result["drift_detected"]
        and result["repair_status"] == "CANDIDATE"
        and result["changed_condition_passed"]
        and result["historical_replay_complete"]
        and result["feedback_inspected_before_repair"]
        and result["repair_evidence_grounded"]
        and result["replayed_after_repair"]
        and result["locked_validation_verdict"] == "PASS"
        and result["independent_reviewer_verdict"] == "ACCEPT"
        and result["status"] == "STAGED"
        and result["hardware_gate_required"]
        and result["parent_immutable"]
    )
    result["verdict"] = "PASS" if passed else "FAIL"
    write_canonical_json(root / "summary.json", result)
    return result


def replay_microscopy_evolution(root: Path, output_dir: Path) -> dict[str, Any]:
    """Validate the captured proposal and reproduce its canonical bytes offline."""

    proposal_path = root / "evolution.json"
    proposal = EvolutionProposal.model_validate_json(proposal_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    write_canonical_json(output_dir / "evolution.json", proposal)
    identical = (output_dir / "evolution.json").read_bytes() == proposal_path.read_bytes()
    summary = summarize_microscopy_evolution(root)
    result = {
        "schema_version": "proprio.microscopy_evolution_replay.v0.1",
        "canonical_record_identical": identical,
        "captured_summary_verdict": summary["verdict"],
        "verdict": "PASS" if identical and summary["verdict"] == "PASS" else "FAIL",
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result


def run_live_microscopy_evolution(
    replication_root: Path,
    output_dir: Path,
    *,
    base_url: str,
) -> dict[str, Any]:
    """Detect drift, repair with DSV4, and stage only a fully gated proposal."""

    output_dir.mkdir(parents=True, exist_ok=True)
    parent_replicate, parent = _select_parent(replication_root)
    write_canonical_json(
        output_dir / "parent.json",
        {"replicate": parent_replicate, "candidate": parent},
    )

    def evaluator(instrument_id: str, source: str, **kwargs: Any) -> Any:
        return evaluate_live_microscopy_skill(
            instrument_id,
            source,
            base_url=base_url,
            **kwargs,
        )

    dsv4 = DSV4Client()
    repair_agent = InstrumentSkillAgent(
        client=dsv4,
        skill_system_prompt=(
            SKILL_ENGINEER_SYSTEM_PROMPT + DISCLOSED_EXECUTOR_CONTRACT + HISTORY_REPLAY_CONTRACT
        ),
        source_loader=load_microscopy_source,
        evaluator=evaluator,
        families={INSTRUMENT_ID: FAMILY},
    )
    write_canonical_json(output_dir / "dsv4-health.json", dsv4.health())
    repair = repair_agent.repair(
        parent,
        feedback_arm=FeedbackArm.TRUTHFUL,
        scenario=SimulationScenario.DRIFT,
        require_history=True,
        history_scenarios=(SimulationScenario.NOMINAL, SimulationScenario.REPAIR),
        max_turns=18,
    )
    write_canonical_json(output_dir / "repair.json", repair)

    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for independent review")
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    config = prereg["independent_reviewer"]
    qwen = DSV4Client(
        base_url=OPENROUTER_BASE_URL,
        api_key=api_key,
        model=config["model"],
        provider=config["provider"],
        reasoning_effort=config["reasoning_effort"],
        include_reasoning=True,
    )
    judge_agent = InstrumentSkillAgent(
        client=qwen,
        source_loader=load_microscopy_source,
        evaluator=evaluator,
        families={INSTRUMENT_ID: FAMILY},
        judge_system_prompt=INDEPENDENT_REVIEWER_SYSTEM_PROMPT,
        sampling_temperature=config["temperature"],
        sampling_seed=880_739,
    )
    write_canonical_json(output_dir / "reviewer-health.json", qwen.health())
    judge = judge_agent.judge(repair)
    write_canonical_json(output_dir / "review.json", judge)

    seal = seal_microscopy_evolution_candidate(repair.final_candidate)
    write_canonical_json(output_dir / "selection-seal.json", seal)
    locked = evaluate_microscopy_evolution_locked(
        repair.final_candidate,
        seal,
        base_url=base_url,
    )
    write_canonical_json(output_dir / "locked-validation.json", locked)
    proposal = stage_microscopy_evolution(
        parent,
        repair,
        judge,
        locked,
        evaluator=evaluator,
    )
    write_canonical_json(output_dir / "evolution.json", proposal)
    return summarize_microscopy_evolution(output_dir)
