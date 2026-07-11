"""Manifest-bound live acquisition study across external simulator families."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

from proprio.adaptive_agent import AdaptiveInstrumentAgent, AdaptiveRepairEpisode
from proprio.adaptive_search import (
    DebugSuiteResult,
    RepairOutcome,
    SearchReport,
    evaluate_debug_suite,
    run_archive_search,
)
from proprio.artifacts import write_canonical_json
from proprio.generalization_instruments import (
    GENERALIZATION_INSTRUMENTS,
    evaluate_generalization_skill,
    load_generalization_source,
    run_generalization_preflight,
)
from proprio.generalization_method import verify_generalization_method
from proprio.instrument_types import CandidatePackage, FeedbackArm
from proprio.policy import DSV4Client
from proprio.schema import canonical_json

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FREEZE = ROOT / "artifacts/evidence/generalization-v0.3/method-freeze/manifest.json"
EXPECTED_PROVIDER_ROUTE = "DeepInfra,GMICloud"
EXPECTED_PROVIDERS = frozenset({"DeepInfra", "GMICloud"})
EXPECTED_RESOLVED_MODEL = "deepseek/deepseek-v4-flash-20260423"
BINDING_SESSIONS_PER_FAMILY = 30
BINDING_SEED_BASE = 2_000_000


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected an object: {path}")
    return payload


def _candidate_hash(skill_py: str) -> str:
    return hashlib.sha256(skill_py.encode()).hexdigest()


def _payload_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _conditions_hash(conditions: tuple[Any, ...]) -> str:
    return _payload_hash(
        [condition.model_dump(mode="json") for condition in conditions]
    )


def _write_or_verify(path: Path, payload: dict[str, Any], *, label: str) -> None:
    if path.is_file() and _read_json(path) != payload:
        raise RuntimeError(f"{label} does not match the frozen session: {path}")
    write_canonical_json(path, payload)


def _checkpoint_binding_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.binding.json")


def _bind_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    _write_or_verify(_checkpoint_binding_path(path), payload, label="checkpoint binding")


def _verify_checkpoint_binding(path: Path, payload: dict[str, Any]) -> None:
    binding_path = _checkpoint_binding_path(path)
    if not binding_path.is_file():
        raise RuntimeError(f"cached checkpoint is missing its frozen binding: {path}")
    if _read_json(binding_path) != payload:
        raise RuntimeError(f"cached checkpoint has the wrong frozen binding: {path}")


def _session_manifest_payload(
    *,
    instrument_id: str,
    session_index: int,
    session_seed: int,
    method_sha256: str,
    source_sha256: str,
    definition: Any,
    panel_manifest_sha256: str | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "proprio.generalization_session_manifest.v0.3",
        "study_mode": "binding" if panel_manifest_sha256 else "engineering",
        "panel_manifest_sha256": panel_manifest_sha256,
        "method_sha256": method_sha256,
        "instrument_id": instrument_id,
        "session_index": session_index,
        "session_seed": session_seed,
        "source_sha256": source_sha256,
        "model": "deepseek/deepseek-v4-flash",
        "resolved_model": EXPECTED_RESOLVED_MODEL,
        "provider_order": list(EXPECTED_PROVIDER_ROUTE.split(",")),
        "provider_allowlist": list(EXPECTED_PROVIDER_ROUTE.split(",")),
        "search_budget": {
            "initial_drafts": 6,
            "archive_survivors": 3,
            "repair_rounds": 6,
            "maximum_candidate_variants": 24,
            "maximum_model_turns_per_draft": 8,
            "maximum_model_turns_per_repair": 16,
            "maximum_causal_repair_episodes": 4,
            "maximum_evolution_repair_episodes": 6,
        },
        "condition_hashes": {
            "acquisition": _conditions_hash(definition.acquisition_conditions),
            "visible": _conditions_hash(definition.visible_conditions),
            "locked": _conditions_hash(definition.locked_conditions),
            "evolution": _conditions_hash(definition.evolution_conditions),
        },
    }
    payload["session_manifest_sha256"] = _payload_hash(payload)
    return payload


def _agent(
    *,
    seed: int,
    temperature: float,
    top_p: float,
) -> AdaptiveInstrumentAgent:
    client = DSV4Client()
    if "openrouter.ai" in client.base_url and client.provider != EXPECTED_PROVIDER_ROUTE:
        client.close()
        raise RuntimeError(
            "binding route must use "
            f"{EXPECTED_PROVIDER_ROUTE}, observed {client.provider or 'unset'}"
        )
    return AdaptiveInstrumentAgent(
        client=client,
        source_loader=load_generalization_source,
        evaluator=evaluate_generalization_skill,
        families={
            instrument_id: definition.family
            for instrument_id, definition in GENERALIZATION_INSTRUMENTS.items()
        },
        sampling_temperature=temperature,
        sampling_top_p=top_p,
        sampling_seed=seed,
    )


def _select_causal_parent(search: Any, instrument_id: str) -> CandidatePackage | None:
    """Choose a model-authored nominal success that fails the registered change."""

    definition = GENERALIZATION_INSTRUMENTS[instrument_id]
    eligible: list[CandidatePackage] = []
    for entry in search.entries:
        if entry.generation != 0:
            continue
        candidate = entry.candidate
        if candidate.self_judgment.get("verdict") != "ACCEPT":
            continue
        acquisition = evaluate_debug_suite(
            candidate,
            definition.acquisition_conditions,
            evaluator=evaluate_generalization_skill,
        )
        changed = evaluate_debug_suite(
            candidate,
            definition.visible_conditions,
            evaluator=evaluate_generalization_skill,
        )
        if acquisition.verdict == "ADMIT" and changed.verdict == "REJECT":
            eligible.append(candidate)
    return min(eligible, key=lambda item: _candidate_hash(item.skill_py)) if eligible else None


def _run_repair_trajectory(
    parent: CandidatePackage,
    *,
    conditions: tuple[Any, ...],
    locked_conditions: tuple[Any, ...],
    feedback_arm: FeedbackArm,
    seed: int,
    output_dir: Path,
    maximum_episodes: int = 6,
) -> dict[str, Any]:
    """Run a bounded repair trajectory and qualify it without model promotion authority."""

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    if summary_path.is_file():
        return _read_json(summary_path)
    current = parent
    initial_path = output_dir / "initial-suite.json"
    if initial_path.is_file():
        suite = DebugSuiteResult.model_validate_json(initial_path.read_text(encoding="utf-8"))
        if suite.candidate_sha256 != _candidate_hash(parent.skill_py):
            raise RuntimeError("partial repair trajectory belongs to a different parent")
    else:
        suite = evaluate_debug_suite(current, conditions, evaluator=evaluate_generalization_skill)
        write_canonical_json(initial_path, suite)
    episodes: list[AdaptiveRepairEpisode] = []
    for path in sorted(output_dir.glob("episode-*.json")):
        episode = AdaptiveRepairEpisode.model_validate_json(path.read_text(encoding="utf-8"))
        if episode.feedback_arm is not feedback_arm:
            raise RuntimeError("partial repair trajectory uses a different feedback arm")
        if _candidate_hash(episode.initial_candidate.skill_py) != _candidate_hash(current.skill_py):
            raise RuntimeError("partial repair trajectory has a broken candidate chain")
        episodes.append(episode)
        current = episode.final_candidate
        replay_path = output_dir / path.name.replace("episode-", "replay-")
        if replay_path.is_file():
            suite = DebugSuiteResult.model_validate_json(replay_path.read_text(encoding="utf-8"))
        else:
            suite = evaluate_debug_suite(
                current,
                conditions,
                evaluator=evaluate_generalization_skill,
            )
            write_canonical_json(replay_path, suite)
    for index in range(len(episodes), maximum_episodes):
        if episodes and episodes[-1].agent_status == "CANDIDATE" and suite.verdict == "ADMIT":
            break
        agent = _agent(seed=seed + index * 1_000_000, temperature=0.0, top_p=1.0)
        try:
            episode = agent.repair_candidate(
                current,
                conditions,
                feedback_arm=feedback_arm,
                initial_suite=suite,
                max_turns=16,
            )
        finally:
            agent.client.close()
        episodes.append(episode)
        write_canonical_json(output_dir / f"episode-{index + 1:02d}.json", episode)
        current = episode.final_candidate
        suite = evaluate_debug_suite(current, conditions, evaluator=evaluate_generalization_skill)
        write_canonical_json(output_dir / f"replay-{index + 1:02d}.json", suite)
        if episode.agent_status == "CANDIDATE" and suite.verdict == "ADMIT":
            break

    locked = evaluate_debug_suite(
        current,
        locked_conditions,
        evaluator=evaluate_generalization_skill,
    )
    write_canonical_json(output_dir / "locked-qualification.json", locked)
    changed = current.skill_py != parent.skill_py
    submitted = any(episode.submission is not None for episode in episodes)
    qualified = bool(
        episodes
        and changed
        and submitted
        and suite.verdict == "ADMIT"
        and locked.verdict == "ADMIT"
        and episodes[-1].agent_status == "CANDIDATE"
    )
    result = {
        "schema_version": "proprio.generalization_repair_trajectory.v0.3",
        "instrument_id": parent.instrument_id,
        "feedback_arm": feedback_arm.value,
        "parent_sha256": _candidate_hash(parent.skill_py),
        "final_sha256": _candidate_hash(current.skill_py),
        "changed": changed,
        "submitted": submitted,
        "episodes_used": len(episodes),
        "visible_verdict": suite.verdict,
        "locked_verdict": locked.verdict,
        "agent_status": episodes[-1].agent_status if episodes else "NOT_RUN",
        "qualified": qualified,
        "final_candidate": current.model_dump(mode="json"),
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result


def _run_causal_pair(
    parent: CandidatePackage,
    *,
    definition: Any,
    seed: int,
    output_dir: Path,
) -> dict[str, Any]:
    summary_path = output_dir / "summary.json"
    if summary_path.is_file():
        return _read_json(summary_path)
    outcomes = {}
    for arm in (FeedbackArm.TRUTHFUL, FeedbackArm.NONE):
        outcomes[arm.value] = _run_repair_trajectory(
            parent,
            conditions=definition.visible_conditions,
            locked_conditions=definition.locked_conditions,
            feedback_arm=arm,
            seed=seed,
            output_dir=output_dir / arm.value,
            maximum_episodes=4,
        )
    result = {
        "schema_version": "proprio.generalization_causal_pair.v0.3",
        "instrument_id": parent.instrument_id,
        "paired_seed": seed,
        "same_parent": len({row["parent_sha256"] for row in outcomes.values()}) == 1,
        "promotion_authority": "deterministic-visible-and-locked-gates",
        "outcomes": outcomes,
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result


def _run_evolution_proposal(
    parent: CandidatePackage,
    *,
    definition: Any,
    seed: int,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    if summary_path.is_file():
        return _read_json(summary_path)
    drift = evaluate_debug_suite(
        parent,
        definition.evolution_conditions,
        evaluator=evaluate_generalization_skill,
    )
    write_canonical_json(output_dir / "drift-detection.json", drift)
    if drift.verdict != "REJECT":
        result = {
            "schema_version": "proprio.generalization_evolution_proposal.v0.3",
            "instrument_id": parent.instrument_id,
            "status": "HOLD",
            "reason": "registered deployment drift did not invalidate the admitted parent",
            "parent_sha256": _candidate_hash(parent.skill_py),
            "hardware_qualification_required": True,
        }
        write_canonical_json(output_dir / "summary.json", result)
        return result

    trajectory = _run_repair_trajectory(
        parent,
        conditions=definition.visible_conditions + definition.evolution_conditions,
        locked_conditions=definition.locked_conditions,
        feedback_arm=FeedbackArm.TRUTHFUL,
        seed=seed,
        output_dir=output_dir / "repair",
    )
    proposal = CandidatePackage.model_validate(trajectory["final_candidate"])
    acquisition = evaluate_debug_suite(
        proposal,
        definition.acquisition_conditions,
        evaluator=evaluate_generalization_skill,
    )
    evolution = evaluate_debug_suite(
        proposal,
        definition.evolution_conditions,
        evaluator=evaluate_generalization_skill,
    )
    qualified = bool(
        trajectory["qualified"]
        and acquisition.verdict == "ADMIT"
        and evolution.verdict == "ADMIT"
    )
    result = {
        "schema_version": "proprio.generalization_evolution_proposal.v0.3",
        "instrument_id": parent.instrument_id,
        "status": "STAGED" if qualified else "REJECTED",
        "reason": (
            "drift detected; proposal passed visible, historical, and locked simulation checks"
            if qualified
            else "proposal did not pass every frozen qualification check"
        ),
        "parent_sha256": _candidate_hash(parent.skill_py),
        "proposal_sha256": _candidate_hash(proposal.skill_py),
        "drift_detected": True,
        "acquisition_verdict": acquisition.verdict,
        "evolution_verdict": evolution.verdict,
        "locked_verdict": trajectory["locked_verdict"],
        "hardware_qualification_required": True,
        "trajectory": trajectory,
    }
    write_canonical_json(summary_path, result)
    return result


def run_live_generalization_session(
    instrument_id: str,
    *,
    session_index: int,
    output_dir: Path,
    freeze_path: Path = DEFAULT_FREEZE,
    seed_base: int = 2_000_000,
    panel_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Run one independent source-to-skill acquisition and locked qualification."""

    if instrument_id not in GENERALIZATION_INSTRUMENTS:
        raise KeyError(instrument_id)
    freeze_verification = verify_generalization_method(freeze_path)
    if freeze_verification["verdict"] != "PASS":
        raise RuntimeError("v0.3 method freeze did not verify before model generation")
    freeze = _read_json(freeze_path)
    preflight = run_generalization_preflight(instrument_id)
    if preflight.verdict != "PASS":
        raise RuntimeError("external simulator preflight failed before model generation")

    definition = GENERALIZATION_INSTRUMENTS[instrument_id]
    session_seed = seed_base + session_index * 10_000
    source, source_hash = load_generalization_source(instrument_id)
    del source
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "work"
    session_manifest = _session_manifest_payload(
        instrument_id=instrument_id,
        session_index=session_index,
        session_seed=session_seed,
        method_sha256=freeze["method_sha256"],
        source_sha256=source_hash,
        definition=definition,
        panel_manifest_sha256=panel_manifest_sha256,
    )
    _write_or_verify(
        output_dir / "session-manifest.json",
        session_manifest,
        label="session manifest",
    )
    session_manifest_sha256 = session_manifest["session_manifest_sha256"]

    def draft(seed: int):
        path = work_dir / "drafts" / f"seed-{seed}.json"
        if path.is_file():
            candidate = CandidatePackage.model_validate_json(path.read_text(encoding="utf-8"))
            if (
                candidate.instrument_id != instrument_id
                or candidate.source_sha256 != source_hash
                or candidate.model != "deepseek/deepseek-v4-flash"
            ):
                raise RuntimeError(f"cached draft does not match the frozen session: {path}")
            _verify_checkpoint_binding(
                path,
                {
                    "session_manifest_sha256": session_manifest_sha256,
                    "seed": seed,
                    "candidate_sha256": _payload_hash(candidate),
                    "prompt_sha256": candidate.prompt_sha256,
                },
            )
            return candidate
        agent = _agent(seed=seed, temperature=0.7, top_p=0.95)
        try:
            candidate = agent.draft(instrument_id, max_turns=8)
        finally:
            agent.client.close()
        write_canonical_json(path, candidate)
        _bind_checkpoint(
            path,
            {
                "session_manifest_sha256": session_manifest_sha256,
                "seed": seed,
                "candidate_sha256": _payload_hash(candidate),
                "prompt_sha256": candidate.prompt_sha256,
            },
        )
        return candidate

    def repair(candidate, suite, seed: int):
        parent_sha = _candidate_hash(candidate.skill_py)
        path = work_dir / "repairs" / f"seed-{seed}-{parent_sha}.json"
        if path.is_file():
            outcome = RepairOutcome.model_validate_json(path.read_text(encoding="utf-8"))
            initial = outcome.record.get("initial_candidate", {})
            if _candidate_hash(str(initial.get("skill_py", ""))) != parent_sha:
                raise RuntimeError(f"cached repair does not match its frozen parent: {path}")
            _verify_checkpoint_binding(
                path,
                {
                    "session_manifest_sha256": session_manifest_sha256,
                    "seed": seed,
                    "parent_sha256": parent_sha,
                    "outcome_sha256": _payload_hash(outcome),
                },
            )
            return outcome
        agent = _agent(seed=seed, temperature=0.0, top_p=1.0)
        try:
            outcome = agent.repair_for_search(
                candidate,
                suite,
                seed,
                conditions=definition.visible_conditions,
                max_turns=16,
            )
        finally:
            agent.client.close()
        write_canonical_json(path, outcome)
        _bind_checkpoint(
            path,
            {
                "session_manifest_sha256": session_manifest_sha256,
                "seed": seed,
                "parent_sha256": parent_sha,
                "outcome_sha256": _payload_hash(outcome),
            },
        )
        return outcome

    search_path = output_dir / "search.json"
    if search_path.is_file():
        search = SearchReport.model_validate_json(search_path.read_text(encoding="utf-8"))
        _verify_checkpoint_binding(
            search_path,
            {
                "session_manifest_sha256": session_manifest_sha256,
                "search_sha256": _payload_hash(search),
            },
        )
    else:
        search = run_archive_search(
            instrument_id,
            conditions=definition.visible_conditions,
            evaluator=evaluate_generalization_skill,
            draft=draft,
            repair=repair,
            preflight=preflight,
            seed_base=session_seed,
            initial_width=6,
            survivor_count=3,
            repair_rounds=6,
        )
        write_canonical_json(search_path, search)
        _bind_checkpoint(
            search_path,
            {
                "session_manifest_sha256": session_manifest_sha256,
                "search_sha256": _payload_hash(search),
            },
        )

    if search.selected is None:
        transport = _transport_evidence(output_dir)
        summary = {
            "schema_version": "proprio.generalization_session.v0.3",
            "instrument_id": instrument_id,
            "session_index": session_index,
            "seed_base": session_seed,
            "method_sha256": freeze["method_sha256"],
            "panel_manifest_sha256": panel_manifest_sha256,
            "session_manifest_sha256": session_manifest_sha256,
            "source_sha256": source_hash,
            "search_verdict": search.verdict,
            "locked_verdict": "NOT_RUN",
            "final_decision": "HOLD",
            "candidate_variants": search.model_candidates_generated,
            "transport": transport,
            "protocol_valid": transport["verdict"] == "PASS",
        }
        write_canonical_json(output_dir / "summary.json", summary)
        return summary

    candidate_sha = _candidate_hash(search.selected.skill_py)
    seal = {
        "schema_version": "proprio.generalization_selection_seal.v0.3",
        "instrument_id": instrument_id,
        "candidate_sha256": candidate_sha,
        "source_sha256": source_hash,
        "method_sha256": freeze["method_sha256"],
        "session_seed": session_seed,
        "feedback_after_seal_prohibited": True,
    }
    seal["seal_sha256"] = hashlib.sha256(canonical_json(seal)).hexdigest()
    seal_path = output_dir / "selection-seal.json"
    if seal_path.is_file() and _read_json(seal_path) != seal:
        raise RuntimeError("partial session selection seal does not match the selected candidate")
    write_canonical_json(seal_path, seal)

    locked_path = output_dir / "locked-qualification.json"
    if locked_path.is_file():
        locked = DebugSuiteResult.model_validate_json(locked_path.read_text(encoding="utf-8"))
        if locked.candidate_sha256 != candidate_sha:
            raise RuntimeError("partial session locked qualification has the wrong candidate")
        _verify_checkpoint_binding(
            locked_path,
            {
                "session_manifest_sha256": session_manifest_sha256,
                "candidate_sha256": candidate_sha,
                "selection_seal_sha256": seal["seal_sha256"],
                "locked_conditions_sha256": _conditions_hash(definition.locked_conditions),
                "qualification_sha256": _payload_hash(locked),
            },
        )
    else:
        locked = evaluate_debug_suite(
            search.selected,
            definition.locked_conditions,
            evaluator=evaluate_generalization_skill,
        )
        write_canonical_json(locked_path, locked)
        _bind_checkpoint(
            locked_path,
            {
                "session_manifest_sha256": session_manifest_sha256,
                "candidate_sha256": candidate_sha,
                "selection_seal_sha256": seal["seal_sha256"],
                "locked_conditions_sha256": _conditions_hash(definition.locked_conditions),
                "qualification_sha256": _payload_hash(locked),
            },
        )
    locked_verdict = {
        "ADMIT": "PASS",
        "REJECT": "FAIL",
        "HOLD": "HOLD",
    }[locked.verdict]
    final_decision = {
        "PASS": "ADMIT",
        "FAIL": "REJECT",
        "HOLD": "HOLD",
    }[locked_verdict]
    causal_parent = _select_causal_parent(search, instrument_id)
    if causal_parent is None:
        causal = {
            "schema_version": "proprio.generalization_causal_pair.v0.3",
            "instrument_id": instrument_id,
            "status": "INELIGIBLE",
            "reason": "no self-accepted nominal success failed the registered visible change",
            "outcomes": {},
        }
        write_canonical_json(output_dir / "causal" / "summary.json", causal)
    else:
        causal = _run_causal_pair(
            causal_parent,
            definition=definition,
            seed=session_seed + 7_000,
            output_dir=output_dir / "causal",
        )

    truthful = causal.get("outcomes", {}).get("truthful", {})
    truthful_repair_regressed = False
    truthful_historical_verdict = "NOT_RUN"
    if truthful.get("qualified") is True and truthful.get("final_candidate"):
        truthful_candidate = CandidatePackage.model_validate(truthful["final_candidate"])
        truthful_historical = evaluate_debug_suite(
            truthful_candidate,
            definition.acquisition_conditions,
            evaluator=evaluate_generalization_skill,
        )
        truthful_historical_verdict = truthful_historical.verdict
        truthful_repair_regressed = truthful_historical.verdict != "ADMIT"
        write_canonical_json(
            output_dir / "causal" / "truthful-historical-replay.json",
            truthful_historical,
        )

    if final_decision == "ADMIT":
        evolution = _run_evolution_proposal(
            search.selected,
            definition=definition,
            seed=session_seed + 8_000,
            output_dir=output_dir / "evolution",
        )
    else:
        evolution = {
            "schema_version": "proprio.generalization_evolution_proposal.v0.3",
            "instrument_id": instrument_id,
            "status": "NOT_RUN",
            "reason": "selected skill did not pass locked qualification",
            "hardware_qualification_required": True,
        }
        write_canonical_json(output_dir / "evolution" / "summary.json", evolution)
    summary = {
        "schema_version": "proprio.generalization_session.v0.3",
        "instrument_id": instrument_id,
        "family": definition.family,
        "session_index": session_index,
        "seed_base": session_seed,
        "method_sha256": freeze["method_sha256"],
        "panel_manifest_sha256": panel_manifest_sha256,
        "session_manifest_sha256": session_manifest_sha256,
        "source_sha256": source_hash,
        "candidate_sha256": candidate_sha,
        "seal_sha256": seal["seal_sha256"],
        "search_verdict": search.verdict,
        "selected_visible_verdict": search.selected_suite.verdict,
        "locked_verdict": locked_verdict,
        "final_decision": final_decision,
        "candidate_variants": search.model_candidates_generated,
        "repair_records": len(search.repairs),
        "model": search.selected.model,
        "provenance_valid": search.selected.source_sha256 == source_hash,
        "causal_status": causal.get("status", "ELIGIBLE"),
        "truthful_repair_qualified": causal.get("outcomes", {})
        .get("truthful", {})
        .get("qualified", False),
        "no_feedback_repair_qualified": causal.get("outcomes", {})
        .get("none", {})
        .get("qualified", False),
        "truthful_historical_verdict": truthful_historical_verdict,
        "truthful_repair_regressed": truthful_repair_regressed,
        "evolution_status": evolution["status"],
    }
    transport = _transport_evidence(output_dir)
    summary["transport"] = transport
    summary["protocol_valid"] = transport["verdict"] == "PASS"
    if transport["verdict"] != "PASS":
        summary["final_decision"] = "HOLD"
        summary["truthful_repair_qualified"] = False
        summary["no_feedback_repair_qualified"] = False
        summary["evolution_status"] = "PROTOCOL_INVALID"
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def _one_sided_exact_p(truthful_only: int, no_feedback_only: int) -> float:
    discordant = truthful_only + no_feedback_only
    if discordant == 0 or truthful_only <= no_feedback_only:
        return 1.0
    return sum(
        math.comb(discordant, successes) for successes in range(truthful_only, discordant + 1)
    ) / (2**discordant)


def _transport_evidence(root: Path) -> dict[str, Any]:
    responses: dict[str, dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("object") == "chat.completion" and isinstance(value.get("id"), str):
                responses[value["id"]] = value
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for path in root.rglob("*.json"):
        try:
            visit(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    providers = sorted({str(row.get("provider")) for row in responses.values()})
    models = sorted({str(row.get("model")) for row in responses.values()})
    reasoning_missing = 0
    successful_responses = 0
    error_responses = 0
    total_tokens = 0
    total_cost = 0.0
    for row in responses.values():
        finish_reason = (row.get("choices") or [{}])[0].get("finish_reason")
        if finish_reason == "error":
            error_responses += 1
            continue
        successful_responses += 1
        message = row.get("preserved_assistant_message") or row.get("choices", [{}])[0].get(
            "message", {}
        )
        if not any(
            message.get(key)
            for key in ("reasoning", "reasoning_details", "reasoning_content")
        ):
            reasoning_missing += 1
    for row in responses.values():
        usage = row.get("usage") or {}
        total_tokens += int(usage.get("total_tokens") or 0)
        total_cost += float(usage.get("cost") or 0.0)
    passed = (
        successful_responses > 0
        and set(providers).issubset(EXPECTED_PROVIDERS)
        and models == [EXPECTED_RESOLVED_MODEL]
        and reasoning_missing == 0
    )
    return {
        "responses": len(responses),
        "successful_responses": successful_responses,
        "error_responses": error_responses,
        "providers": providers,
        "resolved_models": models,
        "reasoning_missing": reasoning_missing,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "verdict": "PASS" if passed else "FAIL",
    }


def summarize_generalization_panel(
    root: Path,
    *,
    sessions_per_family: int,
) -> dict[str, Any]:
    config = yaml.safe_load(
        (ROOT / "src/proprio/data/generalization-v0.3-method.yaml").read_text(encoding="utf-8")
    )
    thresholds = config["per_family_claim_gates"]
    families = []
    for instrument_id, definition in GENERALIZATION_INSTRUMENTS.items():
        rows = []
        for index in range(sessions_per_family):
            path = root / instrument_id / f"session-{index:03d}" / "summary.json"
            if path.is_file():
                rows.append(_read_json(path))
        protocol_valid_rows = [row for row in rows if row.get("protocol_valid") is True]
        qualification_successes = sum(
            row.get("final_decision") == "ADMIT" for row in protocol_valid_rows
        )
        truthful_successes = sum(
            row.get("truthful_repair_qualified") is True for row in protocol_valid_rows
        )
        no_feedback_successes = sum(
            row.get("no_feedback_repair_qualified") is True for row in protocol_valid_rows
        )
        truthful_only = sum(
            row.get("truthful_repair_qualified") is True
            and row.get("no_feedback_repair_qualified") is not True
            for row in protocol_valid_rows
        )
        no_feedback_only = sum(
            row.get("truthful_repair_qualified") is not True
            and row.get("no_feedback_repair_qualified") is True
            for row in protocol_valid_rows
        )
        evolution_successes = sum(
            row.get("evolution_status") == "STAGED" for row in protocol_valid_rows
        )
        regression_count = sum(
            row.get("truthful_repair_qualified") is True
            and row.get("truthful_repair_regressed") is True
            for row in protocol_valid_rows
        )
        regression_rate = regression_count / truthful_successes if truthful_successes else 0.0
        denominator = sessions_per_family
        qualification_rate = qualification_successes / denominator
        truthful_rate = truthful_successes / denominator
        no_feedback_rate = no_feedback_successes / denominator
        uplift = truthful_rate - no_feedback_rate
        evolution_rate = evolution_successes / denominator
        exact_p = _one_sided_exact_p(truthful_only, no_feedback_only)
        gates = {
            "complete": "PASS" if len(rows) == sessions_per_family else "FAIL",
            "transport_integrity": (
                "PASS" if len(protocol_valid_rows) == sessions_per_family else "FAIL"
            ),
            "breadth": "PASS" if qualification_successes >= 1 else "FAIL",
            "repeated_qualification": (
                "PASS"
                if qualification_rate >= thresholds["repeated_qualification_minimum"]
                else "FAIL"
            ),
            "truthful_repair": (
                "PASS" if truthful_rate >= thresholds["truthful_repair_minimum"] else "FAIL"
            ),
            "causal_uplift": (
                "PASS"
                if uplift >= thresholds["truthful_minus_no_feedback_minimum"]
                and exact_p <= thresholds["exact_one_sided_p_maximum"]
                else "FAIL"
            ),
            "drift_evolution": (
                "PASS" if evolution_rate >= thresholds["drift_evolution_minimum"] else "FAIL"
            ),
            "regression_control": (
                "PASS" if regression_rate <= thresholds["regression_rate_maximum"] else "FAIL"
            ),
            "invalid_promotion": (
                "PASS"
                if all(
                    not (
                        row.get("final_decision") == "ADMIT"
                        and not (
                            row.get("protocol_valid") is True
                            and row.get("locked_verdict") == "PASS"
                            and row.get("selected_visible_verdict") == "ADMIT"
                            and row.get("provenance_valid") is True
                        )
                    )
                    for row in rows
                )
                else "FAIL"
            ),
        }
        families.append(
            {
                "instrument_id": instrument_id,
                "family": definition.family,
                "completed_sessions": len(rows),
                "protocol_valid_sessions": len(protocol_valid_rows),
                "registered_sessions": sessions_per_family,
                "qualification_successes": qualification_successes,
                "qualification_rate": qualification_rate,
                "truthful_repair_successes": truthful_successes,
                "truthful_repair_rate": truthful_rate,
                "no_feedback_repair_successes": no_feedback_successes,
                "no_feedback_repair_rate": no_feedback_rate,
                "causal_uplift": uplift,
                "truthful_only_pairs": truthful_only,
                "no_feedback_only_pairs": no_feedback_only,
                "one_sided_exact_p": exact_p,
                "evolution_successes": evolution_successes,
                "evolution_rate": evolution_rate,
                "truthful_repair_regressions": regression_count,
                "truthful_repair_regression_rate": regression_rate,
                "claim_gates": gates,
                "verdict": "PASS" if all(value == "PASS" for value in gates.values()) else "FAIL",
            }
        )
    result = {
        "schema_version": "proprio.generalization_panel.v0.3",
        "registered_instruments": list(GENERALIZATION_INSTRUMENTS),
        "sessions_per_family": sessions_per_family,
        "promotion_authority": "deterministic-execution-and-physical-gates",
        "claim_boundary": (
            "simulation-only pre-deployment qualification; real-hardware qualification "
            "remains separate"
        ),
        "families": families,
        "verdict": (
            "PASS"
            if families and all(family["verdict"] == "PASS" for family in families)
            else "FAIL"
        ),
    }
    write_canonical_json(root / "summary.json", result)
    return result


def run_live_generalization_panel(
    output_dir: Path,
    *,
    sessions_per_family: int = 30,
    freeze_path: Path = DEFAULT_FREEZE,
    seed_base: int = 2_000_000,
) -> dict[str, Any]:
    """Run or resume the binding panel without replacing any registered result."""

    if sessions_per_family != BINDING_SESSIONS_PER_FAMILY:
        raise ValueError(
            f"binding panel requires exactly {BINDING_SESSIONS_PER_FAMILY} sessions per family"
        )
    if seed_base != BINDING_SEED_BASE:
        raise ValueError(f"binding panel seed_base must be {BINDING_SEED_BASE}")
    freeze = _read_json(freeze_path)
    verification = verify_generalization_method(freeze_path)
    if verification["verdict"] != "PASS":
        raise RuntimeError("v0.3 method freeze did not verify before the binding panel")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "proprio.generalization_panel_manifest.v0.3",
        "method_sha256": freeze["method_sha256"],
        "instrument_ids": list(GENERALIZATION_INSTRUMENTS),
        "sessions_per_family": sessions_per_family,
        "seed_base": seed_base,
        "model": "deepseek/deepseek-v4-flash",
        "provider_order": list(EXPECTED_PROVIDER_ROUTE.split(",")),
        "provider_allowlist": list(EXPECTED_PROVIDER_ROUTE.split(",")),
        "resolved_model": EXPECTED_RESOLVED_MODEL,
        "replacement_prohibited": True,
        "post_exposure_method_changes_prohibited": True,
    }
    manifest["panel_manifest_sha256"] = _payload_hash(manifest)
    manifest_path = output_dir / "run-manifest.json"
    if manifest_path.is_file() and _read_json(manifest_path) != manifest:
        raise RuntimeError("existing binding manifest does not match the frozen panel")
    write_canonical_json(manifest_path, manifest)
    panel_manifest_sha256 = manifest["panel_manifest_sha256"]

    for session_index in range(sessions_per_family):
        for instrument_id in GENERALIZATION_INSTRUMENTS:
            session_dir = output_dir / instrument_id / f"session-{session_index:03d}"
            summary_path = session_dir / "summary.json"
            if summary_path.is_file():
                prior = _read_json(summary_path)
                if (
                    prior.get("method_sha256") != freeze["method_sha256"]
                    or prior.get("panel_manifest_sha256") != panel_manifest_sha256
                    or prior.get("session_manifest_sha256")
                    != _read_json(session_dir / "session-manifest.json").get(
                        "session_manifest_sha256"
                    )
                ):
                    raise RuntimeError(f"completed session has the wrong method: {summary_path}")
                continue
            run_live_generalization_session(
                instrument_id,
                session_index=session_index,
                output_dir=session_dir,
                freeze_path=freeze_path,
                seed_base=seed_base,
                panel_manifest_sha256=panel_manifest_sha256,
            )
            summarize_generalization_panel(
                output_dir,
                sessions_per_family=sessions_per_family,
            )
    return summarize_generalization_panel(
        output_dir,
        sessions_per_family=sessions_per_family,
    )
