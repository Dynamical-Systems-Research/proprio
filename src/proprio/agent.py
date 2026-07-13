from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from proprio.agent_runtime import (
    TRANSPORT_ATTEMPTS_PER_MODEL_TURN,
    _assistant_payload,
    _is_retryable_transport_error,
    _json_content,
    _response_has_message,
    _transport_retry_delay,
    _validate_candidate_payload,
)
from proprio.artifacts import write_canonical_json
from proprio.instrument_types import CandidatePackage, FeedbackArm
from proprio.policy import OpenAICompatibleClient
from proprio.schema import canonical_json
from proprio.skill_agent import QUALIFICATION_REPAIR_TOOLS, QUALIFIED_SKILL_SYSTEM_PROMPT
from proprio.skill_search import (
    DebugCondition,
    DebugSuiteResult,
    Evaluator,
    evaluate_debug_suite,
)

AGENT_STATE_SCHEMA_VERSION = "proprio.agent_state.v0.4"


class RepairLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    candidate_sha256: str
    failed_checks: tuple[str, ...]
    diagnosis: str
    evidence_refs: tuple[str, ...]
    change_summary: str
    outcome: Literal["CANDIDATE", "HOLD", "REJECT", "MAX_TURNS", "DUPLICATE"]


class AgentModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    requested_model: str
    provider_route: str
    temperature: float
    top_p: float
    seed: int


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    schema_version: Literal["proprio.agent_state.v0.4"] = "proprio.agent_state.v0.4"
    instrument_id: str
    feedback_arm: str
    messages: tuple[dict[str, Any], ...]
    current_candidate: CandidatePackage
    latest_verifier_record: DebugSuiteResult | None
    repair_ledger: tuple[RepairLedgerEntry, ...]
    consumed_model_calls: int
    model_call_budget: int
    consumed_tokens: int
    token_budget: int
    run_config: AgentModelConfig
    source_sha256: str
    condition_hashes: dict[str, str]
    step_index: int
    status: Literal["ACTIVE", "CANDIDATE", "HOLD", "REJECT", "MAX_TURNS", "BUDGET_EXHAUSTED"]


PERSISTENT_AGENT_CONTRACT = """

Persistent agent context (authoritative operating contract):
- this instrument-operation work runs as one continuous persistent agent context, not a bounded
  episode; operate only through the controller surface declared by the current source bundle and
  never reach past it or invent an operation the source does not declare;
- before acting, inspect the instrument documentation, the current skill, the repair ledger of
  prior attempts, and fresh execution evidence from the verifier;
- treat verifier output as execution evidence to be reconciled, never as optional advice you may
  set aside;
- cite the exact exposed evidence references that justify each repair;
- never resubmit a candidate hash already present in the ledger, and never repeat a strategy that
  already failed, unless new execution evidence supports it;
- preserve the behavior supported by prior conditions that already succeeded;
- make the smallest evidence-grounded change likely to close the observed failure;
- rerun the simulator after every submitted repair and read its record before finishing;
- return HOLD when execution evidence is unavailable or insufficient for a safe edit;
- your own self-judgment is advisory evidence and is never an admission that the candidate
  qualifies;
- keep scientific interpretation out of the instrument-operation record.

This is one continuous persistent agent context: earlier assistant turns, tool results,
diagnoses, and rejected attempts remain in the message history and must be consulted before each
new action. There is no fixed repair recipe; diagnose and revise only from the execution evidence
present in this context.
"""

PERSISTENT_SYSTEM_PROMPT = QUALIFIED_SKILL_SYSTEM_PROMPT + PERSISTENT_AGENT_CONTRACT


def _progress(event: str, **fields: Any) -> None:
    details = " ".join(f"{name}={value}" for name, value in fields.items())
    suffix = f" {details}" if details else ""
    print(f"[proprio] {event}{suffix}", file=sys.stderr, flush=True)


def arm_feedback_view(
    suite: DebugSuiteResult, feedback_arm: str
) -> tuple[dict[str, Any], tuple[str, ...]]:
    if feedback_arm == FeedbackArm.TRUTHFUL.value:
        refs = tuple(ref for row in suite.conditions for ref in row.failure_refs)
        return suite.model_dump(mode="json"), refs
    if feedback_arm == FeedbackArm.NONE.value:
        ref = "feedback:withheld"
        return {
            "evidence_ref": ref,
            "status": "withheld",
            "message": "execution evidence is withheld in this comparison arm",
        }, (ref,)
    raise ValueError(f"unsupported feedback arm for persistent context: {feedback_arm}")


def _condition_hashes(conditions: Sequence[DebugCondition]) -> dict[str, str]:
    return {
        condition.condition_id: hashlib.sha256(
            canonical_json(condition.model_dump(mode="json"))
        ).hexdigest()
        for condition in conditions
    }


def initial_agent_state(
    *,
    instrument_id: str,
    feedback_arm: str,
    source: str,
    source_sha256: str,
    candidate: CandidatePackage,
    conditions: Sequence[DebugCondition],
    run_config: AgentModelConfig,
    model_call_budget: int,
    token_budget: int,
    goal: str,
) -> AgentState:
    user_prompt = (
        f"You maintain one continuous persistent agent context for the `{instrument_id}` "
        "instrument skill across every repair and evolution cycle in this run.\n\n"
        f"Goal:\n{goal}\n\n"
        "Instrument documentation and declared controller surface "
        f"(source bundle {source_sha256}):\n{source}\n\n"
        "Current candidate SKILL.md:\n"
        f"{candidate.skill_md}\n\n"
        "Current candidate skill.py:\n"
        f"{candidate.skill_py}\n\n"
        "Inspect the source, the current skill, the repair ledger, and fresh verifier evidence "
        "through the declared tools before acting. Submit at most one evidence-grounded repair "
        "per cycle and cite the exact exposed evidence references that justify it. The current "
        "candidate may already contain repairs from earlier cycles in this same context; finish "
        "with CANDIDATE only after a post-edit replay admits, and otherwise return an honest HOLD "
        "or REJECT."
    )
    messages: tuple[dict[str, Any], ...] = (
        {"role": "system", "content": PERSISTENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    )
    return AgentState(
        instrument_id=instrument_id,
        feedback_arm=feedback_arm,
        messages=messages,
        current_candidate=candidate,
        latest_verifier_record=None,
        repair_ledger=(),
        consumed_model_calls=0,
        model_call_budget=model_call_budget,
        consumed_tokens=0,
        token_budget=token_budget,
        run_config=run_config,
        source_sha256=source_sha256,
        condition_hashes=_condition_hashes(conditions),
        step_index=0,
        status="ACTIVE",
    )


def branch_agent_state(state: AgentState, *, feedback_arm: str) -> AgentState:
    if state.latest_verifier_record is not None:
        raise ValueError("cannot branch a context that already registered execution evidence")
    return state.model_copy(update={"feedback_arm": feedback_arm})


def _candidate_hash(candidate: CandidatePackage) -> str:
    return hashlib.sha256(candidate.skill_py.encode()).hexdigest()


def _failed_check_ids(suite: DebugSuiteResult) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for condition in suite.conditions:
        for gate in condition.gates:
            for check in gate.checks:
                if not check.passed and check.check_id not in seen:
                    seen.add(check.check_id)
                    ordered.append(check.check_id)
    return tuple(ordered)


def _exposed_refs(messages: Sequence[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            failure_refs = value.get("failure_refs")
            if isinstance(failure_refs, list):
                refs.update(str(item) for item in failure_refs)
            evidence_ref = value.get("evidence_ref")
            if isinstance(evidence_ref, str):
                refs.add(evidence_ref)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            try:
                walk(json.loads(content))
            except (json.JSONDecodeError, ValueError):
                continue
    return refs


def _pending_submission(messages: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict) and parsed.get("status") == "captured":
            if "candidate_sha256" in parsed and "diagnosis" in parsed:
                return parsed
    return None


def _ledger_message_digest(
    ledger: Sequence[RepairLedgerEntry], feedback_arm: str
) -> list[dict[str, Any]]:
    if feedback_arm == FeedbackArm.NONE.value:
        return [
            {"candidate_sha256": entry.candidate_sha256, "outcome": entry.outcome}
            for entry in ledger
        ]
    return [entry.model_dump(mode="json") for entry in ledger]


def append_verifier_record(
    state: AgentState,
    suite: DebugSuiteResult,
    *,
    exposed_view: dict[str, Any],
    checkpoint_dir: str | Path | None = None,
) -> AgentState:
    ledger = list(state.repair_ledger)
    pending = _pending_submission(state.messages)
    recorded = {
        entry.candidate_sha256 for entry in ledger if entry.outcome in {"CANDIDATE", "REJECT"}
    }
    current_hash = _candidate_hash(state.current_candidate)
    if (
        pending is not None
        and pending["candidate_sha256"] == current_hash
        and current_hash not in recorded
    ):
        admitted = suite.verdict == "ADMIT"
        ledger.append(
            RepairLedgerEntry(
                candidate_sha256=current_hash,
                failed_checks=() if admitted else _failed_check_ids(suite),
                diagnosis=str(pending["diagnosis"]),
                evidence_refs=tuple(str(ref) for ref in pending.get("evidence_refs", ())),
                change_summary=str(pending.get("change_summary", "")),
                outcome="CANDIDATE" if admitted else "REJECT",
            )
        )
    ledger_tuple = tuple(ledger)
    record = {
        "verifier_evidence": exposed_view,
        "repair_ledger": _ledger_message_digest(ledger_tuple, state.feedback_arm),
        "remaining_model_calls": state.model_call_budget - state.consumed_model_calls,
        "remaining_tokens": state.token_budget - state.consumed_tokens,
    }
    messages = (*state.messages, {"role": "user", "content": _json_content(record)})
    step_index = state.step_index + 1
    new_state = state.model_copy(
        update={
            "messages": messages,
            "latest_verifier_record": suite,
            "repair_ledger": ledger_tuple,
            "step_index": step_index,
        }
    )
    if checkpoint_dir is not None:
        _write_step(new_state, Path(checkpoint_dir))
    _progress(
        "verifier-record",
        instrument=state.instrument_id,
        step=step_index,
        verdict=suite.verdict,
        candidate=current_hash[:12],
    )
    return new_state


def _write_step(state: AgentState, checkpoint_dir: Path) -> None:
    write_canonical_json(checkpoint_dir / f"step-{state.step_index:04d}.json", state)


def _write_raw(checkpoint_dir: Path, payload: dict[str, Any]) -> None:
    index = len(list(checkpoint_dir.glob("raw-*.json")))
    write_canonical_json(checkpoint_dir / f"raw-{index:04d}.json", payload)


def _usage_total(response: Any) -> int:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump(mode="json")
    if isinstance(usage, dict):
        return int(usage.get("total_tokens") or 0)
    return int(getattr(usage, "total_tokens", 0) or 0)


def _complete_with_retry(
    client: OpenAICompatibleClient,
    request: dict[str, Any],
    checkpoint_dir: Path,
    model_turn: int,
) -> Any:
    create = getattr(client, "create_chat_completion", None)
    if create is None:
        create = client.client.chat.completions.create
    request_config = {
        "temperature": request["temperature"],
        "top_p": request["top_p"],
        "seed": request["seed"],
    }
    for attempt in range(1, TRANSPORT_ATTEMPTS_PER_MODEL_TURN + 1):
        _progress("provider-call", turn=model_turn + 1, attempt=attempt)
        try:
            candidate = create(**request)
        except Exception as exc:
            retryable, status_code = _is_retryable_transport_error(exc)
            will_retry = retryable and attempt < TRANSPORT_ATTEMPTS_PER_MODEL_TURN
            _write_raw(
                checkpoint_dir,
                {
                    "schema_version": "proprio.model_transport_error.v0.2",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "status_code": status_code,
                    "model_turn": model_turn,
                    "transport_attempt": attempt,
                    "will_retry": will_retry,
                    "request_config": request_config,
                },
            )
            if not will_retry:
                raise
            _progress(
                "provider-retry",
                turn=model_turn + 1,
                attempt=attempt,
                status=status_code or "transport-error",
            )
            time.sleep(_transport_retry_delay(status_code, attempt))
            continue
        if _response_has_message(candidate):
            return candidate
        will_retry = attempt < TRANSPORT_ATTEMPTS_PER_MODEL_TURN
        dumped = getattr(candidate, "model_dump", None)
        _write_raw(
            checkpoint_dir,
            {
                "schema_version": "proprio.model_transport_invalid_response.v0.2",
                "error_type": "missing-choice-or-message",
                "response": dumped(mode="json") if callable(dumped) else None,
                "model_turn": model_turn,
                "transport_attempt": attempt,
                "will_retry": will_retry,
                "request_config": request_config,
            },
        )
        if not will_retry:
            raise RuntimeError("model transport returned no choice message after three attempts")
        time.sleep(float(attempt))
    raise RuntimeError("model transport attempts ended without a response")


def run_agent_cycle(
    state: AgentState,
    *,
    client: OpenAICompatibleClient,
    evaluator: Evaluator,
    source: str,
    conditions: Sequence[DebugCondition],
    checkpoint_dir: str | Path,
    compaction_byte_limit: int | None = None,
) -> AgentState:
    if state.status != "ACTIVE":
        return state
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    messages = [dict(message) for message in state.messages]
    current = state.current_candidate
    ledger = list(state.repair_ledger)
    latest_verifier = state.latest_verifier_record
    consumed_model_calls = state.consumed_model_calls
    consumed_tokens = state.consumed_tokens
    step_index = state.step_index
    exposed_refs = _exposed_refs(messages)
    _progress(
        "agent-cycle",
        instrument=state.instrument_id,
        step=step_index,
        calls=f"{consumed_model_calls}/{state.model_call_budget}",
        tokens=f"{consumed_tokens}/{state.token_budget}",
    )

    def snapshot(status: str) -> AgentState:
        return AgentState(
            instrument_id=state.instrument_id,
            feedback_arm=state.feedback_arm,
            messages=tuple(messages),
            current_candidate=current,
            latest_verifier_record=latest_verifier,
            repair_ledger=tuple(ledger),
            consumed_model_calls=consumed_model_calls,
            model_call_budget=state.model_call_budget,
            consumed_tokens=consumed_tokens,
            token_budget=state.token_budget,
            run_config=state.run_config,
            source_sha256=state.source_sha256,
            condition_hashes=state.condition_hashes,
            step_index=step_index,
            status=status,  # type: ignore[arg-type]
        )

    def checkpoint(status: str) -> AgentState:
        nonlocal step_index
        step_index += 1
        recorded = snapshot(status)
        _write_step(recorded, checkpoint_dir)
        return recorded

    def handle(name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
        nonlocal current, latest_verifier
        if name == "read_source_bundle":
            return {"source_ref": state.source_sha256, "content": source}, False, "ACTIVE"
        if name == "read_current_skill":
            return {"skill_md": current.skill_md, "skill_py": current.skill_py}, False, "ACTIVE"
        if name == "run_debug_suite":
            suite = evaluate_debug_suite(current, conditions, evaluator=evaluator)
            latest_verifier = suite
            view, refs = arm_feedback_view(suite, state.feedback_arm)
            exposed_refs.update(refs)
            return view, False, "ACTIVE"
        if name == "submit_repair":
            if not exposed_refs:
                raise ValueError("debug evidence must be inspected before repair")
            skill_md, skill_py, self_judgment = _validate_candidate_payload(arguments)
            refs = tuple(str(ref) for ref in arguments["evidence_refs"])
            if not refs:
                raise ValueError("repair requires at least one debug evidence reference")
            unknown = sorted(set(refs) - exposed_refs)
            if unknown:
                raise ValueError(f"repair cited unexposed evidence references: {unknown}")
            diagnosis = str(arguments["diagnosis"])
            change_summary = str(arguments["expected_effect"])
            new_hash = hashlib.sha256(skill_py.encode()).hexdigest()
            known = {entry.candidate_sha256 for entry in ledger}
            if new_hash == _candidate_hash(current) or new_hash in known:
                ledger.append(
                    RepairLedgerEntry(
                        candidate_sha256=new_hash,
                        failed_checks=(),
                        diagnosis=diagnosis,
                        evidence_refs=refs,
                        change_summary=change_summary,
                        outcome="DUPLICATE",
                    )
                )
                return (
                    {
                        "status": "error",
                        "error": (
                            "duplicate candidate hash; submit a genuinely different repair "
                            "grounded in new evidence"
                        ),
                    },
                    False,
                    "ACTIVE",
                )
            current = current.model_copy(
                update={
                    "skill_md": skill_md,
                    "skill_py": skill_py,
                    "self_judgment": self_judgment,
                    "model": client.model,
                    "raw_response": {
                        "repair_submission": {
                            "diagnosis": diagnosis,
                            "evidence_refs": list(refs),
                            "expected_effect": change_summary,
                        }
                    },
                }
            )
            return (
                {
                    "status": "captured",
                    "candidate_sha256": new_hash,
                    "diagnosis": diagnosis,
                    "evidence_refs": list(refs),
                    "change_summary": change_summary,
                },
                True,
                "ACTIVE",
            )
        if name == "finish_candidate":
            requested = str(arguments["status"])
            if requested == "CANDIDATE":
                if (
                    latest_verifier is None
                    or latest_verifier.candidate_sha256 != _candidate_hash(current)
                    or latest_verifier.verdict != "ADMIT"
                ):
                    raise ValueError(
                        "candidate cannot finish without an admitting replay of the current "
                        "candidate"
                    )
            return {"status": "finished", "candidate_status": requested}, True, requested
        raise KeyError(name)

    while True:
        if consumed_model_calls >= state.model_call_budget or consumed_tokens >= state.token_budget:
            return checkpoint("BUDGET_EXHAUSTED")
        request_messages = messages
        if compaction_byte_limit is not None:
            request_messages = list(
                compact_messages(snapshot("ACTIVE"), byte_limit=compaction_byte_limit).messages
            )
        request: dict[str, Any] = {
            "model": client.model,
            "messages": request_messages,
            "tools": QUALIFICATION_REPAIR_TOOLS,
            "tool_choice": "auto",
            "temperature": state.run_config.temperature,
            "top_p": state.run_config.top_p,
            "max_tokens": 8192,
            "seed": state.run_config.seed,
        }
        response = _complete_with_retry(client, request, checkpoint_dir, consumed_model_calls)
        message = response.choices[0].message
        assistant = _assistant_payload(message)
        raw = response.model_dump(mode="json")
        raw["preserved_assistant_message"] = assistant
        raw["request_config"] = {
            "temperature": state.run_config.temperature,
            "top_p": state.run_config.top_p,
            "seed": state.run_config.seed,
        }
        consumed_model_calls += 1
        response_tokens = _usage_total(response)
        consumed_tokens += response_tokens
        _progress(
            "model-response",
            turn=consumed_model_calls,
            tokens=response_tokens,
            total_tokens=consumed_tokens,
        )
        calls = message.tool_calls or []
        if not calls and not message.content:
            assistant["content"] = "[reasoning-only response; no action emitted]"
            raw["transport_recovery"] = "reasoning-only-no-action"
        _write_raw(checkpoint_dir, raw)
        messages.append(assistant)
        if not calls:
            messages.append(
                {
                    "role": "user",
                    "content": "Use one of the available tools; do not answer in prose.",
                }
            )
            checkpoint("ACTIVE")
            continue
        for call in calls:
            name = call.function.name
            arguments: dict[str, Any] = {}
            terminal = False
            status = "ACTIVE"
            try:
                arguments = json.loads(call.function.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("tool arguments must be an object")
                result, terminal, status = handle(name, arguments)
            except Exception as exc:
                result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
                terminal = False
                status = "ACTIVE"
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": _json_content(result)}
            )
            _progress(
                "tool-result",
                tool=name,
                status=result.get("status", status),
                terminal=terminal,
            )
            if terminal:
                _progress("agent-finish", instrument=state.instrument_id, status=status)
                return checkpoint(status)
            checkpoint("ACTIVE")


def repeated_failed_strategy_count(state: AgentState) -> int:
    entries = [entry for entry in state.repair_ledger if entry.outcome != "DUPLICATE"]
    count = 0
    for index in range(1, len(entries)):
        if (
            entries[index].outcome == "REJECT"
            and entries[index].failed_checks == entries[index - 1].failed_checks
        ):
            count += 1
    return count


def _is_verifier_record(message: dict[str, Any]) -> bool:
    content = message.get("content")
    if not isinstance(content, str):
        return False
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(parsed, dict) and "verifier_evidence" in parsed


def compact_messages(state: AgentState, *, byte_limit: int) -> AgentState:
    messages = [dict(message) for message in state.messages]
    if len(canonical_json(messages)) <= byte_limit:
        return state
    ledger_hashes = {entry.candidate_sha256 for entry in state.repair_ledger}
    protected: set[int] = {0}
    if len(messages) > 1:
        protected.add(1)
    for index in range(max(0, len(messages) - 8), len(messages)):
        protected.add(index)
    for index in range(len(messages) - 1, -1, -1):
        if _is_verifier_record(messages[index]):
            protected.add(index)
            break
    for index, message in enumerate(messages):
        content = message.get("content")
        if isinstance(content, str) and any(digest in content for digest in ledger_hashes):
            protected.add(index)
    step_ref = f"step-{state.step_index:04d}.json"
    stub = _json_content({"compacted": True, "step_ref": step_ref})
    for index, message in enumerate(messages):
        if len(canonical_json(messages)) <= byte_limit:
            break
        if index in protected:
            continue
        if message.get("role") not in {"user", "tool"}:
            continue
        if message.get("content") == stub:
            continue
        replaced = dict(message)
        replaced["content"] = stub
        messages[index] = replaced
    return state.model_copy(update={"messages": tuple(messages)})


def resume_agent_state(checkpoint_dir: str | Path) -> AgentState | None:
    directory = Path(checkpoint_dir)
    files = sorted(directory.glob("step-*.json"), key=lambda path: int(path.stem.split("-")[1]))
    if not files:
        return None
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    if payload.get("schema_version") != AGENT_STATE_SCHEMA_VERSION:
        raise ValueError(f"unexpected checkpoint schema version: {payload.get('schema_version')}")
    return AgentState.model_validate(payload)
