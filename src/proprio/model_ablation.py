"""Controlled model and executor-contract ablations for instrument skill repair."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml

from proprio.artifacts import write_canonical_json
from proprio.instrument_agent import (
    DISCLOSED_EXECUTOR_CONTRACT,
    SKILL_ENGINEER_SYSTEM_PROMPT,
    DSV4InstrumentAgent,
)
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_study import (
    INSTRUMENT_IDS,
    _repair_protocol_evidence,
    _response_transport_evidence,
    run_live_instrument_study,
)
from proprio.instrument_types import CandidatePackage, FeedbackArm, RepairEpisode
from proprio.reference_instruments import INSTRUMENTS

PREREGISTRATION = Path(__file__).with_name("data") / "model-ablation-preregistration.yaml"
StudyKind = Literal["native_draft", "shared_failure_repair"]
PromptCondition = Literal["original", "disclosed_executor_contract"]


def _candidate_path(root: Path, instrument_id: str) -> Path:
    return root / instrument_id / "candidate.json"


def _repair_path(root: Path, instrument_id: str, arm: FeedbackArm) -> Path:
    return root / instrument_id / f"repair-{arm.value}.json"


def _seed_shared_candidates(primary_dir: Path, output_dir: Path) -> None:
    for instrument_id in INSTRUMENT_IDS:
        source = _candidate_path(primary_dir, instrument_id)
        if not source.is_file():
            raise FileNotFoundError(f"missing primary candidate: {source}")
        candidate = CandidatePackage.model_validate_json(source.read_text(encoding="utf-8"))
        target = _candidate_path(output_dir, instrument_id)
        if not target.is_file():
            write_canonical_json(target, candidate)


def _safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def summarize_model_ablation(
    root: Path,
    *,
    target_model: str,
    target_provider: str,
    study: StudyKind,
    prompt_condition: PromptCondition,
) -> dict[str, Any]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    initial_executable = 0
    family_rows: dict[str, list[dict[str, Any]]] = {}

    for instrument_id in INSTRUMENT_IDS:
        candidate = CandidatePackage.model_validate_json(
            _candidate_path(root, instrument_id).read_text(encoding="utf-8")
        )
        nominal = evaluate_instrument_skill(instrument_id, candidate.skill_py)
        initial_executable += nominal.verdict == "ADMIT"
        if study == "native_draft":
            responses.extend(candidate.raw_response.get("responses", []))
        family = INSTRUMENTS[instrument_id].family
        for arm in (FeedbackArm.TRUTHFUL, FeedbackArm.NONE):
            path = _repair_path(root, instrument_id, arm)
            if not path.is_file():
                continue
            episode = RepairEpisode.model_validate_json(path.read_text(encoding="utf-8"))
            responses.extend(episode.raw_responses)
            protocol = _repair_protocol_evidence(episode)
            repaired = episode.final_gate.verdict == "ADMIT"
            regression = (
                evaluate_instrument_skill(instrument_id, episode.final_candidate.skill_py).verdict
                != "ADMIT"
            )
            qualified = repaired and not regression
            protocol_completed = episode.agent_status != "MAX_TURNS"
            cleanly_qualified = qualified and episode.agent_status == "CANDIDATE"
            row = {
                "instrument_id": instrument_id,
                "family": family,
                "feedback_arm": arm.value,
                "initial_nominal_verdict": nominal.verdict,
                "initial_target_verdict": episode.initial_gate.verdict,
                "final_target_verdict": episode.final_gate.verdict,
                "repaired": repaired,
                "regression": regression,
                "qualified": qualified,
                "protocol_completed": protocol_completed,
                "cleanly_qualified": cleanly_qualified,
                "submissions": len(episode.submissions),
                "model_turns": len(episode.raw_responses),
                "agent_status": episode.agent_status,
                "final_candidate_model": episode.final_candidate.model,
                **protocol,
            }
            rows.append(row)
            family_rows.setdefault(family, []).append(row)

    arm_summary: dict[str, Any] = {}
    for arm in (FeedbackArm.TRUTHFUL, FeedbackArm.NONE):
        items = [row for row in rows if row["feedback_arm"] == arm.value]
        arm_summary[arm.value] = {
            "episodes": len(items),
            "repaired": sum(row["repaired"] for row in items),
            "repair_rate": _safe_rate(sum(row["repaired"] for row in items), len(items)),
            "regressions": sum(row["regression"] for row in items),
            "regression_rate": _safe_rate(sum(row["regression"] for row in items), len(items)),
            "qualified": sum(row["qualified"] for row in items),
            "qualification_rate": _safe_rate(sum(row["qualified"] for row in items), len(items)),
            "protocol_completed": sum(row["protocol_completed"] for row in items),
            "protocol_completion_rate": _safe_rate(
                sum(row["protocol_completed"] for row in items), len(items)
            ),
            "cleanly_qualified": sum(row["cleanly_qualified"] for row in items),
            "clean_qualification_rate": _safe_rate(
                sum(row["cleanly_qualified"] for row in items), len(items)
            ),
            "mean_submissions": _safe_rate(sum(row["submissions"] for row in items), len(items)),
            "mean_model_turns": _safe_rate(sum(row["model_turns"] for row in items), len(items)),
        }

    family_summary: dict[str, Any] = {}
    for family, items in sorted(family_rows.items()):
        truthful = [row for row in items if row["feedback_arm"] == FeedbackArm.TRUTHFUL.value]
        family_summary[family] = {
            "instruments": sorted({row["instrument_id"] for row in truthful}),
            "truthful_repaired": sum(row["repaired"] for row in truthful),
            "truthful_repair_rate": _safe_rate(
                sum(row["repaired"] for row in truthful), len(truthful)
            ),
            "truthful_qualified": sum(row["qualified"] for row in truthful),
            "truthful_qualification_rate": _safe_rate(
                sum(row["qualified"] for row in truthful), len(truthful)
            ),
        }

    transport = _response_transport_evidence(responses)
    initial_rate = initial_executable / len(INSTRUMENT_IDS)
    truthful_rate = arm_summary[FeedbackArm.TRUTHFUL.value]["repair_rate"]
    none_rate = arm_summary[FeedbackArm.NONE.value]["repair_rate"]
    uplift = truthful_rate - none_rate
    metrics = prereg["metrics"]
    claim_gates = {
        "promotion_safe_qualification": "PASS"
        if arm_summary[FeedbackArm.TRUTHFUL.value]["qualification_rate"]
        >= metrics["truthful_repair_rate_min"]
        else "FAIL",
        "truthful_repair": "PASS"
        if truthful_rate >= metrics["truthful_repair_rate_min"]
        else "FAIL",
        "causal_uplift": "PASS" if uplift >= metrics["causal_uplift_over_none_min"] else "FAIL",
        "family_floor": (
            "PASS"
            if family_summary
            and all(
                value["truthful_repair_rate"] >= metrics["truthful_repair_family_min"]
                for value in family_summary.values()
            )
            else "FAIL"
        ),
        "regression": (
            "PASS"
            if arm_summary[FeedbackArm.TRUTHFUL.value]["regression_rate"]
            <= metrics["regression_rate_max"]
            else "FAIL"
        ),
        "frozen_model_route": (
            "PASS"
            if transport["providers"] == [target_provider]
            and transport["response_count"] > 0
            and transport["reasoning_state_missing"] == 0
            else "FAIL"
        ),
    }
    if study == "native_draft":
        claim_gates["initial_executable"] = (
            "PASS" if initial_rate >= metrics["initial_executable_rate_min"] else "FAIL"
        )
    result = {
        "schema_version": "proprio.model_ablation.v0.1",
        "study": study,
        "prompt_condition": prompt_condition,
        "target_model": target_model,
        "target_provider": target_provider,
        "instrument_count": len(INSTRUMENT_IDS),
        "family_count": len(family_summary),
        "initial_executable": initial_executable,
        "initial_executable_rate": initial_rate,
        "arms": arm_summary,
        "causal_uplift_over_none": uplift,
        "families": family_summary,
        "transport_evidence": transport,
        "rows": rows,
        "claim_gates": claim_gates,
    }
    result["verdict"] = "PASS" if all(value == "PASS" for value in claim_gates.values()) else "FAIL"
    return result


def run_live_model_ablation(
    primary_dir: Path,
    output_dir: Path,
    *,
    study: StudyKind,
    prompt_condition: PromptCondition,
) -> dict[str, Any]:
    if study == "shared_failure_repair":
        _seed_shared_candidates(primary_dir, output_dir)
    prompt = SKILL_ENGINEER_SYSTEM_PROMPT
    if prompt_condition == "disclosed_executor_contract":
        prompt += DISCLOSED_EXECUTOR_CONTRACT
    agent = DSV4InstrumentAgent(skill_system_prompt=prompt)
    run_live_instrument_study(
        output_dir,
        feedback_arms=(FeedbackArm.TRUTHFUL, FeedbackArm.NONE),
        run_judge=False,
        agent=agent,
    )
    summary = summarize_model_ablation(
        output_dir,
        target_model=agent.client.model,
        target_provider=agent.client.provider or "unfrozen",
        study=study,
        prompt_condition=prompt_condition,
    )
    write_canonical_json(output_dir / "ablation-summary.json", summary)
    return summary
