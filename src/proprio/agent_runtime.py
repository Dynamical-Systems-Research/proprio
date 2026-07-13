"""Model tool-use runtime for scientific-instrument skill drafting."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from proprio.catalog import parse_skill_markdown
from proprio.instrument_types import CandidatePackage
from proprio.policy import OpenAICompatibleClient
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


TRANSPORT_ATTEMPTS_PER_MODEL_TURN = 3
RETRYABLE_HTTP_STATUS = frozenset({408, 409, 429})


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
        "JSONDecodeError",
        "ReadError",
        "ReadTimeout",
    }
    return type(exc).__name__ in retryable_names, None


def _transport_retry_delay(status_code: int | None, attempt: int) -> float:
    """Back off enough for provider throttles without extending the scientific budget."""

    if status_code == 429:
        return float(30 * attempt)
    return float(2 * attempt)


def _response_has_message(response: Any) -> bool:
    choices = getattr(response, "choices", None)
    return bool(choices) and getattr(choices[0], "message", None) is not None


def _run_tool_loop(
    *,
    client: OpenAICompatibleClient,
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
                will_retry = retryable and transport_attempt < TRANSPORT_ATTEMPTS_PER_MODEL_TURN
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
                time.sleep(_transport_retry_delay(status_code, transport_attempt))
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
            # Keep reasoning-only responses replayable while requesting an explicit action.
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
        client: OpenAICompatibleClient | None = None,
        *,
        skill_system_prompt: str = SKILL_ENGINEER_SYSTEM_PROMPT,
        source_loader: Callable[[str], tuple[str, str]],
        evaluator: Callable[..., Any],
        families: Mapping[str, str],
        sampling_temperature: float = 0.0,
        sampling_top_p: float = 1.0,
        sampling_seed: int | None = None,
    ) -> None:
        self.client = client or OpenAICompatibleClient()
        self.skill_system_prompt = skill_system_prompt
        self.source_loader = source_loader
        self.evaluator = evaluator
        self.sampling_temperature = float(sampling_temperature)
        self.sampling_top_p = float(sampling_top_p)
        self.sampling_seed = sampling_seed
        self.families = families

    def draft(self, instrument_id: str, *, max_turns: int = 6) -> CandidatePackage:
        source, source_hash = self.source_loader(instrument_id)
        user_prompt = (
            f"Draft the initial reusable skill for instrument `{instrument_id}`. "
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
            raise RuntimeError(f"model did not submit a valid initial package for {instrument_id}")
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
