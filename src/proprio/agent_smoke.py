from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from proprio.adaptive_search import evaluate_debug_suite
from proprio.agent import (
    AgentModelConfig,
    append_verifier_record,
    arm_feedback_view,
    initial_agent_state,
    run_agent_cycle,
)
from proprio.artifacts import write_canonical_json
from proprio.generalization_instruments import (
    GENERALIZATION_INSTRUMENTS,
    evaluate_generalization_skill,
    external_simulator_identity,
    load_generalization_source,
)
from proprio.instrument_types import CandidatePackage
from proprio.policy import DSV4Client

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_PROVIDER_ROUTE = "DeepInfra,GMICloud"
SMOKE_SEED = 2_100_000
SMOKE_MODEL_CALL_BUDGET = 12
SMOKE_TOKEN_BUDGET = 400_000
SMOKE_VERIFIER_CYCLES = 2

_BINDING_ROOT = ROOT / "cassettes/generalization-v0.3-binding"
_ENGINEERING_ROOT = ROOT / "cassettes/generalization-v0.3-smoke-final"
_CAUSAL_EPISODE = Path("causal/truthful/episode-01.json")

DEFAULT_PARENT_EPISODES: dict[str, Path] = {
    "north-pipette-calibration": (
        _BINDING_ROOT / "north-pipette-calibration/session-000" / _CAUSAL_EPISODE
    ),
    "helao-gamry-cv": _BINDING_ROOT / "helao-gamry-cv/session-000" / _CAUSAL_EPISODE,
    "clslab-light-spectrometer": (
        _ENGINEERING_ROOT / "clslab-light-spectrometer/session-003" / _CAUSAL_EPISODE
    ),
}


def load_smoke_parent(instrument_id: str, parent_episode: Path | None = None) -> CandidatePackage:
    episode_path = parent_episode or DEFAULT_PARENT_EPISODES[instrument_id]
    episode = json.loads(Path(episode_path).read_text(encoding="utf-8"))
    return CandidatePackage.model_validate(episode["initial_candidate"])


def run_persistent_smoke(
    instrument_id: str,
    output_dir: Path,
    *,
    parent_episode: Path | None = None,
) -> dict[str, Any]:
    definition = GENERALIZATION_INSTRUMENTS[instrument_id]
    identity = external_simulator_identity(instrument_id)
    source, source_sha256 = load_generalization_source(instrument_id)
    episode_path = parent_episode or DEFAULT_PARENT_EPISODES[instrument_id]
    parent = load_smoke_parent(instrument_id, episode_path)
    client = DSV4Client()
    if "openrouter.ai" in client.base_url and client.provider != EXPECTED_PROVIDER_ROUTE:
        client.close()
        raise RuntimeError(
            f"smoke route must use {EXPECTED_PROVIDER_ROUTE}, observed {client.provider or 'unset'}"
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_config = AgentModelConfig(
        requested_model=client.model,
        provider_route=client.provider or "",
        temperature=0.0,
        top_p=1.0,
        seed=SMOKE_SEED,
    )
    state = initial_agent_state(
        instrument_id=instrument_id,
        feedback_arm="truthful",
        source=source,
        source_sha256=source_sha256,
        candidate=parent,
        conditions=definition.visible_conditions,
        run_config=run_config,
        model_call_budget=SMOKE_MODEL_CALL_BUDGET,
        token_budget=SMOKE_TOKEN_BUDGET,
        goal=(
            "Repair the current candidate so every registered visible condition admits. "
            "This engineering smoke exercises one persistent agent context across repeated "
            "verifier cycles; it is not binding evidence."
        ),
    )
    try:
        suite = evaluate_debug_suite(
            parent, definition.visible_conditions, evaluator=evaluate_generalization_skill
        )
        view, _ = arm_feedback_view(suite, state.feedback_arm)
        state = append_verifier_record(state, suite, exposed_view=view, checkpoint_dir=output_dir)
        for _ in range(SMOKE_VERIFIER_CYCLES):
            state = run_agent_cycle(
                state,
                client=client,
                evaluator=evaluate_generalization_skill,
                source=source,
                conditions=definition.visible_conditions,
                checkpoint_dir=output_dir,
            )
            if state.status != "ACTIVE":
                break
            suite = evaluate_debug_suite(
                state.current_candidate,
                definition.visible_conditions,
                evaluator=evaluate_generalization_skill,
            )
            view, _ = arm_feedback_view(suite, state.feedback_arm)
            state = append_verifier_record(
                state, suite, exposed_view=view, checkpoint_dir=output_dir
            )
    finally:
        client.close()
    roles = [message.get("role") for message in state.messages]
    assistant_indexes = [index for index, role in enumerate(roles) if role == "assistant"]
    tool_indexes = [index for index, role in enumerate(roles) if role == "tool"]
    verifier_indexes = [
        index
        for index, message in enumerate(state.messages)
        if isinstance(message.get("content"), str) and "verifier_evidence" in message["content"]
    ]
    evidence_indexes = tool_indexes + verifier_indexes
    persisted_history_resent = (
        state.consumed_model_calls >= 2
        and len(assistant_indexes) >= 2
        and bool(evidence_indexes)
        and min(evidence_indexes) < max(assistant_indexes)
    )
    providers: set[str] = set()
    resolved_models: set[str] = set()
    reasoning_present = 0
    chat_completions = 0
    for raw_path in sorted(output_dir.glob("raw-*.json")):
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        if payload.get("object") != "chat.completion":
            continue
        chat_completions += 1
        providers.add(str(payload.get("provider")))
        resolved_models.add(str(payload.get("model")))
        preserved = payload.get("preserved_assistant_message") or {}
        if any(
            preserved.get(key) for key in ("reasoning", "reasoning_details", "reasoning_content")
        ):
            reasoning_present += 1
    providers_allowlisted = providers <= set(EXPECTED_PROVIDER_ROUTE.split(","))
    verdict = (
        "PASS"
        if (
            persisted_history_resent
            and providers_allowlisted
            and chat_completions == state.consumed_model_calls
            and reasoning_present == chat_completions
            and state.status in {"ACTIVE", "CANDIDATE", "HOLD", "REJECT"}
        )
        else "FAIL"
    )
    summary: dict[str, Any] = {
        "schema_version": "proprio.agent_persistence_smoke.v0.4",
        "evidence_role": "engineering smoke; not binding evidence",
        "instrument_id": instrument_id,
        "external_simulator": identity,
        "parent_episode": (
            str(Path(episode_path).relative_to(ROOT))
            if Path(episode_path).is_relative_to(ROOT)
            else str(episode_path)
        ),
        "parent_candidate_sha256": hashlib.sha256(parent.skill_py.encode()).hexdigest(),
        "final_status": state.status,
        "consumed_model_calls": state.consumed_model_calls,
        "consumed_tokens": state.consumed_tokens,
        "assistant_turns": len(assistant_indexes),
        "tool_results": len(tool_indexes),
        "verifier_records": len(verifier_indexes),
        "repair_ledger": [entry.model_dump(mode="json") for entry in state.repair_ledger],
        "persisted_history_resent": persisted_history_resent,
        "providers": sorted(providers),
        "resolved_models": sorted(resolved_models),
        "chat_completions": chat_completions,
        "reasoning_present": reasoning_present,
        "providers_allowlisted": providers_allowlisted,
        "verdict": verdict,
    }
    write_canonical_json(output_dir / "smoke-summary.json", summary)
    return summary
