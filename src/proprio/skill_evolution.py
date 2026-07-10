"""Detect simulated drift and stage independently qualified skill evolution proposals."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import write_bytes, write_canonical_json
from proprio.instrument_agent import (
    DISCLOSED_EXECUTOR_CONTRACT,
    HISTORY_REPLAY_CONTRACT,
    SKILL_ENGINEER_SYSTEM_PROMPT,
    DSV4InstrumentAgent,
)
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_study import _repair_protocol_evidence, _response_transport_evidence
from proprio.instrument_types import (
    CandidatePackage,
    EvolutionLineage,
    EvolutionProposal,
    FeedbackArm,
    HardGateResult,
    HybridVerdict,
    JudgeEpisode,
    LockedValidationReport,
    RepairEpisode,
    SimulationScenario,
    effective_judge_verdict,
)
from proprio.locked_validation import run_locked_validation_once, seal_candidate
from proprio.reference_instruments import INSTRUMENTS
from proprio.schema import canonical_json

PREREGISTRATION = Path(__file__).with_name("data") / "skill-evolution-preregistration.yaml"
INSTRUMENT_IDS = tuple(sorted(INSTRUMENTS))


def _gate_hash(gate: HardGateResult) -> str:
    return hashlib.sha256(canonical_json(gate.model_dump(mode="json"))).hexdigest()


def _candidate_hash(candidate: CandidatePackage) -> str:
    return hashlib.sha256(candidate.skill_py.encode()).hexdigest()


def _qualification_verdict(gates: tuple[HardGateResult, ...]) -> str:
    if any(gate.verdict == "REJECT" for gate in gates):
        return "REJECT"
    if any(gate.verdict == "HOLD" for gate in gates):
        return "HOLD"
    return "ADMIT"


def _hybrid_for_qualification(
    hard_verdict: str,
    judge: JudgeEpisode,
) -> HybridVerdict:
    review = judge.review if judge.status == "completed" else None
    judge_verdict = effective_judge_verdict(review)
    if hard_verdict == "REJECT":
        return HybridVerdict(
            verdict="REJECT",
            hard_verdict="REJECT",
            judge_verdict=judge_verdict,
            reason="one or more independent qualification scenarios rejected the proposal",
        )
    if hard_verdict == "HOLD":
        return HybridVerdict(
            verdict="HOLD",
            hard_verdict="HOLD",
            judge_verdict=judge_verdict,
            reason="qualification evidence is unavailable",
        )
    if review is None:
        return HybridVerdict(
            verdict="HOLD",
            hard_verdict="ADMIT",
            judge_verdict=None,
            reason="stateful semantic review is unavailable",
        )
    if judge_verdict == "REJECT":
        return HybridVerdict(
            verdict="REJECT",
            hard_verdict="ADMIT",
            judge_verdict="REJECT",
            reason="stateful semantic review found a critical defect",
        )
    if judge_verdict == "HOLD":
        return HybridVerdict(
            verdict="HOLD",
            hard_verdict="ADMIT",
            judge_verdict="HOLD",
            reason="stateful semantic review found insufficient evidence",
        )
    return HybridVerdict(
        verdict="ADMIT",
        hard_verdict="ADMIT",
        judge_verdict="ACCEPT",
        reason="all independent scenarios passed and semantic review found no critical defect",
    )


def stage_skill_evolution(
    parent: CandidatePackage,
    repair: RepairEpisode,
    judge: JudgeEpisode,
    locked_validation: LockedValidationReport,
    *,
    evaluator: Callable[..., HardGateResult] = evaluate_instrument_skill,
) -> EvolutionProposal:
    """Stage a proposal without mutating the admitted parent or bypassing hardware review."""

    if repair.instrument_id != parent.instrument_id or judge.instrument_id != parent.instrument_id:
        raise ValueError("evolution artifacts must refer to the same instrument")
    if _candidate_hash(repair.initial_candidate) != _candidate_hash(parent):
        raise ValueError("repair episode does not start from the declared parent")
    if repair.scenario not in {SimulationScenario.DRIFT, SimulationScenario.UNAVAILABLE}:
        raise ValueError("evolution requires drift or unavailable simulation evidence")

    baseline = tuple(
        evaluator(parent.instrument_id, parent.skill_py, scenario=scenario)
        for scenario in (SimulationScenario.NOMINAL, SimulationScenario.REPAIR)
    )
    drift_detection = repair.initial_gate
    proposed = repair.final_candidate
    proposed_hash = _candidate_hash(proposed)
    if locked_validation.instrument_id != parent.instrument_id:
        raise ValueError("locked validation refers to a different instrument")
    if locked_validation.candidate_sha256 != proposed_hash:
        raise ValueError("locked validation does not bind the proposed candidate")
    qualification = tuple(
        evaluator(parent.instrument_id, proposed.skill_py, scenario=scenario)
        for scenario in (
            SimulationScenario.NOMINAL,
            SimulationScenario.REPAIR,
            SimulationScenario.DRIFT,
        )
    )
    hard_verdict = _qualification_verdict(qualification)
    if locked_validation.verdict == "FAIL":
        hard_verdict = "REJECT"
    protocol = _repair_protocol_evidence(repair)
    provenance_complete = (
        repair.feedback_arm is FeedbackArm.TRUTHFUL
        and protocol["feedback_inspected_before_repair"]
        and protocol["repair_evidence_grounded"]
        and protocol["replayed_after_repair"]
    )
    if not provenance_complete:
        hard_verdict = "REJECT"
    hybrid = _hybrid_for_qualification(hard_verdict, judge)

    if _qualification_verdict(baseline) != "ADMIT":
        status = "REJECTED"
        reason = "parent was not qualified across the pre-drift baseline"
    elif drift_detection.verdict == "HOLD":
        status = "HOLD"
        reason = "drift evidence is unavailable"
    elif drift_detection.verdict == "ADMIT":
        status = "HOLD"
        reason = "no drift failure was detected; evolution is not justified"
    elif not provenance_complete:
        status = "REJECTED"
        reason = "repair provenance did not prove inspect, grounded edit, and replay"
    elif hybrid.verdict == "ADMIT":
        status = "STAGED"
        reason = (
            "drift was detected and the proposal passed development replay plus locked "
            "simulation qualification"
        )
    elif hybrid.verdict == "REJECT":
        status = "REJECTED"
        reason = hybrid.reason
    else:
        status = "HOLD"
        reason = hybrid.reason

    evidence = (
        *baseline,
        drift_detection,
        *qualification,
        *(case.gate for case in locked_validation.cases),
    )
    lineage = EvolutionLineage(
        parent_skill_sha256=_candidate_hash(parent),
        proposal_skill_sha256=proposed_hash,
        rollback_skill_sha256=_candidate_hash(parent),
        source_sha256=parent.source_sha256,
        simulator_sha256=qualification[-1].simulator_sha256,
        verifier_sha256=qualification[-1].verifier_sha256,
        validation_preregistration_sha256=(locked_validation.validation_preregistration_sha256),
        validation_suite_sha256=locked_validation.suite_sha256,
        evidence_sha256=tuple(_gate_hash(gate) for gate in evidence),
    )
    return EvolutionProposal(
        instrument_id=parent.instrument_id,
        family=repair.family,
        status=status,
        reason=reason,
        parent_candidate=parent,
        proposed_candidate=proposed,
        baseline_qualification=baseline,
        drift_detection=drift_detection,
        qualification=qualification,
        locked_validation=locked_validation,
        repair_episode=repair,
        judge_episode=judge,
        hybrid_verdict=hybrid,
        lineage=lineage,
    )


def _proposal_path(root: Path, instrument_id: str) -> Path:
    return root / instrument_id / "evolution.json"


def run_live_evolution_study(
    study_cassette_dir: Path,
    output_dir: Path,
    *,
    instrument_ids: tuple[str, ...] = INSTRUMENT_IDS,
) -> dict[str, Any]:
    """Capture live DSV4 drift repairs and stage only independently qualified proposals."""

    output_dir.mkdir(parents=True, exist_ok=True)
    agent = DSV4InstrumentAgent(
        skill_system_prompt=(
            SKILL_ENGINEER_SYSTEM_PROMPT + DISCLOSED_EXECUTOR_CONTRACT + HISTORY_REPLAY_CONTRACT
        )
    )
    write_canonical_json(output_dir / "health.json", agent.client.health())
    for instrument_id in instrument_ids:
        path = _proposal_path(output_dir, instrument_id)
        if path.is_file():
            continue
        repair_path = study_cassette_dir / instrument_id / "repair-truthful.json"
        if not repair_path.is_file():
            raise FileNotFoundError(f"missing truthful repair cassette: {repair_path}")
        prior = RepairEpisode.model_validate_json(repair_path.read_text(encoding="utf-8"))
        parent = prior.final_candidate
        repair = agent.repair(
            parent,
            feedback_arm=FeedbackArm.TRUTHFUL,
            scenario=SimulationScenario.DRIFT,
            require_history=True,
            max_turns=18,
        )
        judge = agent.judge(repair)
        seal_path = path.parent / "selection-seal.json"
        validation_path = path.parent / "locked-validation.json"
        if validation_path.is_file():
            locked_validation = LockedValidationReport.model_validate_json(
                validation_path.read_text(encoding="utf-8")
            )
            expected_seal = seal_candidate(repair.final_candidate)
            if locked_validation.candidate_sha256 != expected_seal.candidate_sha256:
                raise ValueError("captured locked validation belongs to a different candidate")
        else:
            locked_validation = run_locked_validation_once(
                repair.final_candidate,
                seal_path,
                validation_path,
            )
        write_canonical_json(
            path,
            stage_skill_evolution(parent, repair, judge, locked_validation),
        )

    summary = summarize_evolution_study(output_dir, instrument_ids=instrument_ids)
    write_canonical_json(output_dir / "summary.json", summary)
    _write_report(output_dir / "report.md", summary)
    return summary


def _load_proposal(path: Path) -> EvolutionProposal:
    return EvolutionProposal.model_validate_json(path.read_text(encoding="utf-8"))


def summarize_evolution_study(
    root: Path,
    *,
    instrument_ids: tuple[str, ...] = INSTRUMENT_IDS,
) -> dict[str, Any]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    requested_models: set[str] = set()
    for instrument_id in instrument_ids:
        path = _proposal_path(root, instrument_id)
        if not path.is_file():
            continue
        proposal = _load_proposal(path)
        requested_models.add(proposal.proposed_candidate.model)
        responses.extend(proposal.repair_episode.raw_responses)
        responses.extend(proposal.judge_episode.raw_responses)
        baseline_passed = all(gate.verdict == "ADMIT" for gate in proposal.baseline_qualification)
        qualified = all(gate.verdict == "ADMIT" for gate in proposal.qualification)
        locked_validation_passed = proposal.locked_validation.verdict == "PASS"
        judge_accepted = effective_judge_verdict(proposal.judge_episode.review) == "ACCEPT"
        protocol = _repair_protocol_evidence(proposal.repair_episode)
        provenance_complete = (
            proposal.repair_episode.feedback_arm is FeedbackArm.TRUTHFUL
            and protocol["feedback_inspected_before_repair"]
            and protocol["repair_evidence_grounded"]
            and protocol["replayed_after_repair"]
        )
        unsafe = proposal.status == "STAGED" and not (
            baseline_passed
            and proposal.drift_detection.verdict == "REJECT"
            and qualified
            and locked_validation_passed
            and judge_accepted
            and provenance_complete
            and proposal.lineage.hardware_gate_required
        )
        rows.append(
            {
                "instrument_id": instrument_id,
                "family": proposal.family,
                "baseline_passed": baseline_passed,
                "drift_detected": proposal.drift_detection.verdict == "REJECT",
                "proposal_qualified": qualified,
                "locked_validation_passed": locked_validation_passed,
                "locked_validation_cases": len(proposal.locked_validation.cases),
                "judge_verdict": (
                    proposal.judge_episode.review.verdict
                    if proposal.judge_episode.review is not None
                    else None
                ),
                "provenance_complete": provenance_complete,
                **protocol,
                "status": proposal.status,
                "unsafe_promotion": unsafe,
                "hardware_gate_required": proposal.lineage.hardware_gate_required,
                "parent_skill_sha256": proposal.lineage.parent_skill_sha256,
                "proposal_skill_sha256": proposal.lineage.proposal_skill_sha256,
            }
        )

    baseline_valid = [row for row in rows if row["baseline_passed"]]
    eligible = [row for row in baseline_valid if row["drift_detected"]]
    staged = [row for row in eligible if row["status"] == "STAGED"]
    rate = len(staged) / len(eligible) if eligible else 0.0
    unsafe_promotions = sum(row["unsafe_promotion"] for row in rows)
    metrics = prereg["metrics"]
    expected = prereg["reproducibility"]
    transport = _response_transport_evidence(responses)
    providers = transport["providers"]
    resolved_models = transport["resolved_models"]
    reasoning_missing = transport["reasoning_state_missing"]
    live_capture = expected["live_model"] in requested_models
    route_gate = (
        requested_models == {expected["live_model"]}
        and providers == [expected["provider"]]
        and resolved_models == [expected["resolved_model_revision"]]
        and bool(responses)
        and reasoning_missing == 0
    )
    claim_gates = {
        "drift_detection": (
            "PASS" if baseline_valid and len(eligible) == len(baseline_valid) else "FAIL"
        ),
        "invalid_parent_protection": (
            "PASS"
            if rows and all(row["baseline_passed"] or row["status"] != "STAGED" for row in rows)
            else "FAIL"
        ),
        "validated_evolution": (
            "PASS" if rate >= metrics["drift_evolution_repairable_rate_min"] else "FAIL"
        ),
        "unsafe_promotion_prevention": (
            "PASS" if unsafe_promotions <= metrics["drift_unsafe_promotions_max"] else "FAIL"
        ),
        "hardware_qualification_boundary": (
            "PASS" if rows and all(row["hardware_gate_required"] for row in rows) else "FAIL"
        ),
    }
    if live_capture:
        claim_gates["frozen_model_route"] = "PASS" if route_gate else "FAIL"
    result = {
        "schema_version": "proprio.evolution_study.v0.2",
        "instrument_count": len(rows),
        "family_count": len({row["family"] for row in rows}),
        "eligible_drift_cases": len(eligible),
        "baseline_invalid_cases": len(rows) - len(baseline_valid),
        "staged_proposals": len(staged),
        "validated_evolution_rate": rate,
        "unsafe_promotions": unsafe_promotions,
        "capture_mode": "live" if live_capture else "fixture",
        "requested_models": sorted(requested_models),
        "transport_evidence": transport,
        "rows": rows,
        "claim_gates": claim_gates,
    }
    result["verdict"] = "PASS" if all(value == "PASS" for value in claim_gates.values()) else "FAIL"
    return result


def replay_evolution_study(
    cassette_dir: Path,
    output_dir: Path,
    *,
    instrument_ids: tuple[str, ...] = INSTRUMENT_IDS,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for instrument_id in instrument_ids:
        path = _proposal_path(cassette_dir, instrument_id)
        if not path.is_file():
            continue
        captured = _load_proposal(path)
        replayed = stage_skill_evolution(
            captured.parent_candidate,
            captured.repair_episode,
            captured.judge_episode,
            captured.locked_validation,
        )
        rows.append(
            {
                "instrument_id": instrument_id,
                "captured_status": captured.status,
                "replayed_status": replayed.status,
                "byte_identical": canonical_json(captured.model_dump(mode="json"))
                == canonical_json(replayed.model_dump(mode="json")),
            }
        )
    result = {
        "schema_version": "proprio.evolution_replay.v0.2",
        "episodes": len(rows),
        "identical": sum(row["byte_identical"] for row in rows),
        "rows": rows,
    }
    result["verdict"] = "PASS" if rows and all(row["byte_identical"] for row in rows) else "FAIL"
    write_canonical_json(output_dir / "summary.json", result)
    return result


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Simulated deployment-drift evolution study",
        "",
        f"Overall verdict: **{summary['verdict']}**",
        "",
        f"Detected eligible drift cases: {summary['eligible_drift_cases']}",
        f"Staged proposals: {summary['staged_proposals']}",
        f"Validated evolution rate: {summary['validated_evolution_rate']:.3f}",
        f"Unsafe promotions: {summary['unsafe_promotions']}",
        "",
        "Every staged proposal remains blocked on a separate real-hardware qualification gate.",
        "",
        "## Claim gates",
        "",
    ]
    lines.extend(
        f"- {name.replace('_', ' ')}: **{verdict}**"
        for name, verdict in summary["claim_gates"].items()
    )
    write_bytes(path, ("\n".join(lines) + "\n").encode(), "text/markdown")
