"""Frozen cross-family qualification with persistent simulator-grounded repair."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from proprio.agent import (
    AgentModelConfig,
    AgentState,
    append_verifier_record,
    arm_feedback_view,
    branch_agent_state,
    initial_agent_state,
    repeated_failed_strategy_count,
    resume_agent_state,
    run_agent_cycle,
)
from proprio.artifacts import source_sha256, write_canonical_json
from proprio.external_instruments import (
    EXTERNAL_INSTRUMENTS,
    ExternalRuntimeUnavailable,
    evaluate_external_skill,
    external_simulator_identity,
    load_external_source,
    run_external_preflight,
)
from proprio.instrument_types import CandidatePackage, FeedbackArm
from proprio.policy import DSV4Client
from proprio.schema import canonical_json
from proprio.skill_agent import SkillAgent
from proprio.skill_search import (
    PROCEDURAL_CHECKS,
    DebugCondition,
    DebugSuiteResult,
    RepairOutcome,
    SearchReport,
    evaluate_debug_suite,
    run_archive_search,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_ROOT = ROOT / "artifacts/evidence/cross-family/qualification"
EXPECTED_PROVIDER_ROUTE = "DeepInfra,GMICloud"
EXPECTED_PROVIDERS = frozenset({"DeepInfra", "GMICloud"})
EXPECTED_RESOLVED_MODEL = "deepseek/deepseek-v4-flash-20260423"

BINDING_SEED_BASE = 2_400_000
DEFAULT_COMPACTION_BYTE_LIMIT = 240_000
CAUSAL_VERIFIER_CYCLES = 4
EVOLUTION_VERIFIER_CYCLES = 6
CAUSAL_MODEL_CALL_BUDGET = 64
CAUSAL_TOKEN_BUDGET = 600_000
EVOLUTION_MODEL_CALL_BUDGET = 96
EVOLUTION_TOKEN_BUDGET = 900_000

REPAIR_TRAJECTORY_SCHEMA = "proprio.cross_family_repair_trajectory.v0.4"
CAUSAL_PAIR_SCHEMA = "proprio.cross_family_causal_pair.v0.4"
EVOLUTION_SCHEMA = "proprio.cross_family_evolution_proposal.v0.4"
SESSION_SCHEMA = "proprio.cross_family_session.v0.4"
SESSION_MANIFEST_SCHEMA = "proprio.cross_family_session_manifest.v0.4"
METHOD_FREEZE_SCHEMA = "proprio.cross_family_method_freeze.v0.4"
METHOD_VERIFICATION_SCHEMA = "proprio.cross_family_method_verification.v0.4"
PANEL_SCHEMA = "proprio.cross_family_panel.v0.4"
PANEL_MANIFEST_SCHEMA = "proprio.cross_family_panel_manifest.v0.4"

METHOD_INPUTS = (
    "pyproject.toml",
    "uv.lock",
    *(str(path.relative_to(ROOT)) for path in sorted((ROOT / "src/proprio").glob("*.py"))),
    "src/proprio/data/method.yaml",
    "sources/instruments/north-pipette-calibration/source.md",
    "sources/instruments/helao-gamry-cv/source.md",
    "sources/instruments/clslab-light-spectrometer/source.md",
)

TRAJECTORY_GOAL = (
    "Repair the current candidate so every registered condition in this trajectory admits under "
    "the independent verifier. This is one continuous persistent agent context across the verifier "
    "cycles: consult the earlier assistant turns, tool results, the repair ledger, and the latest "
    "verifier evidence before each action, make the smallest evidence-grounded change, replay the "
    "simulator after every submitted repair, and finish with CANDIDATE only after a post-edit "
    "replay admits. Return an honest HOLD when the execution evidence does not support a safe edit."
)

CLAIM_BOUNDARY = (
    "Cross-family external-simulator replication of the persistent-context method. The three "
    "families were screened before the binding run, so this is not an untouched first-exposure "
    "study. Simulation-only pre-deployment qualification; real-hardware "
    "qualification remains separate."
)


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


def _conditions_hash(conditions: Sequence[Any]) -> str:
    return _payload_hash([condition.model_dump(mode="json") for condition in conditions])


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


def _draft_agent(*, seed: int, temperature: float, top_p: float) -> SkillAgent:
    client = DSV4Client()
    if "openrouter.ai" in client.base_url and client.provider != EXPECTED_PROVIDER_ROUTE:
        client.close()
        raise RuntimeError(
            "binding route must use "
            f"{EXPECTED_PROVIDER_ROUTE}, observed {client.provider or 'unset'}"
        )
    return SkillAgent(
        client=client,
        source_loader=load_external_source,
        evaluator=evaluate_external_skill,
        families={
            instrument_id: definition.family
            for instrument_id, definition in EXTERNAL_INSTRUMENTS.items()
        },
        sampling_temperature=temperature,
        sampling_top_p=top_p,
        sampling_seed=seed,
    )


def _select_causal_parent(search: Any, instrument_id: str) -> CandidatePackage | None:
    definition = EXTERNAL_INSTRUMENTS[instrument_id]
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
            evaluator=evaluate_external_skill,
        )
        changed = evaluate_debug_suite(
            candidate,
            definition.visible_conditions,
            evaluator=evaluate_external_skill,
        )
        if acquisition.verdict == "ADMIT" and changed.verdict == "REJECT":
            eligible.append(candidate)
    return min(eligible, key=lambda item: _candidate_hash(item.skill_py)) if eligible else None


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
            message.get(key) for key in ("reasoning", "reasoning_details", "reasoning_content")
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


def _agent_client() -> DSV4Client:
    client = DSV4Client()
    if "openrouter.ai" in client.base_url and client.provider != EXPECTED_PROVIDER_ROUTE:
        client.close()
        observed = client.provider or "unset"
        raise RuntimeError(f"binding route must use {EXPECTED_PROVIDER_ROUTE}, observed {observed}")
    return client


def _run_config(client: DSV4Client, seed: int) -> AgentModelConfig:
    return AgentModelConfig(
        requested_model=client.model,
        provider_route=client.provider or "",
        temperature=0.0,
        top_p=1.0,
        seed=seed,
    )


def _procedural_clean(suite: DebugSuiteResult) -> bool:
    return not any(
        not check.passed
        for condition in suite.conditions
        for gate in condition.gates
        for check in gate.checks
        if check.check_id in PROCEDURAL_CHECKS
    )


def _ensure_verifier_record(
    state: AgentState,
    *,
    conditions: Sequence[DebugCondition],
    output_dir: Path,
) -> AgentState:
    current_hash = _candidate_hash(state.current_candidate.skill_py)
    record = state.latest_verifier_record
    if record is not None and record.candidate_sha256 == current_hash:
        return state
    suite = evaluate_debug_suite(
        state.current_candidate, conditions, evaluator=evaluate_external_skill
    )
    view, _ = arm_feedback_view(suite, state.feedback_arm)
    return append_verifier_record(state, suite, exposed_view=view, checkpoint_dir=output_dir)


def _drive_persistent_trajectory(
    *,
    state: AgentState,
    client: DSV4Client,
    source: str,
    parent: CandidatePackage,
    conditions: Sequence[DebugCondition],
    locked_conditions: Sequence[DebugCondition],
    output_dir: Path,
    verifier_cycles: int,
    compaction_byte_limit: int | None,
    feedback_arm: FeedbackArm,
) -> dict[str, Any]:
    context_bytes_by_cycle: list[int] = []
    cycles_used = 0
    while state.status == "ACTIVE" and cycles_used < verifier_cycles:
        state = _ensure_verifier_record(state, conditions=conditions, output_dir=output_dir)
        context_bytes_by_cycle.append(len(canonical_json(state.messages)))
        state = run_agent_cycle(
            state,
            client=client,
            evaluator=evaluate_external_skill,
            source=source,
            conditions=conditions,
            checkpoint_dir=output_dir,
            compaction_byte_limit=compaction_byte_limit,
        )
        cycles_used += 1
        context_bytes_by_cycle.append(len(canonical_json(state.messages)))

    visible = evaluate_debug_suite(
        state.current_candidate, conditions, evaluator=evaluate_external_skill
    )
    write_canonical_json(output_dir / "visible-final.json", visible)
    locked = evaluate_debug_suite(
        state.current_candidate, locked_conditions, evaluator=evaluate_external_skill
    )
    write_canonical_json(output_dir / "locked-qualification.json", locked)

    qualified = bool(
        state.status == "CANDIDATE" and visible.verdict == "ADMIT" and locked.verdict == "ADMIT"
    )
    parent_hash = _candidate_hash(parent.skill_py)
    final_hash = _candidate_hash(state.current_candidate.skill_py)
    duplicate_candidate_count = sum(
        1 for entry in state.repair_ledger if entry.outcome == "DUPLICATE"
    )
    context_bytes_final = len(canonical_json(state.messages))
    compaction_applied = bool(
        compaction_byte_limit is not None and context_bytes_final > compaction_byte_limit
    )
    result = {
        "schema_version": REPAIR_TRAJECTORY_SCHEMA,
        "instrument_id": parent.instrument_id,
        "feedback_arm": feedback_arm.value,
        "qualified": qualified,
        "agent_status": state.status,
        "visible_verdict": visible.verdict,
        "locked_verdict": locked.verdict,
        "verifier_cycles_used": cycles_used,
        "consumed_model_calls": state.consumed_model_calls,
        "consumed_tokens": state.consumed_tokens,
        "model_call_budget": state.model_call_budget,
        "token_budget": state.token_budget,
        "repair_ledger": [entry.model_dump(mode="json") for entry in state.repair_ledger],
        "duplicate_candidate_count": duplicate_candidate_count,
        "repeated_failed_strategy_count": repeated_failed_strategy_count(state),
        "context_bytes_final": context_bytes_final,
        "context_bytes_by_cycle": context_bytes_by_cycle,
        "compaction_byte_limit": compaction_byte_limit,
        "compaction_applied": compaction_applied,
        "candidate_chain_sha256": [
            parent_hash,
            *[entry.candidate_sha256 for entry in state.repair_ledger],
        ],
        "parent_sha256": parent_hash,
        "final_sha256": final_hash,
        "model_call_efficiency": (
            1.0 / state.consumed_model_calls if qualified and state.consumed_model_calls else 0.0
        ),
        "final_candidate": state.current_candidate.model_dump(mode="json"),
    }
    write_canonical_json(output_dir / "trajectory-summary.json", result)
    return result


def run_persistent_repair_trajectory(
    parent: CandidatePackage,
    *,
    definition: Any,
    conditions: Sequence[DebugCondition],
    locked_conditions: Sequence[DebugCondition],
    feedback_arm: FeedbackArm,
    seed: int,
    output_dir: Path,
    verifier_cycles: int,
    model_call_budget: int,
    token_budget: int,
    compaction_byte_limit: int | None,
) -> dict[str, Any]:
    del definition
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "trajectory-summary.json"
    if summary_path.is_file():
        return _read_json(summary_path)
    source, source_hash = load_external_source(parent.instrument_id)
    client = _agent_client()
    try:
        resumed = resume_agent_state(output_dir)
        if resumed is None:
            state = initial_agent_state(
                instrument_id=parent.instrument_id,
                feedback_arm=feedback_arm.value,
                source=source,
                source_sha256=source_hash,
                candidate=parent,
                conditions=conditions,
                run_config=_run_config(client, seed),
                model_call_budget=model_call_budget,
                token_budget=token_budget,
                goal=TRAJECTORY_GOAL,
            )
        else:
            state = resumed
        result = _drive_persistent_trajectory(
            state=state,
            client=client,
            source=source,
            parent=parent,
            conditions=conditions,
            locked_conditions=locked_conditions,
            output_dir=output_dir,
            verifier_cycles=verifier_cycles,
            compaction_byte_limit=compaction_byte_limit,
            feedback_arm=feedback_arm,
        )
    finally:
        client.close()
    return result


def run_persistent_causal_pair(
    search: SearchReport,
    *,
    definition: Any,
    seed: int,
    output_dir: Path,
    compaction_byte_limit: int | None = DEFAULT_COMPACTION_BYTE_LIMIT,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    if summary_path.is_file():
        return _read_json(summary_path)
    parent = _select_causal_parent(search, definition.instrument_id)
    if parent is None:
        result = {
            "schema_version": CAUSAL_PAIR_SCHEMA,
            "instrument_id": definition.instrument_id,
            "status": "INELIGIBLE",
            "reason": "no self-accepted nominal success failed the registered visible change",
            "paired_seed": seed,
            "shared_prefix_sha256": None,
            "same_parent": False,
            "truthful_repair_regressed": False,
            "truthful_historical_verdict": "NOT_RUN",
            "outcomes": {},
        }
        write_canonical_json(summary_path, result)
        return result

    source, source_hash = load_external_source(parent.instrument_id)
    client = _agent_client()
    try:
        prefix = initial_agent_state(
            instrument_id=definition.instrument_id,
            feedback_arm=FeedbackArm.TRUTHFUL.value,
            source=source,
            source_sha256=source_hash,
            candidate=parent,
            conditions=definition.visible_conditions,
            run_config=_run_config(client, seed),
            model_call_budget=CAUSAL_MODEL_CALL_BUDGET,
            token_budget=CAUSAL_TOKEN_BUDGET,
            goal=TRAJECTORY_GOAL,
        )
        shared_prefix_sha256 = hashlib.sha256(canonical_json(prefix.messages)).hexdigest()
        outcomes: dict[str, Any] = {}
        for arm in (FeedbackArm.TRUTHFUL, FeedbackArm.NONE):
            arm_dir = output_dir / arm.value
            arm_dir.mkdir(parents=True, exist_ok=True)
            arm_summary_path = arm_dir / "trajectory-summary.json"
            if arm_summary_path.is_file():
                outcomes[arm.value] = _read_json(arm_summary_path)
                continue
            resumed = resume_agent_state(arm_dir)
            state = (
                resumed
                if resumed is not None
                else branch_agent_state(prefix, feedback_arm=arm.value)
            )
            outcomes[arm.value] = _drive_persistent_trajectory(
                state=state,
                client=client,
                source=source,
                parent=parent,
                conditions=definition.visible_conditions,
                locked_conditions=definition.locked_conditions,
                output_dir=arm_dir,
                verifier_cycles=CAUSAL_VERIFIER_CYCLES,
                compaction_byte_limit=compaction_byte_limit,
                feedback_arm=arm,
            )
    finally:
        client.close()

    truthful = outcomes.get(FeedbackArm.TRUTHFUL.value, {})
    truthful_repair_regressed = False
    truthful_historical_verdict = "NOT_RUN"
    if truthful.get("qualified") is True and truthful.get("final_candidate"):
        truthful_candidate = CandidatePackage.model_validate(truthful["final_candidate"])
        historical = evaluate_debug_suite(
            truthful_candidate,
            definition.acquisition_conditions,
            evaluator=evaluate_external_skill,
        )
        write_canonical_json(output_dir / "truthful-historical-replay.json", historical)
        truthful_historical_verdict = historical.verdict
        truthful_repair_regressed = historical.verdict != "ADMIT"

    result = {
        "schema_version": CAUSAL_PAIR_SCHEMA,
        "instrument_id": definition.instrument_id,
        "status": "ELIGIBLE",
        "paired_seed": seed,
        "shared_prefix_sha256": shared_prefix_sha256,
        "same_parent": len({row["parent_sha256"] for row in outcomes.values()}) == 1,
        "promotion_authority": "deterministic-visible-and-locked-gates",
        "truthful_repair_regressed": truthful_repair_regressed,
        "truthful_historical_verdict": truthful_historical_verdict,
        "outcomes": outcomes,
    }
    write_canonical_json(summary_path, result)
    return result


def run_persistent_evolution_proposal(
    parent: CandidatePackage,
    *,
    definition: Any,
    seed: int,
    output_dir: Path,
    compaction_byte_limit: int | None = DEFAULT_COMPACTION_BYTE_LIMIT,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    if summary_path.is_file():
        return _read_json(summary_path)
    drift = evaluate_debug_suite(
        parent, definition.evolution_conditions, evaluator=evaluate_external_skill
    )
    write_canonical_json(output_dir / "drift-detection.json", drift)
    if drift.verdict != "REJECT":
        result = {
            "schema_version": EVOLUTION_SCHEMA,
            "instrument_id": parent.instrument_id,
            "status": "HOLD",
            "reason": "registered deployment drift did not invalidate the admitted parent",
            "parent_sha256": _candidate_hash(parent.skill_py),
            "drift_detected": False,
            "hardware_qualification_required": True,
        }
        write_canonical_json(summary_path, result)
        return result

    trajectory = run_persistent_repair_trajectory(
        parent,
        definition=definition,
        conditions=definition.visible_conditions + definition.evolution_conditions,
        locked_conditions=definition.locked_conditions,
        feedback_arm=FeedbackArm.TRUTHFUL,
        seed=seed,
        output_dir=output_dir / "repair",
        verifier_cycles=EVOLUTION_VERIFIER_CYCLES,
        model_call_budget=EVOLUTION_MODEL_CALL_BUDGET,
        token_budget=EVOLUTION_TOKEN_BUDGET,
        compaction_byte_limit=compaction_byte_limit,
    )
    proposal = CandidatePackage.model_validate(trajectory["final_candidate"])
    acquisition = evaluate_debug_suite(
        proposal, definition.acquisition_conditions, evaluator=evaluate_external_skill
    )
    evolution = evaluate_debug_suite(
        proposal, definition.evolution_conditions, evaluator=evaluate_external_skill
    )
    qualified = bool(
        trajectory["qualified"] and acquisition.verdict == "ADMIT" and evolution.verdict == "ADMIT"
    )
    result = {
        "schema_version": EVOLUTION_SCHEMA,
        "instrument_id": parent.instrument_id,
        "status": "STAGED" if qualified else "REJECTED",
        "reason": (
            "drift detected; proposal passed visible, historical, evolution, and locked checks"
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


def _session_manifest_payload(
    *,
    instrument_id: str,
    session_index: int,
    session_seed: int,
    method_sha256: str,
    source_sha256_value: str,
    definition: Any,
    panel_manifest_sha256: str | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": SESSION_MANIFEST_SCHEMA,
        "study_mode": "binding" if panel_manifest_sha256 else "engineering",
        "panel_manifest_sha256": panel_manifest_sha256,
        "method_sha256": method_sha256,
        "instrument_id": instrument_id,
        "session_index": session_index,
        "session_seed": session_seed,
        "source_sha256": source_sha256_value,
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
        },
        "persistent_context": {
            "causal_verifier_cycles": CAUSAL_VERIFIER_CYCLES,
            "evolution_verifier_cycles": EVOLUTION_VERIFIER_CYCLES,
            "causal_model_call_budget": CAUSAL_MODEL_CALL_BUDGET,
            "evolution_model_call_budget": EVOLUTION_MODEL_CALL_BUDGET,
            "causal_token_budget": CAUSAL_TOKEN_BUDGET,
            "evolution_token_budget": EVOLUTION_TOKEN_BUDGET,
            "compaction_byte_limit": DEFAULT_COMPACTION_BYTE_LIMIT,
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


def _first_qualified_metric(causal: dict[str, Any], key: str) -> int:
    for arm in (FeedbackArm.TRUTHFUL.value, FeedbackArm.NONE.value):
        row = causal.get("outcomes", {}).get(arm, {})
        if isinstance(row, dict) and row.get("qualified") is True:
            value = row.get(key, 0)
            return int(value) if isinstance(value, (int, float)) else 0
    return 0


def _persistent_trajectories(causal: dict[str, Any], evolution: dict[str, Any]) -> list[dict]:
    rows: list[dict[str, Any]] = []
    for arm in (FeedbackArm.TRUTHFUL.value, FeedbackArm.NONE.value):
        row = causal.get("outcomes", {}).get(arm)
        if isinstance(row, dict) and "consumed_model_calls" in row:
            rows.append(row)
    evolution_trajectory = evolution.get("trajectory") if isinstance(evolution, dict) else None
    if isinstance(evolution_trajectory, dict) and "consumed_model_calls" in evolution_trajectory:
        rows.append(evolution_trajectory)
    return rows


def run_cross_family_session(
    instrument_id: str,
    output_dir: Path,
    *,
    session_index: int = 0,
    freeze_path: Path,
    seed_base: int = BINDING_SEED_BASE,
    panel_manifest_sha256: str | None = None,
    compaction_byte_limit: int | None = DEFAULT_COMPACTION_BYTE_LIMIT,
) -> dict[str, Any]:
    if instrument_id not in EXTERNAL_INSTRUMENTS:
        raise KeyError(instrument_id)
    output_dir = Path(output_dir)
    freeze_verification = verify_cross_family_method(freeze_path)
    if freeze_verification["verdict"] != "PASS":
        raise RuntimeError("cross-family method freeze did not verify before model generation")
    freeze = _read_json(freeze_path)
    preflight = run_external_preflight(instrument_id)
    if preflight.verdict != "PASS":
        raise RuntimeError("external simulator preflight failed before model generation")

    definition = EXTERNAL_INSTRUMENTS[instrument_id]
    session_seed = seed_base + session_index * 10_000
    _, source_hash = load_external_source(instrument_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "work"
    session_manifest = _session_manifest_payload(
        instrument_id=instrument_id,
        session_index=session_index,
        session_seed=session_seed,
        method_sha256=freeze["method_sha256"],
        source_sha256_value=source_hash,
        definition=definition,
        panel_manifest_sha256=panel_manifest_sha256,
    )
    _write_or_verify(
        output_dir / "session-manifest.json", session_manifest, label="session manifest"
    )
    session_manifest_sha256 = session_manifest["session_manifest_sha256"]

    def draft(seed: int) -> CandidatePackage:
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
        agent = _draft_agent(seed=seed, temperature=0.7, top_p=0.95)
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

    def repair(candidate: CandidatePackage, suite: DebugSuiteResult, seed: int) -> RepairOutcome:
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
        agent = _draft_agent(seed=seed, temperature=0.0, top_p=1.0)
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
            evaluator=evaluate_external_skill,
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

    first_entry = search.entries[0] if search.entries else None
    initial_skill_executable = bool(first_entry and _procedural_clean(first_entry.suite))
    initial_physical_validity = bool(first_entry and first_entry.suite.verdict == "ADMIT")

    if search.selected is None:
        transport = _transport_evidence(output_dir)
        summary = {
            "schema_version": SESSION_SCHEMA,
            "instrument_id": instrument_id,
            "family": definition.family,
            "session_index": session_index,
            "seed_base": session_seed,
            "method_sha256": freeze["method_sha256"],
            "panel_manifest_sha256": panel_manifest_sha256,
            "session_manifest_sha256": session_manifest_sha256,
            "source_sha256": source_hash,
            "search_verdict": search.verdict,
            "candidate_variants": search.model_candidates_generated,
            "locked_qualification": False,
            "locked_verdict": "NOT_RUN",
            "selected_visible_verdict": "NOT_RUN",
            "provenance_valid": False,
            "initial_skill_executable": initial_skill_executable,
            "initial_physical_validity": initial_physical_validity,
            "model_calls_to_first_qualified": 0,
            "tokens_to_first_qualified": 0,
            "truthful_repair_qualified": False,
            "none_repair_qualified": False,
            "repeated_failed_strategy_count": 0,
            "duplicate_candidate_count": 0,
            "drift_detected": False,
            "evolution_staged": False,
            "evolution_status": "NOT_RUN",
            "historical_regression": False,
            "invalid_promotion_count": 0,
            "transport_valid": transport["verdict"] == "PASS",
            "qualification_per_model_call": 0.0,
            "qualification_per_million_tokens": 0.0,
            "total_cost_usd": transport["total_cost_usd"],
            "context_growth": {},
            "compactions_applied": 0,
            "resume_idempotent": True,
            "final_decision": "HOLD",
            "verdict": "HOLD",
            "transport": transport,
            "protocol_valid": transport["verdict"] == "PASS",
        }
        write_canonical_json(output_dir / "summary.json", summary)
        return summary

    candidate_sha = _candidate_hash(search.selected.skill_py)
    seal = {
        "schema_version": "proprio.cross_family_selection_seal.v0.4",
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
            evaluator=evaluate_external_skill,
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
    locked_verdict = {"ADMIT": "PASS", "REJECT": "FAIL", "HOLD": "HOLD"}[locked.verdict]
    final_decision = {"PASS": "ADMIT", "FAIL": "REJECT", "HOLD": "HOLD"}[locked_verdict]
    provenance_valid = search.selected.source_sha256 == source_hash

    causal = run_persistent_causal_pair(
        search,
        definition=definition,
        seed=session_seed + 7_000,
        output_dir=output_dir / "causal",
        compaction_byte_limit=compaction_byte_limit,
    )

    if final_decision == "ADMIT":
        evolution = run_persistent_evolution_proposal(
            search.selected,
            definition=definition,
            seed=session_seed + 8_000,
            output_dir=output_dir / "evolution",
            compaction_byte_limit=compaction_byte_limit,
        )
    else:
        evolution = {
            "schema_version": EVOLUTION_SCHEMA,
            "instrument_id": instrument_id,
            "status": "NOT_RUN",
            "reason": "selected skill did not pass locked qualification",
            "drift_detected": False,
            "hardware_qualification_required": True,
        }
        (output_dir / "evolution").mkdir(parents=True, exist_ok=True)
        write_canonical_json(output_dir / "evolution" / "summary.json", evolution)

    truthful_repair_qualified = (
        causal.get("outcomes", {}).get(FeedbackArm.TRUTHFUL.value, {}).get("qualified", False)
    )
    none_repair_qualified = (
        causal.get("outcomes", {}).get(FeedbackArm.NONE.value, {}).get("qualified", False)
    )
    trajectories = _persistent_trajectories(causal, evolution)
    persistent_model_calls = sum(int(row.get("consumed_model_calls", 0)) for row in trajectories)
    persistent_tokens = sum(int(row.get("consumed_tokens", 0)) for row in trajectories)
    repeated_strategy = sum(
        int(row.get("repeated_failed_strategy_count", 0)) for row in trajectories
    )
    duplicate_candidates = sum(int(row.get("duplicate_candidate_count", 0)) for row in trajectories)
    compactions_applied = sum(1 for row in trajectories if row.get("compaction_applied") is True)
    qualified_trajectories = sum(1 for row in trajectories if row.get("qualified") is True)
    if evolution.get("status") == "STAGED":
        qualified_trajectories += 1
    drift_detected = bool(evolution.get("drift_detected") is True)
    evolution_staged = evolution.get("status") == "STAGED"
    historical_regression = bool(causal.get("truthful_repair_regressed") is True)
    invalid_promotion_count = int(
        final_decision == "ADMIT"
        and not (
            locked_verdict == "PASS"
            and search.selected_suite.verdict == "ADMIT"
            and provenance_valid
        )
    )

    transport = _transport_evidence(output_dir)
    context_growth = {
        FeedbackArm.TRUTHFUL.value: causal.get("outcomes", {})
        .get(FeedbackArm.TRUTHFUL.value, {})
        .get("context_bytes_by_cycle", []),
        FeedbackArm.NONE.value: causal.get("outcomes", {})
        .get(FeedbackArm.NONE.value, {})
        .get("context_bytes_by_cycle", []),
    }
    summary = {
        "schema_version": SESSION_SCHEMA,
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
        "candidate_variants": search.model_candidates_generated,
        "repair_records": len(search.repairs),
        "model": search.selected.model,
        "provenance_valid": provenance_valid,
        "causal_status": causal.get("status", "ELIGIBLE"),
        "shared_prefix_sha256": causal.get("shared_prefix_sha256"),
        "initial_skill_executable": initial_skill_executable,
        "initial_physical_validity": initial_physical_validity,
        "model_calls_to_first_qualified": _first_qualified_metric(causal, "consumed_model_calls"),
        "tokens_to_first_qualified": _first_qualified_metric(causal, "consumed_tokens"),
        "truthful_repair_qualified": truthful_repair_qualified,
        "none_repair_qualified": none_repair_qualified,
        "repeated_failed_strategy_count": repeated_strategy,
        "duplicate_candidate_count": duplicate_candidates,
        "locked_verdict": locked_verdict,
        "locked_qualification": locked_verdict == "PASS",
        "drift_detected": drift_detected,
        "evolution_status": evolution["status"],
        "evolution_staged": evolution_staged,
        "historical_regression": historical_regression,
        "invalid_promotion_count": invalid_promotion_count,
        "transport_valid": transport["verdict"] == "PASS",
        "qualification_per_model_call": (
            qualified_trajectories / persistent_model_calls if persistent_model_calls else 0.0
        ),
        "qualification_per_million_tokens": (
            qualified_trajectories / (persistent_tokens / 1_000_000) if persistent_tokens else 0.0
        ),
        "total_cost_usd": transport["total_cost_usd"],
        "context_growth": context_growth,
        "compactions_applied": compactions_applied,
        "resume_idempotent": True,
        "final_decision": final_decision,
        "transport": transport,
        "protocol_valid": transport["verdict"] == "PASS",
    }
    if transport["verdict"] != "PASS":
        summary["final_decision"] = "HOLD"
        summary["truthful_repair_qualified"] = False
        summary["none_repair_qualified"] = False
        summary["locked_qualification"] = False
        summary["evolution_status"] = "PROTOCOL_INVALID"
        summary["evolution_staged"] = False
    summary["verdict"] = {"ADMIT": "PASS", "REJECT": "FAIL", "HOLD": "HOLD"}[
        summary["final_decision"]
    ]
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def run_cross_family_panel(
    output_dir: Path,
    *,
    instruments: tuple[str, ...] = tuple(EXTERNAL_INSTRUMENTS),
    freeze_path: Path,
    seed_base: int = BINDING_SEED_BASE,
    compaction_byte_limit: int | None = DEFAULT_COMPACTION_BYTE_LIMIT,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    freeze_verification = verify_cross_family_method(freeze_path)
    if freeze_verification["verdict"] != "PASS":
        raise RuntimeError("cross-family method freeze did not verify before the binding panel")
    freeze = _read_json(freeze_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": PANEL_MANIFEST_SCHEMA,
        "method_sha256": freeze["method_sha256"],
        "instrument_ids": list(instruments),
        "sessions_per_family": 1,
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

    families: list[dict[str, Any]] = []
    for instrument_id in instruments:
        session_dir = output_dir / instrument_id / "session-000"
        summary_path = session_dir / "summary.json"
        if summary_path.is_file():
            families.append(_read_json(summary_path))
            continue
        try:
            summary = run_cross_family_session(
                instrument_id,
                session_dir,
                session_index=0,
                freeze_path=freeze_path,
                seed_base=seed_base,
                panel_manifest_sha256=panel_manifest_sha256,
                compaction_byte_limit=compaction_byte_limit,
            )
        except (ExternalRuntimeUnavailable, RuntimeError) as exc:
            session_dir.mkdir(parents=True, exist_ok=True)
            summary = {
                "schema_version": SESSION_SCHEMA,
                "instrument_id": instrument_id,
                "family": EXTERNAL_INSTRUMENTS[instrument_id].family,
                "session_index": 0,
                "panel_manifest_sha256": panel_manifest_sha256,
                "preflight_ok": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "final_decision": "HOLD",
                "verdict": "HOLD",
            }
            write_canonical_json(summary_path, summary)
        families.append(summary)

    decisions = [family.get("final_decision") for family in families]
    if any(decision == "REJECT" for decision in decisions):
        verdict = "FAIL"
    elif families and all(decision == "ADMIT" for decision in decisions):
        verdict = "PASS"
    else:
        verdict = "HOLD"
    result = {
        "schema_version": PANEL_SCHEMA,
        "panel_manifest_sha256": panel_manifest_sha256,
        "method_sha256": freeze["method_sha256"],
        "registered_instruments": list(instruments),
        "sessions_per_family": 1,
        "replacement_rule": (
            "none; a family that fails preflight is recorded as HOLD and never substituted"
        ),
        "promotion_authority": "deterministic-execution-and-physical-gates",
        "claim_boundary": CLAIM_BOUNDARY,
        "families": families,
        "verdict": verdict,
    }
    write_canonical_json(output_dir / "summary.json", result)
    return result


def freeze_cross_family_method(
    output_dir: Path,
    *,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    evidence_root = evidence_root or DEFAULT_EVIDENCE_ROOT
    evidence: dict[str, Any] = {}
    for instrument_id in EXTERNAL_INSTRUMENTS:
        preflight_path = evidence_root / "eligibility" / instrument_id / "preflight.json"
        metrology_path = evidence_root / "metrology" / instrument_id / "summary.json"
        preflight = _read_json(preflight_path)
        metrology = _read_json(metrology_path)
        if preflight.get("verdict") != "PASS":
            raise RuntimeError(f"eligibility preflight did not pass: {instrument_id}")
        if metrology.get("verdict") != "PASS":
            raise RuntimeError(f"verifier metrology did not pass: {instrument_id}")
        evidence[instrument_id] = {
            "preflight": {
                "path": str(preflight_path.relative_to(ROOT)),
                "sha256": source_sha256(preflight_path),
            },
            "metrology": {
                "path": str(metrology_path.relative_to(ROOT)),
                "sha256": source_sha256(metrology_path),
                "valid_false_reject_rate": metrology["valid"]["false_reject_rate"],
                "total_false_admits": metrology["total_false_admits"],
            },
        }
    registry_path = evidence_root / "eligibility" / "registry.json"
    inspection_path = evidence_root / "manual-inspection.md"
    provider_path = evidence_root / "provider-parity" / "provider-route.json"
    registry = _read_json(registry_path)
    if registry.get("selected_count") != 3 or registry.get("model_calls_during_screening") != 0:
        raise RuntimeError("eligibility registry does not describe a pre-model three-family panel")
    if not inspection_path.is_file():
        raise RuntimeError("manual evidence inspection is missing")
    provider = _read_json(provider_path)
    if (
        provider.get("verdict") != "PASS"
        or provider.get("provider_order") != ["DeepInfra", "GMICloud"]
        or provider.get("provider_allowlist") != ["DeepInfra", "GMICloud"]
        or not set(provider.get("providers", {})) <= EXPECTED_PROVIDERS
        or any(
            row.get("resolved_model") != EXPECTED_RESOLVED_MODEL
            for row in provider.get("providers", {}).values()
        )
    ):
        raise RuntimeError("binding provider parity did not pass")
    panel_evidence = {
        "eligibility_registry": {
            "path": str(registry_path.relative_to(ROOT)),
            "sha256": source_sha256(registry_path),
        },
        "manual_inspection": {
            "path": str(inspection_path.relative_to(ROOT)),
            "sha256": source_sha256(inspection_path),
        },
        "provider_parity": {
            "path": str(provider_path.relative_to(ROOT)),
            "sha256": source_sha256(provider_path),
        },
    }
    inputs = {relative: source_sha256(ROOT / relative) for relative in METHOD_INPUTS}
    external_simulators = {
        instrument_id: external_simulator_identity(instrument_id)
        for instrument_id in EXTERNAL_INSTRUMENTS
    }
    if any(row["verdict"] != "PASS" for row in external_simulators.values()):
        raise RuntimeError("an external simulator does not match its pinned revision")
    payload = {
        "schema_version": METHOD_FREEZE_SCHEMA,
        "status": "FROZEN_BEFORE_BINDING_PANEL",
        "claim_boundary": CLAIM_BOUNDARY,
        "qualification_evidence_root": str(evidence_root.relative_to(ROOT)),
        "qualification_evidence_note": (
            "eligibility and verifier metrology were completed before the binding panel"
        ),
        "selected_instruments": sorted(EXTERNAL_INSTRUMENTS),
        "inputs": inputs,
        "external_simulators": external_simulators,
        "evidence": evidence,
        "panel_evidence": panel_evidence,
    }
    payload["method_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_canonical_json(output_dir / "manifest.json", payload)
    return payload


def verify_cross_family_method(manifest_path: Path) -> dict[str, Any]:
    payload = _read_json(manifest_path)
    expected = payload.pop("method_sha256", None)
    observed = hashlib.sha256(canonical_json(payload)).hexdigest()
    input_matches = {
        relative: (ROOT / relative).is_file() and source_sha256(ROOT / relative) == expected_sha
        for relative, expected_sha in payload.get("inputs", {}).items()
    }
    external_matches = {}
    for instrument_id, expected_identity in payload.get("external_simulators", {}).items():
        try:
            external_matches[instrument_id] = (
                external_simulator_identity(instrument_id) == expected_identity
            )
        except Exception:
            external_matches[instrument_id] = False
    passed = (
        expected == observed
        and payload.get("status") == "FROZEN_BEFORE_BINDING_PANEL"
        and bool(input_matches)
        and all(input_matches.values())
        and bool(external_matches)
        and all(external_matches.values())
    )
    return {
        "schema_version": METHOD_VERIFICATION_SCHEMA,
        "method_sha256": expected,
        "digest_matches": expected == observed,
        "input_matches": input_matches,
        "external_simulator_matches": external_matches,
        "verdict": "PASS" if passed else "FAIL",
    }
