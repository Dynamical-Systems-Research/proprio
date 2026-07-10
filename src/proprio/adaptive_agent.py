"""DSV4 interaction loop for evidence-grounded adaptive skill repair."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from proprio.adaptive_search import (
    DebugCondition,
    DebugSuiteResult,
    Evaluator,
    RepairOutcome,
    evaluate_debug_suite,
)
from proprio.instrument_agent import (
    EMPTY_OBJECT,
    SKILL_ENGINEER_SYSTEM_PROMPT,
    InstrumentSkillAgent,
    _run_tool_loop,
    _tool,
    _validate_candidate_payload,
)
from proprio.instrument_sources import load_instrument_source
from proprio.instrument_types import CandidatePackage, FeedbackArm, RepairSubmission
from proprio.policy import DSV4Client

ADAPTIVE_EXECUTOR_CONTRACT = """

Bounded adaptive executor contract (complete and authoritative):
- define exactly one function, run(controller), with one controller argument and a dictionary
  return value;
- allowed control flow is `if` plus `for ... in range(...)` with literal integer bounds and at
  most 16 iterations; use branches only on values returned by source-declared controller calls;
- assignments, comparisons, boolean expressions, dictionary indexing, and numeric +, -, *, /
  arithmetic are allowed; every controller call must target a source-declared method;
- the complete procedure has a static and runtime limit of 96 controller calls, nesting depth
  at most four, and source length at most 16,384 bytes;
- imports, while loops, exception handling, recursion, comprehensions, arbitrary built-ins,
  object construction, direct simulator-state reads, and calls outside the controller are
  forbidden;
- do not catch or convert controller failures; the runtime must expose them honestly;
- noisy measurements must use the source-declared repeated-measurement operation and branch on
  its returned uncertainty summary; the skill cannot set verifier thresholds or claim its own
  validity;
- do not invent or tune proxy thresholds from public diagnostics; preserve every raw measurement
  used by the procedure and keep every repair inside the source-declared acquisition budget;
- always execute source-required cleanup on every normal return path. If evidence remains
  ambiguous at the acquisition budget, finish the agent episode as HOLD instead of fabricating
  a passing procedure.

Source precedence: (1) the current source bundle and declared units, (2) returned controller
observations, (3) immutable simulator and physical-check records, (4) the existing candidate.
If these conflict or do not support a safe edit, HOLD.
"""

ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT = SKILL_ENGINEER_SYSTEM_PROMPT + ADAPTIVE_EXECUTOR_CONTRACT


class AdaptiveRepairEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proprio.adaptive_repair.v0.2"] = "proprio.adaptive_repair.v0.2"
    instrument_id: str
    feedback_arm: FeedbackArm
    initial_candidate: CandidatePackage
    final_candidate: CandidatePackage
    initial_suite: DebugSuiteResult
    final_suite: DebugSuiteResult
    submission: RepairSubmission | None
    tool_events: tuple[dict[str, Any], ...]
    raw_responses: tuple[dict[str, Any], ...]
    agent_status: Literal["CANDIDATE", "HOLD", "REJECT", "MAX_TURNS"]
    agent_summary: str


DEBUG_REPAIR_TOOLS = [
    _tool("read_source_bundle", "Read the complete instrument source bundle.", EMPTY_OBJECT),
    _tool("read_current_skill", "Read the current SKILL.md and skill.py.", EMPTY_OBJECT),
    _tool(
        "run_debug_suite",
        "Reset and run the current candidate over every visible debug condition and repeat.",
        EMPTY_OBJECT,
    ),
    _tool(
        "submit_repair",
        "Submit one bounded repair grounded in exact debug evidence references.",
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
        "finish_candidate",
        "Finish only after post-edit suite replay, or return an honest hold or rejection.",
        {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["CANDIDATE", "HOLD", "REJECT"]},
                "summary": {"type": "string"},
            },
            "required": ["status", "summary"],
            "additionalProperties": False,
        },
    ),
]


class AdaptiveInstrumentAgent(InstrumentSkillAgent):
    def __init__(
        self,
        client: DSV4Client | None = None,
        *,
        source_loader: Callable[[str], tuple[str, str]] = load_instrument_source,
        evaluator: Evaluator,
        families: Mapping[str, str],
        sampling_temperature: float = 0.0,
        sampling_top_p: float = 1.0,
        sampling_seed: int | None = None,
    ) -> None:
        super().__init__(
            client=client,
            skill_system_prompt=ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT,
            source_loader=source_loader,
            evaluator=evaluator,
            families=families,
            sampling_temperature=sampling_temperature,
            sampling_top_p=sampling_top_p,
            sampling_seed=sampling_seed,
        )

    def repair_candidate(
        self,
        candidate: CandidatePackage,
        conditions: Sequence[DebugCondition],
        *,
        feedback_arm: FeedbackArm = FeedbackArm.TRUTHFUL,
        initial_suite: DebugSuiteResult | None = None,
        mismatched_suite: DebugSuiteResult | None = None,
        max_turns: int = 12,
    ) -> AdaptiveRepairEpisode:
        source, source_hash = self.source_loader(candidate.instrument_id)
        if source_hash != candidate.source_sha256:
            raise ValueError("candidate source hash does not match current source bundle")
        candidate_sha = hashlib.sha256(candidate.skill_py.encode()).hexdigest()
        if initial_suite is None:
            initial_suite = evaluate_debug_suite(candidate, conditions, evaluator=self.evaluator)
        elif initial_suite.candidate_sha256 != candidate_sha:
            raise ValueError("provided initial suite belongs to a different candidate")
        if mismatched_suite is not None and mismatched_suite.candidate_sha256 != candidate_sha:
            raise ValueError("mismatched suite belongs to a different candidate")
        current = candidate
        current_suite = initial_suite
        submission: RepairSubmission | None = None
        suite_run_turn = -1
        submission_turn = -1
        exposed_refs: set[str] = set()
        status: Literal["CANDIDATE", "HOLD", "REJECT", "MAX_TURNS"] = "MAX_TURNS"
        summary = "adaptive repair turn budget exhausted"
        user_prompt = (
            f"Repair the `{candidate.instrument_id}` skill across the complete visible debug "
            "distribution. Inspect the source and current skill as needed. Run the debug suite, "
            "submit at most one evidence-grounded repair, rerun all conditions, then finish. "
            "This is one bounded repair episode and the current candidate may already contain "
            "repairs from earlier episodes. Preserve behavior supported by current evidence; "
            "diagnose and revise only from the execution evidence exposed in this episode."
        )
        prompt_hash = hashlib.sha256(
            (ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT + "\n" + user_prompt).encode()
        ).hexdigest()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        def feedback_view(suite: DebugSuiteResult) -> tuple[dict[str, Any], set[str]]:
            if feedback_arm is FeedbackArm.TRUTHFUL:
                refs = {ref for row in suite.conditions for ref in row.failure_refs}
                return suite.model_dump(mode="json"), refs
            if feedback_arm is FeedbackArm.GENERIC:
                ref = "feedback:binary-outcome"
                return {
                    "evidence_ref": ref,
                    "verdict": suite.verdict,
                    "message": "candidate did not satisfy every visible condition",
                }, {ref}
            if feedback_arm is FeedbackArm.NONE:
                ref = "feedback:withheld"
                return {
                    "evidence_ref": ref,
                    "status": "withheld",
                    "message": "execution evidence is withheld in this comparison arm",
                }, {ref}
            borrowed_suite = mismatched_suite or suite
            rows = list(borrowed_suite.conditions)
            shifted = rows if mismatched_suite is not None else rows[1:] + rows[:1]
            payload: list[dict[str, Any]] = []
            refs: set[str] = set()
            for borrowed in shifted:
                row = borrowed.model_dump(mode="json")
                row_refs = [
                    f"feedback:mismatched:{borrowed.condition.condition_id}:{index}"
                    for index, _ in enumerate(borrowed.failure_refs)
                ]
                row["failure_refs"] = row_refs
                refs.update(row_refs)
                payload.append(row)
            if not refs:
                refs.add("feedback:shuffled")
            return {
                "schema_version": suite.schema_version,
                "instrument_id": suite.instrument_id,
                "candidate_sha256": suite.candidate_sha256,
                "conditions": payload,
                "verdict": suite.verdict,
            }, refs

        def handler(
            name: str,
            arguments: dict[str, Any],
            model_turn: int,
        ) -> tuple[dict[str, Any], bool]:
            nonlocal current, current_suite, submission, suite_run_turn, submission_turn
            nonlocal status, summary, exposed_refs
            if name == "read_source_bundle":
                return {"source_ref": source_hash, "content": source}, False
            if name == "read_current_skill":
                return {"skill_md": current.skill_md, "skill_py": current.skill_py}, False
            if name == "run_debug_suite":
                if submission is None:
                    current_suite = initial_suite
                else:
                    current_suite = evaluate_debug_suite(
                        current,
                        conditions,
                        evaluator=self.evaluator,
                    )
                suite_run_turn = model_turn
                view, exposed_refs = feedback_view(current_suite)
                return view, False
            if name == "submit_repair":
                if submission is not None:
                    raise ValueError("one repair submission is allowed per archive round")
                if suite_run_turn < 0 or suite_run_turn >= model_turn:
                    raise ValueError("debug evidence must be inspected before repair")
                skill_md, skill_py, self_judgment = _validate_candidate_payload(arguments)
                refs = tuple(str(ref) for ref in arguments["evidence_refs"])
                if not refs:
                    raise ValueError("repair requires at least one debug evidence reference")
                unknown_refs = sorted(set(refs) - exposed_refs)
                if unknown_refs:
                    raise ValueError(f"repair cited unexposed evidence references: {unknown_refs}")
                submission = RepairSubmission(
                    diagnosis=str(arguments["diagnosis"]),
                    evidence_refs=refs,
                    skill_md=skill_md,
                    skill_py=skill_py,
                    expected_effect=str(arguments["expected_effect"]),
                    risks=tuple(str(risk) for risk in arguments["risks"]),
                    self_judgment=self_judgment,
                )
                current = CandidatePackage(
                    instrument_id=candidate.instrument_id,
                    skill_md=skill_md,
                    skill_py=skill_py,
                    self_judgment=self_judgment,
                    source_sha256=source_hash,
                    prompt_sha256=prompt_hash,
                    model=self.client.model,
                    raw_response={},
                )
                submission_turn = model_turn
                return {
                    "status": "captured",
                    "skill_sha256": hashlib.sha256(skill_py.encode()).hexdigest(),
                }, False
            if name == "finish_candidate":
                requested = str(arguments["status"])
                summary = str(arguments["summary"])
                if suite_run_turn < 0:
                    raise ValueError("debug suite must run before finishing")
                if requested == "CANDIDATE":
                    if submission is None:
                        raise ValueError("a repaired candidate requires a submission")
                    if suite_run_turn <= submission_turn:
                        raise ValueError("latest repair must be replayed before finishing")
                    if current_suite.verdict != "ADMIT":
                        raise ValueError("candidate cannot finish while a debug condition fails")
                status = requested  # type: ignore[assignment]
                return {"status": "captured", "candidate_status": status}, True
            raise KeyError(name)

        raw, events, completed = _run_tool_loop(
            client=self.client,
            messages=messages,
            tools=DEBUG_REPAIR_TOOLS,
            handler=handler,
            max_turns=max_turns,
            temperature=self.sampling_temperature,
            top_p=self.sampling_top_p,
            seed=self.sampling_seed,
        )
        if not completed:
            status = "MAX_TURNS"
        final_candidate = current.model_copy(
            update={"raw_response": {"responses": raw, "tool_events": events}}
        )
        return AdaptiveRepairEpisode(
            instrument_id=candidate.instrument_id,
            feedback_arm=feedback_arm,
            initial_candidate=candidate,
            final_candidate=final_candidate,
            initial_suite=initial_suite,
            final_suite=current_suite,
            submission=submission,
            tool_events=tuple(events),
            raw_responses=tuple(raw),
            agent_status=status,
            agent_summary=summary,
        )

    def repair_for_search(
        self,
        candidate: CandidatePackage,
        suite: DebugSuiteResult,
        seed: int,
        *,
        conditions: Sequence[DebugCondition],
        feedback_arm: FeedbackArm = FeedbackArm.TRUTHFUL,
        max_turns: int = 12,
    ) -> RepairOutcome:
        if suite.candidate_sha256 != hashlib.sha256(candidate.skill_py.encode()).hexdigest():
            raise ValueError("archive suite does not belong to repair parent")
        self.sampling_seed = seed
        episode = self.repair_candidate(
            candidate,
            conditions,
            feedback_arm=feedback_arm,
            initial_suite=suite,
            max_turns=max_turns,
        )
        return RepairOutcome(
            candidate=episode.final_candidate,
            record=episode.model_dump(mode="json"),
        )
