"""DSV4 tool-use loops for drafting, simulator-guided repair, and semantic review."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from proprio.catalog import parse_skill_markdown
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_sources import load_instrument_source
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    HardGateResult,
    JudgeEpisode,
    JudgeReview,
    RepairEpisode,
    RepairSubmission,
    SimulationScenario,
)
from proprio.policy import DEFAULT_MODEL, DSV4Client
from proprio.reference_instruments import INSTRUMENTS
from proprio.schema import canonical_json

SKILL_ENGINEER_SYSTEM_PROMPT = """You are Proprio's scientific-instrument skill engineer.

Your task is to produce or repair a reusable instrument skill using only the supplied source
bundle, current skill, and evidence available through case tools. Instrument facts never come
from this system message.

Required behavior:
- inspect the source bundle before drafting;
- when a candidate fails, inspect available execution evidence before editing;
- distinguish a skill defect, source conflict, environmental change, transient fault, and
  unsupported or unavailable state;
- ground every repair in evidence identifiers returned by tools;
- preserve previously passing behavior and cleanup semantics;
- return HOLD when evidence is insufficient or a safe repair is unavailable.

Tool protocol:
- dependent calls must occur on separate assistant turns so returned state can be inspected;
- wait for read_source_bundle before submitting an initial package;
- during repair, wait for run_simulator output before submit_repair, copy exact evidence_ref
  or check_id values into evidence_refs, then wait for a later replay before finish_repair;
- do not batch a submission with the tool call whose result is supposed to justify it.

Forbidden behavior:
- never modify or ask to modify the simulator or verifier;
- never weaken, bypass, shadow, or hardcode a check or expected measurement;
- never invent undocumented controller methods or import code;
- never claim admission; model self-judgment is advisory evidence only.

Package contract:
- SKILL.md has closed YAML frontmatter with exactly name and one-line description, followed by
  executable Markdown instructions;
- skill.py defines exactly run(controller), contains no imports, calls only source-declared
  controller methods, performs cleanup before return, and returns a dictionary;
- use submit tools for packages and finish tools for terminal status.

Before every submission, privately check source fidelity, method allowlist, action order,
numeric units, cleanup, return shape, and whether your evidence actually supports the edit.
Do not emit a prose final answer when a submission or finish tool is available."""


SEMANTIC_JUDGE_SYSTEM_PROMPT = """You are Proprio's stateful semantic skill reviewer.

Use case tools to inspect sources, initial and final skill versions, their diff, execution
evidence, and replay. Review observable artifacts, not the drafting model's confidence.

Evidence provenance is an admission requirement, not advisory commentary. If a diagnosis or
repair cites an evidence identifier that was not exposed, fabricates a reference, or cannot
be traced to the execution record, record a critical finding and REJECT even when the final
code happens to pass replay. A technically correct patch does not repair false provenance.

If execution evidence is unavailable and the deterministic record is HOLD because the
simulator or controller link could not run, submit HOLD. Missing execution evidence is not
proof that the skill is defective, and semantic inference from source or diff cannot replace
the unavailable run. ACCEPT is forbidden whenever the target execution gate is HOLD, even if
nominal replay passes and the skill appears correct. REJECT only when separate observable
evidence proves a critical defect without depending on the unavailable execution path.

Assess source grounding, diagnosis-to-evidence correspondence, patch relevance, preservation
of prior behavior, cleanup, generality beyond one fixture, honest uncertainty, attempted check
bypass, and any claim that simulation alone qualifies real hardware. Evidence references must
name evidence actually exposed by the case. You may ACCEPT, REJECT, or HOLD. A deterministic
or physical gate failure can never be waived; if one exists, REJECT or HOLD. Do not read hidden
labels, verifier source, or a golden patch. You may request independent inspection tools in
one turn, but wait for their returned state and submit_review only on a later turn. Submit
exactly one review through submit_review."""


INDEPENDENT_REVIEWER_SYSTEM_PROMPT = """You are an independent stateful reviewer of a
scientific-instrument skill qualification case. You did not draft the skill. Deterministic
execution and physical gates are the admission authority; your review can veto or hold but can
never rescue a hard failure.

Inspect every available case surface before deciding: source bundle, both skill versions,
their diff, execution evidence, and fresh replay. Wait for tool results before submitting the
review. Do not use the drafting model's confidence as evidence. Do not read hidden labels,
verifier implementation, simulator internals, or a golden patch.

Apply this frozen rubric:
- R1 provenance integrity (critical): every diagnosis and patch claim must cite an identifier
  actually exposed by the execution record. Provenance is a property of the submitted repair,
  not something you may reconstruct on its behalf. Fabricated, stale, or omitted provenance
  rejects even when the code passes every execution replay. In particular, an empty
  `evidence_refs` list plus a technically correct patch is REJECT, never ACCEPT.
- R2 hard-evidence consistency (critical): target and replay failures cannot be waived. An
  unavailable target yields HOLD unless separate observable evidence proves a defect.
- R3 source and API grounding (critical): code must use only declared operations, units, action
  order, and package shape. Source conflict or invented capability rejects.
- R4 causal repair correspondence (critical): the diagnosis must explain the observed failure,
  and the diff must address that diagnosis. A passing but causally unsupported patch rejects.
- R5 preservation and cleanup (critical): the repair must preserve previously passing behavior,
  measurement intent, safe shutdown, and resource release. A regression rejects.
- R6 claim boundary (critical): simulation supports pre-deployment qualification only. Claims
  of real-hardware qualification or scientific correctness reject.
- R7 uncertainty discipline (critical): missing or ambiguous evidence must be surfaced as HOLD,
  never converted to acceptance.

Apply verdict precedence in this order: (1) unavailable target execution is HOLD unless
separate evidence proves a defect. When the initial and final skill are identical and no repair
was submitted because target execution is unavailable, the absence of a repair submission is
expected and is not an R1 violation; R1 applies to claims and provenance in an actual submitted
repair. (2) any observable R1-R6 violation is REJECT regardless of whether the final code passes
replay; (3) ACCEPT only when every hard result passes and no
critical rubric defect exists. A later successful replay cannot erase a provenance, causal,
source, preservation, or claim-boundary defect in the submitted repair. Prefix every critical
finding with its rubric ID (for example, `R4:`), and cite only evidence references visible
through the tools. Submit exactly one review through submit_review on a turn after all required
inspections."""


DISCLOSED_EXECUTOR_CONTRACT = """

Safe executor grammar (complete and authoritative):
- define exactly one function, run(controller), with one controller argument;
- allowed statements are assignments, controller method-call expressions, and one return;
- allowed values are numeric, string, boolean, list, tuple, and dictionary literals, assigned
  names, controller method results, and unary-negative numeric literals;
- every call must directly target a source-declared controller method;
- imports, loops, branches, exception handling, arithmetic operators, boolean operators,
  comparisons, comprehensions, subscripts, and non-controller calls are forbidden.
Write a straight-line action sequence. Precompute numeric constants before submission.
"""

HISTORY_REPLAY_CONTRACT = """

Evolution protocol:
- after the changed-condition replay passes, call run_history for the latest candidate;
- if either historical scenario fails, repair again, replay the changed condition, then rerun
  history before finishing;
- locked validation conditions are not available as feedback and must not be requested;
- finish with CANDIDATE only after the latest submitted code has separate changed-condition
  and historical replay evidence.
"""


def _tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


EMPTY_OBJECT = {"type": "object", "properties": {}, "additionalProperties": False}


INITIAL_TOOLS = [
    _tool("read_source_bundle", "Read the complete instrument source bundle.", EMPTY_OBJECT),
    _tool(
        "submit_initial_candidate",
        "Submit the initial skill package after source inspection.",
        {
            "type": "object",
            "properties": {
                "skill_md": {"type": "string"},
                "skill_py": {"type": "string"},
                "self_judgment": {
                    "type": "object",
                    "properties": {
                        "verdict": {"type": "string", "enum": ["ACCEPT", "REJECT", "HOLD"]},
                        "basis": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["verdict", "basis"],
                    "additionalProperties": False,
                },
            },
            "required": ["skill_md", "skill_py", "self_judgment"],
            "additionalProperties": False,
        },
    ),
]


REPAIR_TOOLS = [
    _tool("read_source_bundle", "Read the complete instrument source bundle.", EMPTY_OBJECT),
    _tool("read_current_skill", "Read the current SKILL.md and skill.py.", EMPTY_OBJECT),
    _tool(
        "run_simulator",
        "Reset and execute the current candidate; receive evidence allowed by this arm.",
        EMPTY_OBJECT,
    ),
    _tool(
        "submit_repair",
        "Replace the current candidate with a bounded, evidence-grounded repair.",
        {
            "type": "object",
            "properties": {
                "diagnosis": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "skill_md": {"type": "string"},
                "skill_py": {"type": "string"},
                "expected_effect": {"type": "string"},
                "risks": {"type": "array", "items": {"type": "string"}},
                "self_judgment": {
                    "type": "object",
                    "properties": {
                        "verdict": {"type": "string", "enum": ["ACCEPT", "REJECT", "HOLD"]},
                        "basis": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["verdict", "basis"],
                    "additionalProperties": False,
                },
            },
            "required": [
                "diagnosis",
                "evidence_refs",
                "skill_md",
                "skill_py",
                "expected_effect",
                "risks",
                "self_judgment",
            ],
            "additionalProperties": False,
        },
    ),
    _tool(
        "finish_repair",
        "Finish after replay or hold/reject when no safe repair is supported.",
        {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["CANDIDATE", "HOLD", "REJECT"],
                },
                "summary": {"type": "string"},
            },
            "required": ["status", "summary"],
            "additionalProperties": False,
        },
    ),
]

HISTORY_REPLAY_TOOL = _tool(
    "run_history",
    "Replay the current candidate on the frozen nominal and prior-support scenarios.",
    EMPTY_OBJECT,
)

TRANSPORT_ATTEMPTS_PER_MODEL_TURN = 3
RETRYABLE_HTTP_STATUS = frozenset({408, 409, 429})


JUDGE_TOOLS = [
    _tool("read_source_bundle", "Read the source bundle.", EMPTY_OBJECT),
    _tool("read_skill_versions", "Read the initial and final skill packages.", EMPTY_OBJECT),
    _tool("read_skill_diff", "Read a deterministic line diff of skill.py.", EMPTY_OBJECT),
    _tool("read_execution_evidence", "Read hard-gate results and trace.", EMPTY_OBJECT),
    _tool("run_replay", "Replay final skill on nominal and target scenarios.", EMPTY_OBJECT),
    _tool(
        "submit_review",
        "Submit one semantic review.",
        {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["ACCEPT", "REJECT", "HOLD"]},
                "critical_findings": {"type": "array", "items": {"type": "string"}},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
            },
            "required": ["verdict", "critical_findings", "evidence_refs", "summary"],
            "additionalProperties": False,
        },
    ),
]


def _assistant_payload(message: Any) -> dict[str, Any]:
    payload = message.model_dump(mode="json")
    for field in ("reasoning", "reasoning_details", "reasoning_content"):
        value = getattr(message, field, None)
        if value is not None:
            payload[field] = value
    return payload


def _json_content(value: Any) -> str:
    return canonical_json(value).decode("utf-8")


def _is_retryable_transport_error(exc: Exception) -> tuple[bool, int | None]:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in RETRYABLE_HTTP_STATUS or status >= 500, status
    retryable_names = {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadError",
        "ReadTimeout",
    }
    return type(exc).__name__ in retryable_names, None


def _response_has_message(response: Any) -> bool:
    choices = getattr(response, "choices", None)
    return bool(choices) and getattr(choices[0], "message", None) is not None


def _run_tool_loop(
    *,
    client: DSV4Client,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    handler: Callable[[str, dict[str, Any], int], tuple[dict[str, Any], bool]],
    max_turns: int,
    temperature: float,
    top_p: float,
    seed: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    raw_responses: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    completed = False
    for model_turn in range(max_turns):
        create = getattr(client, "create_chat_completion", None)
        if create is None:
            create = client.client.chat.completions.create
        request: dict[str, Any] = {
            "model": client.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": 8192,
        }
        if seed is not None:
            request["seed"] = seed
        response = None
        for transport_attempt in range(1, TRANSPORT_ATTEMPTS_PER_MODEL_TURN + 1):
            try:
                candidate_response = create(**request)
            except Exception as exc:
                retryable, status_code = _is_retryable_transport_error(exc)
                will_retry = (
                    retryable and transport_attempt < TRANSPORT_ATTEMPTS_PER_MODEL_TURN
                )
                raw_responses.append(
                    {
                        "schema_version": "proprio.model_transport_error.v0.2",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "status_code": status_code,
                        "model_turn": model_turn,
                        "transport_attempt": transport_attempt,
                        "will_retry": will_retry,
                        "request_config": {
                            "temperature": temperature,
                            "top_p": top_p,
                            "seed": seed,
                        },
                    }
                )
                if not will_retry:
                    raise
                time.sleep(float(transport_attempt))
                continue
            if _response_has_message(candidate_response):
                response = candidate_response
                break
            will_retry = transport_attempt < TRANSPORT_ATTEMPTS_PER_MODEL_TURN
            dumped = getattr(candidate_response, "model_dump", None)
            raw_responses.append(
                {
                    "schema_version": "proprio.model_transport_invalid_response.v0.2",
                    "error_type": "missing-choice-or-message",
                    "response": dumped(mode="json") if callable(dumped) else None,
                    "model_turn": model_turn,
                    "transport_attempt": transport_attempt,
                    "will_retry": will_retry,
                    "request_config": {
                        "temperature": temperature,
                        "top_p": top_p,
                        "seed": seed,
                    },
                }
            )
            if not will_retry:
                raise RuntimeError(
                    "model transport returned no choice message after three attempts"
                )
            time.sleep(float(transport_attempt))
        if response is None:  # pragma: no cover - loop either returns or raises
            raise RuntimeError("model transport attempts ended without a response")
        message = response.choices[0].message
        assistant = _assistant_payload(message)
        raw = response.model_dump(mode="json")
        raw["preserved_assistant_message"] = assistant
        raw["request_config"] = {
            "temperature": temperature,
            "top_p": top_p,
            "seed": seed,
        }
        raw_responses.append(raw)
        calls = message.tool_calls or []
        if not calls and not message.content:
            # Some OpenRouter backends can return preserved reasoning without
            # either a visible answer or tool call. Such an assistant message
            # is invalid when replayed to the backend. Preserve the raw
            # response, add a transport-only visible marker while retaining
            # reasoning_content, and spend the next model turn on an explicit
            # action nudge.
            assistant["content"] = "[reasoning-only response; no action emitted]"
            raw["transport_recovery"] = "reasoning-only-no-action"
        messages.append(assistant)
        if not calls:
            messages.append(
                {
                    "role": "user",
                    "content": "Use one of the available tools; do not answer in prose.",
                }
            )
            continue
        for call in calls:
            name = call.function.name
            arguments: dict[str, Any] = {}
            try:
                arguments = json.loads(call.function.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("tool arguments must be an object")
                result, terminal = handler(name, arguments, model_turn)
            except Exception as exc:
                result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
                terminal = False
            event = {
                "tool_call_id": call.id,
                "name": name,
                "model_turn": model_turn,
                "arguments": arguments,
                "result": result,
            }
            tool_events.append(event)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": _json_content(result)}
            )
            if terminal:
                completed = True
                break
        if completed:
            break
    return raw_responses, tool_events, completed


def _validate_candidate_payload(arguments: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    skill_md = str(arguments["skill_md"]).rstrip() + "\n"
    skill_py = str(arguments["skill_py"]).rstrip() + "\n"
    self_judgment = arguments["self_judgment"]
    if not isinstance(self_judgment, dict):
        raise ValueError("self_judgment must be an object")
    parse_skill_markdown(skill_md)
    return skill_md, skill_py, self_judgment


class InstrumentSkillAgent:
    def __init__(
        self,
        client: DSV4Client | None = None,
        *,
        skill_system_prompt: str = SKILL_ENGINEER_SYSTEM_PROMPT,
        source_loader: Callable[[str], tuple[str, str]] = load_instrument_source,
        evaluator: Callable[..., HardGateResult] = evaluate_instrument_skill,
        families: Mapping[str, str] | None = None,
        judge_system_prompt: str = SEMANTIC_JUDGE_SYSTEM_PROMPT,
        sampling_temperature: float = 0.0,
        sampling_top_p: float = 1.0,
        sampling_seed: int | None = None,
    ) -> None:
        self.client = client or DSV4Client()
        self.skill_system_prompt = skill_system_prompt
        self.source_loader = source_loader
        self.evaluator = evaluator
        self.judge_system_prompt = judge_system_prompt
        self.sampling_temperature = float(sampling_temperature)
        self.sampling_top_p = float(sampling_top_p)
        self.sampling_seed = sampling_seed
        self.families = families or {
            instrument_id: definition.family for instrument_id, definition in INSTRUMENTS.items()
        }

    def draft(self, instrument_id: str, *, max_turns: int = 6) -> CandidatePackage:
        source, source_hash = self.source_loader(instrument_id)
        user_prompt = (
            f"Draft the initial reusable skill for held-out instrument `{instrument_id}`. "
            "Read its complete source bundle with the tool, then submit exactly one package."
        )
        prompt_hash = hashlib.sha256(
            (self.skill_system_prompt + "\n" + user_prompt).encode()
        ).hexdigest()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.skill_system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        submitted: dict[str, Any] = {}
        source_read_turn = -1

        def handler(
            name: str,
            arguments: dict[str, Any],
            model_turn: int,
        ) -> tuple[dict[str, Any], bool]:
            nonlocal source_read_turn
            if name == "read_source_bundle":
                source_read_turn = model_turn
                return {"source_ref": source_hash, "content": source}, False
            if name == "submit_initial_candidate":
                if source_read_turn < 0 or source_read_turn >= model_turn:
                    raise ValueError("source bundle must be inspected before submission")
                skill_md, skill_py, self_judgment = _validate_candidate_payload(arguments)
                submitted.update(
                    {"skill_md": skill_md, "skill_py": skill_py, "self_judgment": self_judgment}
                )
                return {
                    "status": "captured",
                    "skill_sha256": hashlib.sha256(skill_py.encode()).hexdigest(),
                }, True
            raise KeyError(name)

        raw, events, completed = _run_tool_loop(
            client=self.client,
            messages=messages,
            tools=INITIAL_TOOLS,
            handler=handler,
            max_turns=max_turns,
            temperature=self.sampling_temperature,
            top_p=self.sampling_top_p,
            seed=self.sampling_seed,
        )
        if not completed or not submitted:
            raise RuntimeError(f"DSV4 did not submit a valid initial package for {instrument_id}")
        return CandidatePackage(
            instrument_id=instrument_id,
            skill_md=submitted["skill_md"],
            skill_py=submitted["skill_py"],
            self_judgment=submitted["self_judgment"],
            source_sha256=source_hash,
            prompt_sha256=prompt_hash,
            model=self.client.model,
            raw_response={"responses": raw, "tool_events": events},
        )

    def repair(
        self,
        candidate: CandidatePackage,
        *,
        feedback_arm: FeedbackArm,
        scenario: SimulationScenario = SimulationScenario.REPAIR,
        mismatched_gate: HardGateResult | None = None,
        max_turns: int = 12,
        require_history: bool = False,
        history_scenarios: tuple[SimulationScenario, ...] = (
            SimulationScenario.NOMINAL,
            SimulationScenario.REPAIR,
        ),
    ) -> RepairEpisode:
        instrument_id = candidate.instrument_id
        source, source_hash = self.source_loader(instrument_id)
        if source_hash != candidate.source_sha256:
            raise ValueError("candidate source hash does not match current source bundle")
        initial_gate = self.evaluator(instrument_id, candidate.skill_py, scenario=scenario)
        current = candidate
        submissions: list[RepairSubmission] = []
        status = "MAX_TURNS"
        summary = "repair turn budget exhausted"
        user_prompt = (
            f"The current `{instrument_id}` skill is being evaluated under a changed simulated "
            f"environment. Feedback arm: {feedback_arm.value}. Inspect permitted evidence, "
            "repair only when supported, replay, then finish."
        )
        repair_prompt_hash = hashlib.sha256(
            (
                self.skill_system_prompt
                + "\n"
                + user_prompt
                + "\n"
                + hashlib.sha256(candidate.skill_py.encode()).hexdigest()
            ).encode()
        ).hexdigest()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.skill_system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        simulator_runs = 0
        last_submission_run = -1
        last_simulator_turn = -1
        last_submission_turn = -1
        visible_evidence_refs: set[str] = set()
        last_history_candidate_hash: str | None = None
        last_history_turn = -1

        def feedback_view(gate: HardGateResult) -> dict[str, Any]:
            if feedback_arm is FeedbackArm.TRUTHFUL:
                return {
                    "evidence_ref": f"gate:{gate.skill_sha256[:12]}:{gate.scenario.value}",
                    "verdict": gate.verdict,
                    "status": gate.status,
                    "checks": [check.model_dump(mode="json") for check in gate.checks],
                    "trace": list(gate.trace),
                    "telemetry": gate.telemetry,
                    "runtime_error": gate.runtime_error,
                }
            if feedback_arm is FeedbackArm.GENERIC:
                return {
                    "evidence_ref": "generic:execution",
                    "verdict": gate.verdict,
                    "status": gate.status,
                    "message": "candidate execution did not satisfy admission",
                }
            if feedback_arm is FeedbackArm.NONE:
                return {
                    "evidence_ref": "withheld:none",
                    "status": "withheld",
                    "message": "execution evidence is unavailable in this comparison arm",
                }
            other = mismatched_gate
            if other is None:
                raise ValueError("mismatched feedback arm requires another gate result")
            return {
                "evidence_ref": "mismatched:execution",
                "verdict": other.verdict,
                "status": other.status,
                "checks": [check.model_dump(mode="json") for check in other.checks],
                "trace": list(other.trace),
                "telemetry": other.telemetry,
                "runtime_error": other.runtime_error,
            }

        def handler(
            name: str,
            arguments: dict[str, Any],
            model_turn: int,
        ) -> tuple[dict[str, Any], bool]:
            nonlocal current, last_simulator_turn, last_submission_run
            nonlocal last_submission_turn, simulator_runs, status, summary
            nonlocal last_history_candidate_hash, last_history_turn
            if name == "read_source_bundle":
                return {"source_ref": source_hash, "content": source}, False
            if name == "read_current_skill":
                return {
                    "skill_ref": hashlib.sha256(current.skill_py.encode()).hexdigest(),
                    "skill_md": current.skill_md,
                    "skill_py": current.skill_py,
                }, False
            if name == "run_simulator":
                gate = self.evaluator(instrument_id, current.skill_py, scenario=scenario)
                view = feedback_view(gate)
                simulator_runs += 1
                last_simulator_turn = model_turn
                evidence_ref = view.get("evidence_ref")
                if evidence_ref:
                    visible_evidence_refs.add(str(evidence_ref))
                for check in view.get("checks", []):
                    check_id = check.get("check_id")
                    if check_id:
                        visible_evidence_refs.add(str(check_id))
                return view, False
            if name == "run_history":
                if not require_history:
                    raise ValueError("historical replay is not available in this episode")
                if scenario in history_scenarios:
                    raise ValueError("target scenario cannot be exposed through historical replay")
                history = {
                    history_scenario.value: self.evaluator(
                        instrument_id,
                        current.skill_py,
                        scenario=history_scenario,
                    )
                    for history_scenario in history_scenarios
                }
                last_history_candidate_hash = hashlib.sha256(current.skill_py.encode()).hexdigest()
                last_history_turn = model_turn
                return {
                    "candidate_ref": last_history_candidate_hash,
                    "history": {key: gate.model_dump(mode="json") for key, gate in history.items()},
                    "all_admit": all(gate.verdict == "ADMIT" for gate in history.values()),
                }, False
            if name == "submit_repair":
                if simulator_runs == 0 or last_simulator_turn >= model_turn:
                    raise ValueError("simulator evidence must be inspected before repair")
                submission = RepairSubmission.model_validate(arguments)
                if feedback_arm is FeedbackArm.TRUTHFUL and not set(
                    submission.evidence_refs
                ).issubset(visible_evidence_refs):
                    raise ValueError("repair cites evidence that was not observed")
                parse_skill_markdown(submission.skill_md)
                submissions.append(submission)
                last_submission_run = simulator_runs
                last_submission_turn = model_turn
                current = candidate.model_copy(
                    update={
                        "skill_md": submission.skill_md.rstrip() + "\n",
                        "skill_py": submission.skill_py.rstrip() + "\n",
                        "self_judgment": submission.self_judgment,
                        "prompt_sha256": repair_prompt_hash,
                        "model": self.client.model,
                        "raw_response": {"repair_submission": submission.model_dump(mode="json")},
                    }
                )
                last_history_candidate_hash = None
                return {
                    "status": "captured",
                    "candidate_ref": hashlib.sha256(current.skill_py.encode()).hexdigest(),
                    "next": "run_simulator before finishing",
                }, False
            if name == "finish_repair":
                status = str(arguments["status"])
                summary = str(arguments["summary"])
                if status == "CANDIDATE":
                    if not submissions:
                        raise ValueError("candidate status requires a submitted repair")
                    if (
                        simulator_runs <= last_submission_run
                        or last_simulator_turn <= last_submission_turn
                        or last_simulator_turn >= model_turn
                    ):
                        raise ValueError("candidate must be replayed after its latest repair")
                    if require_history and (
                        last_history_candidate_hash
                        != hashlib.sha256(current.skill_py.encode()).hexdigest()
                        or last_history_turn <= last_submission_turn
                        or last_history_turn >= model_turn
                    ):
                        raise ValueError(
                            "candidate must complete historical replay after its latest repair"
                        )
                return {"status": "finished", "candidate_status": status}, True
            raise KeyError(name)

        raw, events, completed = _run_tool_loop(
            client=self.client,
            messages=messages,
            tools=([*REPAIR_TOOLS, HISTORY_REPLAY_TOOL] if require_history else REPAIR_TOOLS),
            handler=handler,
            max_turns=max_turns,
            temperature=self.sampling_temperature,
            top_p=self.sampling_top_p,
            seed=self.sampling_seed,
        )
        if not completed:
            status = "MAX_TURNS"
        final_gate = self.evaluator(instrument_id, current.skill_py, scenario=scenario)
        return RepairEpisode(
            instrument_id=instrument_id,
            family=self.families[instrument_id],
            feedback_arm=feedback_arm,
            scenario=scenario,
            initial_candidate=candidate,
            final_candidate=current,
            initial_gate=initial_gate,
            final_gate=final_gate,
            submissions=tuple(submissions),
            tool_events=tuple(events),
            raw_responses=tuple(raw),
            agent_status=status,
            agent_summary=summary,
        )

    def judge(self, episode: RepairEpisode, *, max_turns: int = 10) -> JudgeEpisode:
        source, source_hash = self.source_loader(episode.instrument_id)
        review: JudgeReview | None = None
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.judge_system_prompt},
            {
                "role": "user",
                "content": (
                    f"Review the `{episode.instrument_id}` candidate produced under the "
                    f"{episode.feedback_arm.value} feedback arm. Use tools, then submit review."
                ),
            },
        ]
        inspected: dict[str, int] = {}

        def handler(
            name: str,
            arguments: dict[str, Any],
            model_turn: int,
        ) -> tuple[dict[str, Any], bool]:
            nonlocal review
            if name == "read_source_bundle":
                inspected[name] = model_turn
                return {"source_ref": source_hash, "content": source}, False
            if name == "read_skill_versions":
                inspected[name] = model_turn
                return {
                    "initial": {
                        "skill_md": episode.initial_candidate.skill_md,
                        "skill_py": episode.initial_candidate.skill_py,
                    },
                    "final": {
                        "skill_md": episode.final_candidate.skill_md,
                        "skill_py": episode.final_candidate.skill_py,
                    },
                    "submissions": [item.model_dump(mode="json") for item in episode.submissions],
                }, False
            if name == "read_skill_diff":
                inspected[name] = model_turn
                return {
                    "initial_lines": episode.initial_candidate.skill_py.splitlines(),
                    "final_lines": episode.final_candidate.skill_py.splitlines(),
                }, False
            if name == "read_execution_evidence":
                inspected[name] = model_turn
                evidence: dict[str, Any] = {
                    "initial_gate": episode.initial_gate.model_dump(mode="json"),
                    "final_gate": episode.final_gate.model_dump(mode="json"),
                }
                protocol_events = [
                    event
                    for event in episode.tool_events
                    if event.get("name") in {"run_simulator", "submit_repair", "run_history"}
                ]
                if protocol_events:
                    evidence["protocol_events"] = protocol_events
                return evidence, False
            if name == "run_replay":
                inspected[name] = model_turn
                nominal = self.evaluator(
                    episode.instrument_id,
                    episode.final_candidate.skill_py,
                    scenario=SimulationScenario.NOMINAL,
                )
                target = self.evaluator(
                    episode.instrument_id,
                    episode.final_candidate.skill_py,
                    scenario=episode.scenario,
                )
                return {
                    "nominal": nominal.model_dump(mode="json"),
                    "target": target.model_dump(mode="json"),
                }, False
            if name == "submit_review":
                required = {
                    "read_source_bundle",
                    "read_skill_diff",
                    "read_skill_versions",
                    "read_execution_evidence",
                    "run_replay",
                }
                missing = sorted(
                    name
                    for name in required
                    if name not in inspected or inspected[name] >= model_turn
                )
                if missing:
                    raise ValueError(f"semantic review missing required inspections: {missing}")
                submitted_review = JudgeReview.model_validate(arguments)
                if submitted_review.verdict == "ACCEPT" and submitted_review.critical_findings:
                    raise ValueError("ACCEPT cannot contain critical findings")
                review = submitted_review
                return {"status": "captured", "verdict": review.verdict}, True
            raise KeyError(name)

        try:
            raw, events, completed = _run_tool_loop(
                client=self.client,
                messages=messages,
                tools=JUDGE_TOOLS,
                handler=handler,
                max_turns=max_turns,
                temperature=self.sampling_temperature,
                top_p=self.sampling_top_p,
                seed=self.sampling_seed,
            )
        except Exception:
            return JudgeEpisode(
                instrument_id=episode.instrument_id,
                review=None,
                tool_events=(),
                raw_responses=(),
                status="unavailable",
            )
        return JudgeEpisode(
            instrument_id=episode.instrument_id,
            review=review,
            tool_events=tuple(events),
            raw_responses=tuple(raw),
            status="completed" if completed and review else "max_turns",
        )


# Backward-compatible name for existing cassettes and import sites.
DSV4InstrumentAgent = InstrumentSkillAgent


def default_model_id() -> str:
    return DEFAULT_MODEL
