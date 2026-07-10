"""Live capture, deterministic replay, and reporting for diagnostic skill episodes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from proprio.artifacts import write_bytes, write_canonical_json
from proprio.instrument_agent import DSV4InstrumentAgent
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    JudgeEpisode,
    RepairEpisode,
    SimulationScenario,
    combine_hybrid_verdict,
    effective_judge_verdict,
)
from proprio.reference_instruments import INSTRUMENTS

PREREGISTRATION = Path(__file__).with_name("data") / "skill-evolution-preregistration.yaml"
INSTRUMENT_IDS = tuple(sorted(INSTRUMENTS))


def _candidate_path(root: Path, instrument_id: str) -> Path:
    return root / instrument_id / "candidate.json"


def _repair_path(root: Path, instrument_id: str, arm: FeedbackArm) -> Path:
    return root / instrument_id / f"repair-{arm.value}.json"


def _judge_path(root: Path, instrument_id: str, arm: FeedbackArm) -> Path:
    return root / instrument_id / f"judge-{arm.value}.json"


def _load_candidate(path: Path) -> CandidatePackage:
    return CandidatePackage.model_validate_json(path.read_text(encoding="utf-8"))


def _load_repair(path: Path) -> RepairEpisode:
    return RepairEpisode.model_validate_json(path.read_text(encoding="utf-8"))


def _load_judge(path: Path) -> JudgeEpisode:
    return JudgeEpisode.model_validate_json(path.read_text(encoding="utf-8"))


def run_live_instrument_study(
    cassette_dir: Path,
    *,
    instrument_ids: tuple[str, ...] = INSTRUMENT_IDS,
    feedback_arms: tuple[FeedbackArm, ...] = tuple(FeedbackArm),
    run_judge: bool = True,
    agent: DSV4InstrumentAgent | None = None,
) -> dict[str, Any]:
    """Capture live DSV4 episodes incrementally so interrupted studies can resume."""

    cassette_dir.mkdir(parents=True, exist_ok=True)
    agent = agent or DSV4InstrumentAgent()
    health = agent.client.health()
    write_canonical_json(cassette_dir / "health.json", health)

    candidates: dict[str, CandidatePackage] = {}
    for instrument_id in instrument_ids:
        path = _candidate_path(cassette_dir, instrument_id)
        if path.is_file():
            candidate = _load_candidate(path)
        else:
            candidate = agent.draft(instrument_id)
            write_canonical_json(path, candidate)
        candidates[instrument_id] = candidate

    changed_gates = {
        instrument_id: evaluate_instrument_skill(
            instrument_id,
            candidate.skill_py,
            scenario=SimulationScenario.REPAIR,
        )
        for instrument_id, candidate in candidates.items()
    }

    for index, instrument_id in enumerate(instrument_ids):
        mismatch_id = instrument_ids[(index + 1) % len(instrument_ids)]
        for arm in feedback_arms:
            repair_path = _repair_path(cassette_dir, instrument_id, arm)
            if repair_path.is_file():
                episode = _load_repair(repair_path)
            else:
                episode = agent.repair(
                    candidates[instrument_id],
                    feedback_arm=arm,
                    mismatched_gate=changed_gates[mismatch_id]
                    if arm is FeedbackArm.MISMATCHED
                    else None,
                )
                write_canonical_json(repair_path, episode)
            if run_judge:
                judge_path = _judge_path(cassette_dir, instrument_id, arm)
                if not judge_path.is_file():
                    write_canonical_json(judge_path, agent.judge(episode))

    summary = summarize_instrument_study(cassette_dir, instrument_ids=instrument_ids)
    write_canonical_json(cassette_dir / "summary.json", summary)
    _write_study_report(cassette_dir / "report.md", summary)
    return summary


def _paired_bootstrap_interval(
    truthful: list[int],
    comparison: list[int],
    *,
    seed: int = 20260709,
    samples: int = 10000,
) -> list[float]:
    if len(truthful) != len(comparison) or not truthful:
        return [0.0, 0.0]
    differences = np.asarray(truthful, dtype=float) - np.asarray(comparison, dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(differences), size=(samples, len(differences)))
    estimates = differences[indices].mean(axis=1)
    return [float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))]


def _repair_protocol_evidence(episode: RepairEpisode) -> dict[str, bool]:
    successful_runs: list[tuple[int, dict[str, Any]]] = []
    successful_submissions: list[tuple[int, dict[str, Any]]] = []
    for index, event in enumerate(episode.tool_events):
        result = event.get("result", {})
        if result.get("status") == "error":
            continue
        if event.get("name") == "run_simulator":
            successful_runs.append((index, result))
        elif event.get("name") == "submit_repair" and result.get("status") == "captured":
            successful_submissions.append((index, event.get("arguments", {})))

    inspected = bool(
        successful_runs
        and successful_submissions
        and successful_runs[0][0] < successful_submissions[0][0]
    )
    replayed = bool(
        successful_runs
        and successful_submissions
        and successful_runs[-1][0] > successful_submissions[-1][0]
    )
    grounded = bool(successful_submissions)
    if episode.feedback_arm is FeedbackArm.TRUTHFUL:
        for submission_index, arguments in successful_submissions:
            observed: set[str] = set()
            for run_index, result in successful_runs:
                if run_index >= submission_index:
                    continue
                if result.get("evidence_ref"):
                    observed.add(str(result["evidence_ref"]))
                observed.update(
                    str(check["check_id"])
                    for check in result.get("checks", [])
                    if check.get("check_id")
                )
            cited = {str(value) for value in arguments.get("evidence_refs", [])}
            grounded = grounded and bool(cited) and cited.issubset(observed)
    return {
        "feedback_inspected_before_repair": inspected,
        "repair_evidence_grounded": grounded,
        "replayed_after_repair": replayed,
        "multi_turn": len(episode.raw_responses) >= 2,
    }


def _response_transport_evidence(responses: list[dict[str, Any]]) -> dict[str, Any]:
    providers = sorted({str(item["provider"]) for item in responses if item.get("provider")})
    models = sorted({str(item["model"]) for item in responses if item.get("model")})
    reasoning_present = sum(
        bool(
            item.get("preserved_assistant_message", {}).get("reasoning")
            or item.get("preserved_assistant_message", {}).get("reasoning_details")
            or item.get("preserved_assistant_message", {}).get("reasoning_content")
        )
        for item in responses
    )
    usage_rows = [item.get("usage") or {} for item in responses]
    prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in usage_rows)
    completion_tokens = sum(int(item.get("completion_tokens") or 0) for item in usage_rows)
    reasoning_tokens = sum(
        int((item.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        for item in usage_rows
    )
    cost_usd = sum(float(item.get("cost") or 0.0) for item in usage_rows)
    return {
        "response_count": len(responses),
        "providers": providers,
        "resolved_models": models,
        "reasoning_state_present": reasoning_present,
        "reasoning_state_missing": len(responses) - reasoning_present,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": cost_usd,
        },
    }


def summarize_instrument_study(
    cassette_dir: Path,
    *,
    instrument_ids: tuple[str, ...] = INSTRUMENT_IDS,
) -> dict[str, Any]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    rows = []
    initial_executable = 0
    family_rows: dict[str, list[dict[str, Any]]] = {}
    paired: dict[str, list[int]] = {arm.value: [] for arm in FeedbackArm}
    captured_responses: list[dict[str, Any]] = []
    requested_models: set[str] = set()

    for instrument_id in instrument_ids:
        candidate = _load_candidate(_candidate_path(cassette_dir, instrument_id))
        requested_models.add(candidate.model)
        captured_responses.extend(candidate.raw_response.get("responses", []))
        nominal = evaluate_instrument_skill(instrument_id, candidate.skill_py)
        initial_executable += nominal.verdict == "ADMIT"
        family = INSTRUMENTS[instrument_id].family
        for arm in FeedbackArm:
            repair_path = _repair_path(cassette_dir, instrument_id, arm)
            if not repair_path.is_file():
                continue
            episode = _load_repair(repair_path)
            captured_responses.extend(episode.raw_responses)
            judge_path = _judge_path(cassette_dir, instrument_id, arm)
            judge = _load_judge(judge_path) if judge_path.is_file() else None
            if judge is not None:
                captured_responses.extend(judge.raw_responses)
            review = judge.review if judge else None
            hybrid = combine_hybrid_verdict(episode.final_gate, review)
            regression = (
                evaluate_instrument_skill(instrument_id, episode.final_candidate.skill_py).verdict
                != "ADMIT"
            )
            repairable = episode.initial_gate.verdict == "REJECT"
            repaired = episode.final_gate.verdict == "ADMIT" if repairable else True
            protocol = _repair_protocol_evidence(episode)
            paired[arm.value].append(int(repaired and repairable))
            row = {
                "instrument_id": instrument_id,
                "family": family,
                "feedback_arm": arm.value,
                "initial_nominal_verdict": nominal.verdict,
                "initial_target_verdict": episode.initial_gate.verdict,
                "repairable": repairable,
                "final_target_verdict": episode.final_gate.verdict,
                "repaired": repaired,
                "regression": regression,
                "agent_status": episode.agent_status,
                "submission_count": len(episode.submissions),
                "judge_status": judge.status if judge else "missing",
                "judge_verdict": review.verdict if review else None,
                "effective_judge_verdict": effective_judge_verdict(review),
                "hybrid_verdict": hybrid.verdict,
                **protocol,
            }
            rows.append(row)
            family_rows.setdefault(family, []).append(row)

    arm_summary = {}
    for arm in FeedbackArm:
        arm_rows = [row for row in rows if row["feedback_arm"] == arm.value]
        eligible = [row for row in arm_rows if row["repairable"]]
        arm_summary[arm.value] = {
            "episodes": len(arm_rows),
            "repairable": len(eligible),
            "repaired": sum(row["repaired"] for row in eligible),
            "repair_rate": (
                sum(row["repaired"] for row in eligible) / len(eligible) if eligible else 0.0
            ),
            "regressions": sum(row["regression"] for row in arm_rows),
            "regression_rate": (
                sum(row["regression"] for row in arm_rows) / len(arm_rows) if arm_rows else 0.0
            ),
        }

    family_summary = {}
    for family, items in sorted(family_rows.items()):
        truthful = [
            row
            for row in items
            if row["feedback_arm"] == FeedbackArm.TRUTHFUL.value and row["repairable"]
        ]
        family_summary[family] = {
            "variants": sorted({row["instrument_id"] for row in items}),
            "truthful_repairable": len(truthful),
            "truthful_repaired": sum(row["repaired"] for row in truthful),
            "truthful_repair_rate": (
                sum(row["repaired"] for row in truthful) / len(truthful) if truthful else 0.0
            ),
        }

    initial_rate = initial_executable / len(instrument_ids)
    truthful_rate = arm_summary[FeedbackArm.TRUTHFUL.value]["repair_rate"]
    none_rate = arm_summary[FeedbackArm.NONE.value]["repair_rate"]
    causal_uplift = truthful_rate - none_rate
    interval = _paired_bootstrap_interval(
        paired[FeedbackArm.TRUTHFUL.value], paired[FeedbackArm.NONE.value]
    )
    metrics = prereg["metrics"]
    draft_gate = initial_rate >= metrics["initial_executable_rate_min"]
    repair_gate = (
        truthful_rate >= metrics["truthful_repair_macro_min"]
        and causal_uplift >= metrics["causal_uplift_over_none_min"]
        and interval[0] > 0.0
        and arm_summary[FeedbackArm.TRUTHFUL.value]["regression_rate"]
        <= metrics["regression_rate_max"]
        and all(
            row["feedback_inspected_before_repair"]
            and row["repair_evidence_grounded"]
            and row["replayed_after_repair"]
            and row["multi_turn"]
            for row in rows
            if row["feedback_arm"] == FeedbackArm.TRUTHFUL.value and row["repairable"]
        )
    )
    family_gate = bool(family_summary) and all(
        item["truthful_repair_rate"] >= metrics["truthful_repair_family_min"]
        for item in family_summary.values()
    )
    hard_override_count = sum(
        row["final_target_verdict"] == "REJECT" and row["hybrid_verdict"] == "ADMIT" for row in rows
    )
    transport = _response_transport_evidence(captured_responses)
    expected = prereg["reproducibility"]
    live_capture = expected["live_model"] in requested_models
    route_gate = (
        requested_models == {expected["live_model"]}
        and transport["providers"] == [expected["provider"]]
        and transport["resolved_models"] == [expected["resolved_model_revision"]]
        and transport["response_count"] > 0
        and transport["reasoning_state_missing"] == 0
    )
    summary = {
        "schema_version": "proprio.instrument_study.v0.2",
        "instrument_count": len(instrument_ids),
        "family_count": len({INSTRUMENTS[item].family for item in instrument_ids}),
        "initial_executable": initial_executable,
        "initial_executable_rate": initial_rate,
        "arms": arm_summary,
        "families": family_summary,
        "causal_uplift_over_none": causal_uplift,
        "causal_uplift_bootstrap_95": interval,
        "hard_failure_overrides": hard_override_count,
        "capture_mode": "live" if live_capture else "fixture",
        "requested_models": sorted(requested_models),
        "transport_evidence": transport,
        "rows": rows,
        "claim_gates": {
            "executable_drafting": "PASS" if draft_gate else "FAIL",
            "causal_repair": "PASS" if repair_gate else "FAIL",
            "diagnostic_family_coverage": "PASS" if family_gate else "FAIL",
            "hard_gate_dominance": "PASS" if hard_override_count == 0 else "FAIL",
        },
    }
    if live_capture:
        summary["claim_gates"]["frozen_model_route"] = "PASS" if route_gate else "FAIL"
    summary["verdict"] = (
        "PASS" if all(value == "PASS" for value in summary["claim_gates"].values()) else "FAIL"
    )
    return summary


def replay_instrument_study(cassette_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    replay_rows = []
    for instrument_id in INSTRUMENT_IDS:
        for arm in FeedbackArm:
            path = _repair_path(cassette_dir, instrument_id, arm)
            if not path.is_file():
                continue
            episode = _load_repair(path)
            replayed = evaluate_instrument_skill(
                instrument_id,
                episode.final_candidate.skill_py,
                scenario=episode.scenario,
            )
            replay_rows.append(
                {
                    "instrument_id": instrument_id,
                    "feedback_arm": arm.value,
                    "captured_verdict": episode.final_gate.verdict,
                    "replayed_verdict": replayed.verdict,
                    "captured_skill_sha256": episode.final_gate.skill_sha256,
                    "replayed_skill_sha256": replayed.skill_sha256,
                    "identical": replayed.model_dump(mode="json")
                    == episode.final_gate.model_dump(mode="json"),
                }
            )
    summary = {
        "schema_version": "proprio.instrument_study_replay.v0.2",
        "episodes": len(replay_rows),
        "identical": sum(row["identical"] for row in replay_rows),
        "rows": replay_rows,
    }
    summary["verdict"] = (
        "PASS" if replay_rows and all(row["identical"] for row in replay_rows) else "FAIL"
    )
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def _write_study_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Diagnostic instrument skill study",
        "",
        f"Overall verdict: **{summary['verdict']}**",
        "",
        f"Initial executable drafts: {summary['initial_executable']}/{summary['instrument_count']}",
        f"Truthful repair rate: {summary['arms']['truthful']['repair_rate']:.3f}",
        f"No-feedback repair rate: {summary['arms']['none']['repair_rate']:.3f}",
        f"Causal uplift: {summary['causal_uplift_over_none']:.3f}",
        f"Paired bootstrap 95% interval: {summary['causal_uplift_bootstrap_95']}",
        f"Hard-failure overrides: {summary['hard_failure_overrides']}",
        "",
        "## Claim gates",
        "",
    ]
    lines.extend(
        f"- {name.replace('_', ' ')}: **{verdict}**"
        for name, verdict in summary["claim_gates"].items()
    )
    lines.extend(["", "## Family results", ""])
    lines.extend(
        f"- {family}: {item['truthful_repaired']}/{item['truthful_repairable']} "
        f"({item['truthful_repair_rate']:.3f})"
        for family, item in summary["families"].items()
    )
    write_bytes(path, ("\n".join(lines) + "\n").encode(), "text/markdown")


def load_study_summary(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("study summary must be an object")
    return value
