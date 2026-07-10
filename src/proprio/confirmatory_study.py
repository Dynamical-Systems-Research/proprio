"""Frozen confirmatory study across instrument families absent from method development."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import write_canonical_json
from proprio.confirmatory_instruments import CONFIRMATORY_INSTRUMENTS
from proprio.confirmatory_qualification import (
    CONFIRMATORY_FAMILIES,
    evaluate_confirmatory_skill,
    load_confirmatory_source,
)
from proprio.confirmatory_validation import (
    evaluate_confirmatory_validation,
    run_confirmatory_validation_once,
    seal_confirmatory_candidate,
)
from proprio.instrument_agent import (
    DISCLOSED_EXECUTOR_CONTRACT,
    HISTORY_REPLAY_CONTRACT,
    SKILL_ENGINEER_SYSTEM_PROMPT,
    InstrumentSkillAgent,
)
from proprio.instrument_study import (
    _paired_bootstrap_interval,
    _repair_protocol_evidence,
    _response_transport_evidence,
)
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    JudgeEpisode,
    LockedValidationReport,
    RepairEpisode,
    SimulationScenario,
    effective_judge_verdict,
)
from proprio.schema import canonical_json

PREREGISTRATION = Path(__file__).with_name("data") / "confirmatory-preregistration.yaml"
INSTRUMENT_IDS = tuple(sorted(CONFIRMATORY_INSTRUMENTS))
ARMS = (FeedbackArm.TRUTHFUL, FeedbackArm.NONE)


def _candidate_path(root: Path, instrument_id: str) -> Path:
    return root / instrument_id / "candidate.json"


def _repair_path(root: Path, instrument_id: str, arm: FeedbackArm) -> Path:
    return root / instrument_id / f"repair-{arm.value}.json"


def _validation_path(root: Path, instrument_id: str, arm: FeedbackArm) -> Path:
    return root / instrument_id / f"locked-validation-{arm.value}.json"


def _judge_path(root: Path, instrument_id: str, arm: FeedbackArm) -> Path:
    return root / instrument_id / f"judge-{arm.value}.json"


def _load_candidate(path: Path) -> CandidatePackage:
    return CandidatePackage.model_validate_json(path.read_text(encoding="utf-8"))


def _load_repair(path: Path) -> RepairEpisode:
    return RepairEpisode.model_validate_json(path.read_text(encoding="utf-8"))


def _load_or_run_validation(
    root: Path,
    episode: RepairEpisode,
) -> LockedValidationReport:
    path = _validation_path(root, episode.instrument_id, episode.feedback_arm)
    if path.is_file():
        report = LockedValidationReport.model_validate_json(path.read_text(encoding="utf-8"))
        expected = seal_confirmatory_candidate(episode.final_candidate)
        if report.candidate_sha256 != expected.candidate_sha256:
            raise ValueError("captured validation belongs to a different candidate")
        return report
    return run_confirmatory_validation_once(
        episode.final_candidate,
        path.with_name(f"selection-seal-{episode.feedback_arm.value}.json"),
        path,
    )


def run_live_confirmatory_study(output_dir: Path) -> dict[str, Any]:
    """Run the frozen DSV4 confirmatory protocol and capture deterministic evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    acquisition_prompt = SKILL_ENGINEER_SYSTEM_PROMPT + DISCLOSED_EXECUTOR_CONTRACT
    evolution_prompt = acquisition_prompt + HISTORY_REPLAY_CONTRACT
    draft_agent = InstrumentSkillAgent(
        skill_system_prompt=acquisition_prompt,
        source_loader=load_confirmatory_source,
        evaluator=evaluate_confirmatory_skill,
        families=CONFIRMATORY_FAMILIES,
    )
    repair_agent = InstrumentSkillAgent(
        client=draft_agent.client,
        skill_system_prompt=evolution_prompt,
        source_loader=load_confirmatory_source,
        evaluator=evaluate_confirmatory_skill,
        families=CONFIRMATORY_FAMILIES,
    )
    write_canonical_json(output_dir / "health.json", draft_agent.client.health())
    candidates: dict[str, CandidatePackage] = {}
    for instrument_id in INSTRUMENT_IDS:
        path = _candidate_path(output_dir, instrument_id)
        if path.is_file():
            candidate = _load_candidate(path)
        else:
            candidate = draft_agent.draft(instrument_id)
            write_canonical_json(path, candidate)
        candidates[instrument_id] = candidate

    for instrument_id in INSTRUMENT_IDS:
        for arm in ARMS:
            path = _repair_path(output_dir, instrument_id, arm)
            if path.is_file():
                episode = _load_repair(path)
            else:
                episode = repair_agent.repair(
                    candidates[instrument_id],
                    feedback_arm=arm,
                    scenario=SimulationScenario.REPAIR,
                    require_history=True,
                    history_scenarios=(SimulationScenario.NOMINAL,),
                    max_turns=12,
                )
                write_canonical_json(path, episode)
            _load_or_run_validation(output_dir, episode)

    summary = summarize_confirmatory_study(output_dir)
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def run_live_confirmatory_judges(
    root: Path,
    *,
    instrument_ids: tuple[str, ...] = INSTRUMENT_IDS,
) -> dict[str, Any]:
    """Capture stateful semantic reviews after deterministic evidence is complete."""

    agent = InstrumentSkillAgent(
        skill_system_prompt=SKILL_ENGINEER_SYSTEM_PROMPT + DISCLOSED_EXECUTOR_CONTRACT,
        source_loader=load_confirmatory_source,
        evaluator=evaluate_confirmatory_skill,
        families=CONFIRMATORY_FAMILIES,
    )
    for instrument_id in instrument_ids:
        for arm in ARMS:
            path = _judge_path(root, instrument_id, arm)
            if path.is_file():
                continue
            episode = _load_repair(_repair_path(root, instrument_id, arm))
            write_canonical_json(path, agent.judge(episode))
    summary = summarize_confirmatory_study(root)
    write_canonical_json(root / "summary.json", summary)
    return summary


def replay_confirmatory_study(cassette_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Re-execute captured candidates and locked conditions without a model call."""

    rows: list[dict[str, Any]] = []
    for instrument_id in INSTRUMENT_IDS:
        for arm in ARMS:
            episode = _load_repair(_repair_path(cassette_dir, instrument_id, arm))
            initial = evaluate_confirmatory_skill(
                instrument_id,
                episode.initial_candidate.skill_py,
                scenario=SimulationScenario.REPAIR,
            )
            target = evaluate_confirmatory_skill(
                instrument_id,
                episode.final_candidate.skill_py,
                scenario=SimulationScenario.REPAIR,
            )
            nominal_a = evaluate_confirmatory_skill(
                instrument_id,
                episode.final_candidate.skill_py,
                scenario=SimulationScenario.NOMINAL,
            )
            nominal_b = evaluate_confirmatory_skill(
                instrument_id,
                episode.final_candidate.skill_py,
                scenario=SimulationScenario.NOMINAL,
            )
            captured_validation = LockedValidationReport.model_validate_json(
                _validation_path(cassette_dir, instrument_id, arm).read_text(encoding="utf-8")
            )
            replayed_validation = evaluate_confirmatory_validation(
                episode.final_candidate,
                seal_confirmatory_candidate(episode.final_candidate),
            )
            initial_identical = canonical_json(initial.model_dump(mode="json")) == canonical_json(
                episode.initial_gate.model_dump(mode="json")
            )
            target_identical = canonical_json(target.model_dump(mode="json")) == canonical_json(
                episode.final_gate.model_dump(mode="json")
            )
            validation_identical = canonical_json(
                replayed_validation.model_dump(mode="json")
            ) == canonical_json(captured_validation.model_dump(mode="json"))
            idempotent = canonical_json(nominal_a.model_dump(mode="json")) == canonical_json(
                nominal_b.model_dump(mode="json")
            )
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "feedback_arm": arm.value,
                    "initial_gate_byte_identical": initial_identical,
                    "target_gate_byte_identical": target_identical,
                    "locked_validation_byte_identical": validation_identical,
                    "reset_idempotent": idempotent,
                }
            )
    result = {
        "schema_version": "proprio.confirmatory_replay.v0.1",
        "episodes": len(rows),
        "byte_identical": sum(
            row["initial_gate_byte_identical"]
            and row["target_gate_byte_identical"]
            and row["locked_validation_byte_identical"]
            for row in rows
        ),
        "reset_idempotent": sum(row["reset_idempotent"] for row in rows),
        "rows": rows,
    }
    result["verdict"] = (
        "PASS"
        if rows
        and all(
            row["initial_gate_byte_identical"]
            and row["target_gate_byte_identical"]
            and row["locked_validation_byte_identical"]
            and row["reset_idempotent"]
            for row in rows
        )
        else "FAIL"
    )
    write_canonical_json(output_dir / "summary.json", result)
    return result


def summarize_confirmatory_study(root: Path) -> dict[str, Any]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    initial_executable = 0
    paired: dict[str, list[int]] = {arm.value: [] for arm in ARMS}

    for instrument_id in INSTRUMENT_IDS:
        candidate_path = _candidate_path(root, instrument_id)
        if not candidate_path.is_file():
            continue
        candidate = _load_candidate(candidate_path)
        responses.extend(candidate.raw_response.get("responses", []))
        nominal = evaluate_confirmatory_skill(instrument_id, candidate.skill_py)
        initial_executable += nominal.verdict == "ADMIT"
        for arm in ARMS:
            path = _repair_path(root, instrument_id, arm)
            validation_path = _validation_path(root, instrument_id, arm)
            if not path.is_file() or not validation_path.is_file():
                continue
            episode = _load_repair(path)
            validation = LockedValidationReport.model_validate_json(
                validation_path.read_text(encoding="utf-8")
            )
            responses.extend(episode.raw_responses)
            judge_path = _judge_path(root, instrument_id, arm)
            judge = (
                JudgeEpisode.model_validate_json(judge_path.read_text(encoding="utf-8"))
                if judge_path.is_file()
                else None
            )
            if judge is not None:
                responses.extend(judge.raw_responses)
            history = evaluate_confirmatory_skill(
                instrument_id,
                episode.final_candidate.skill_py,
                scenario=SimulationScenario.NOMINAL,
            )
            target_passed = episode.final_gate.verdict == "ADMIT"
            history_passed = history.verdict == "ADMIT"
            locked_passed = validation.verdict == "PASS"
            hard_qualified = target_passed and history_passed and locked_passed
            semantic_verdict = effective_judge_verdict(judge.review) if judge is not None else None
            qualified = hard_qualified and (
                semantic_verdict == "ACCEPT" if judge is not None else True
            )
            protocol = _repair_protocol_evidence(episode)
            provenance_complete = (
                arm is FeedbackArm.TRUTHFUL
                and protocol["feedback_inspected_before_repair"]
                and protocol["repair_evidence_grounded"]
                and protocol["replayed_after_repair"]
            )
            admission_qualified = qualified and provenance_complete
            paired[arm.value].append(int(qualified))
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "family": CONFIRMATORY_FAMILIES[instrument_id],
                    "feedback_arm": arm.value,
                    "initial_nominal_verdict": nominal.verdict,
                    "final_target_verdict": episode.final_gate.verdict,
                    "history_verdict": history.verdict,
                    "locked_validation_verdict": validation.verdict,
                    "locked_validation_cases": len(validation.cases),
                    "hard_qualified": hard_qualified,
                    "semantic_review_status": judge.status if judge is not None else "not_run",
                    "semantic_verdict": semantic_verdict,
                    "qualified": qualified,
                    "provenance_complete": provenance_complete,
                    "admission_qualified": admission_qualified,
                    "promotion_eligible": admission_qualified,
                    "regression": target_passed and not history_passed,
                    "protocol_completed": episode.agent_status != "MAX_TURNS",
                    "cleanly_qualified": qualified and episode.agent_status == "CANDIDATE",
                    "agent_status": episode.agent_status,
                    "submissions": len(episode.submissions),
                    "model_turns": len(episode.raw_responses),
                    **protocol,
                }
            )

    arm_summary: dict[str, Any] = {}
    for arm in ARMS:
        arm_rows = [row for row in rows if row["feedback_arm"] == arm.value]
        count = len(arm_rows)
        arm_summary[arm.value] = {
            "episodes": count,
            "qualified": sum(row["qualified"] for row in arm_rows),
            "qualification_rate": sum(row["qualified"] for row in arm_rows) / count
            if count
            else 0.0,
            "admission_qualified": sum(row["admission_qualified"] for row in arm_rows),
            "admission_qualification_rate": (
                sum(row["admission_qualified"] for row in arm_rows) / count if count else 0.0
            ),
            "cleanly_qualified": sum(row["cleanly_qualified"] for row in arm_rows),
            "clean_qualification_rate": sum(row["cleanly_qualified"] for row in arm_rows) / count
            if count
            else 0.0,
            "regressions": sum(row["regression"] for row in arm_rows),
            "regression_rate": sum(row["regression"] for row in arm_rows) / count if count else 0.0,
            "protocol_completion_rate": sum(row["protocol_completed"] for row in arm_rows) / count
            if count
            else 0.0,
        }

    family_summary = {}
    for family in sorted(set(CONFIRMATORY_FAMILIES.values())):
        family_rows = [
            row
            for row in rows
            if row["family"] == family and row["feedback_arm"] == FeedbackArm.TRUTHFUL.value
        ]
        family_summary[family] = {
            "instruments": sorted(row["instrument_id"] for row in family_rows),
            "qualified": sum(row["admission_qualified"] for row in family_rows),
            "qualification_rate": (
                sum(row["admission_qualified"] for row in family_rows) / len(family_rows)
            )
            if family_rows
            else 0.0,
        }

    truthful = arm_summary.get(FeedbackArm.TRUTHFUL.value, {"qualification_rate": 0.0})
    none = arm_summary.get(FeedbackArm.NONE.value, {"qualification_rate": 0.0})
    uplift = truthful["qualification_rate"] - none["qualification_rate"]
    interval = _paired_bootstrap_interval(
        paired[FeedbackArm.TRUTHFUL.value],
        paired[FeedbackArm.NONE.value],
    )
    transport = _response_transport_evidence(responses)
    health_path = root / "health.json"
    health = json.loads(health_path.read_text(encoding="utf-8")) if health_path.is_file() else {}
    metrics = prereg["metrics"]
    initial_rate = initial_executable / len(INSTRUMENT_IDS)
    unsafe_promotions = sum(
        row["promotion_eligible"]
        and not (
            row["final_target_verdict"] == "ADMIT"
            and row["history_verdict"] == "ADMIT"
            and row["locked_validation_verdict"] == "PASS"
            and row["semantic_verdict"] in {None, "ACCEPT"}
            and row["provenance_complete"]
        )
        for row in rows
    )
    claim_gates = {
        "complete_capture": ("PASS" if len(rows) == len(INSTRUMENT_IDS) * len(ARMS) else "FAIL"),
        "initial_executable": (
            "PASS" if initial_rate >= metrics["initial_executable_rate_min"] else "FAIL"
        ),
        "truthful_qualification": (
            "PASS"
            if truthful["qualification_rate"] >= metrics["truthful_qualification_rate_min"]
            else "FAIL"
        ),
        "family_floor": (
            "PASS"
            if family_summary
            and all(
                item["qualification_rate"] >= metrics["truthful_family_rate_min"]
                for item in family_summary.values()
            )
            else "FAIL"
        ),
        "causal_uplift": ("PASS" if uplift >= metrics["causal_uplift_over_none_min"] else "FAIL"),
        "regression": (
            "PASS" if truthful["regression_rate"] <= metrics["regression_rate_max"] else "FAIL"
        ),
        "unsafe_promotion_prevention": (
            "PASS" if unsafe_promotions <= metrics["unsafe_promotions_max"] else "FAIL"
        ),
        "frozen_model_route": (
            "PASS"
            if health.get("requested_model") == prereg["model"]["id"]
            and transport["providers"] == [prereg["model"]["provider"]]
            and transport["resolved_models"] == [prereg["model"]["resolved_revision"]]
            and transport["reasoning_state_missing"] <= metrics["reasoning_state_missing_max"]
            else "FAIL"
        ),
    }
    reviewed = [row for row in rows if row["semantic_review_status"] != "not_run"]
    if reviewed:
        claim_gates["semantic_review_complete"] = (
            "PASS"
            if len(reviewed) == len(rows)
            and all(row["semantic_review_status"] == "completed" for row in reviewed)
            else "FAIL"
        )
    result = {
        "schema_version": "proprio.confirmatory_study.v0.2",
        "instrument_count": len(INSTRUMENT_IDS),
        "family_count": len(family_summary),
        "initial_executable": initial_executable,
        "initial_executable_rate": initial_rate,
        "arms": arm_summary,
        "causal_uplift_over_none": uplift,
        "causal_uplift_bootstrap_95": interval,
        "unsafe_promotions": unsafe_promotions,
        "families": family_summary,
        "transport_evidence": transport,
        "rows": rows,
        "claim_gates": claim_gates,
    }
    result["verdict"] = "PASS" if all(value == "PASS" for value in claim_gates.values()) else "FAIL"
    return result
