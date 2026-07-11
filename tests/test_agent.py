import hashlib
import json
import re
from types import SimpleNamespace

from proprio.adaptive_agent import ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT
from proprio.adaptive_search import DebugCondition, evaluate_debug_suite
from proprio.agent import (
    PERSISTENT_AGENT_CONTRACT,
    PERSISTENT_SYSTEM_PROMPT,
    AgentModelConfig,
    RepairLedgerEntry,
    _candidate_hash,
    append_verifier_record,
    arm_feedback_view,
    branch_agent_state,
    compact_messages,
    initial_agent_state,
    repeated_failed_strategy_count,
    resume_agent_state,
    run_agent_cycle,
)
from proprio.instrument_types import CandidatePackage, GateCheck, HardGateResult, SimulationScenario
from proprio.schema import canonical_json

INITIAL = "def run(controller):\n    controller.measure(1.0)\n    return {'value': 1.0}\n"
REPAIRED = """def run(controller):
    best = 0.0
    for index in range(3):
        reading = controller.measure(0.5)
        if reading["value"] > best:
            best = reading["value"]
    return {"value": best}
"""
FAIL_ONE = "def run(controller):\n    controller.measure(2.0)\n    return {'value': 2.0}\n"
FAIL_TWO = "def run(controller):\n    controller.measure(3.0)\n    return {'value': 3.0}\n"
SKILL_MD = "---\nname: adaptive-fixture\ndescription: Measure safely.\n---\n# Run\nMeasure.\n"
CONDITION = DebugCondition(
    condition_id="noise-repeat", scenario=SimulationScenario.NOMINAL, repetitions=3
)


def _source_loader(instrument_id):
    assert instrument_id == "adaptive-fixture"
    source = "# controller.measure(step) returns {'value': float}; repeat noisy measurements"
    return source, hashlib.sha256(source.encode()).hexdigest()


_SOURCE, _SOURCE_HASH = _source_loader("adaptive-fixture")


def _candidate():
    return CandidatePackage(
        instrument_id="adaptive-fixture",
        skill_md=SKILL_MD,
        skill_py=INITIAL,
        self_judgment={"verdict": "ACCEPT", "basis": ["source"]},
        source_sha256=_SOURCE_HASH,
        prompt_sha256="0" * 64,
        model="deepseek/deepseek-v4-flash",
        raw_response={},
    )


def _evaluator(instrument_id, source, *, scenario, condition=None):
    del condition
    assert instrument_id == "adaptive-fixture"
    valid = "range(3)" in source
    checks = (
        GateCheck(check_id="runtime-completed", passed=True),
        GateCheck(
            check_id="repeat-precision",
            passed=valid,
            evidence={"observed_repeats": 3 if valid else 1, "minimum_repeats": 3},
        ),
    )
    return HardGateResult(
        instrument_id=instrument_id,
        family="fixture",
        scenario=scenario,
        verdict="ADMIT" if valid else "REJECT",
        status="succeeded" if valid else "failed",
        checks=checks,
        trace=(),
        telemetry={},
        result={},
        runtime_error=None,
        skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
        simulator_sha256="1" * 64,
        verifier_sha256="2" * 64,
    )


class FakeUsage:
    def __init__(self, total_tokens):
        self.total_tokens = total_tokens

    def model_dump(self, mode="json"):
        del mode
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": 0,
            "completion_tokens": self.total_tokens,
        }


class FakeMessage:
    def __init__(self, calls, *, content=None):
        self.content = content
        self.reasoning_content = "preserved reasoning"
        self.tool_calls = [
            SimpleNamespace(
                id=f"call-{index}",
                function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
            )
            for index, (name, arguments) in enumerate(calls)
        ]

    def model_dump(self, mode="json"):
        del mode
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ],
        }


class FakeResponse:
    def __init__(self, message, *, total_tokens=10):
        self.choices = [SimpleNamespace(message=message)]
        self.usage = FakeUsage(total_tokens)

    def model_dump(self, mode="json"):
        del mode
        return {
            "object": "chat.completion",
            "id": "resp",
            "provider": "DeepInfra",
            "model": "deepseek/deepseek-v4-flash-20260423",
            "choices": [{"message": self.choices[0].message.model_dump()}],
            "usage": self.usage.model_dump(),
        }


class FakeClient:
    model = "deepseek/deepseek-v4-flash"

    def __init__(self, turns, *, total_tokens=10):
        self.turns = iter(turns)
        self.total_tokens = total_tokens
        self.call_count = 0
        self.request_messages = []

    def create_chat_completion(self, **kwargs):
        assert kwargs["tools"]
        assert kwargs["seed"] == 7
        assert kwargs["max_tokens"] == 8192
        self.call_count += 1
        self.request_messages.append(json.loads(json.dumps(kwargs["messages"])))
        return FakeResponse(FakeMessage(next(self.turns)), total_tokens=self.total_tokens)


class RaisingClient(FakeClient):
    def create_chat_completion(self, **kwargs):
        self.call_count += 1
        raise AssertionError("completed model call was repeated after resume")


def _run_config():
    return AgentModelConfig(
        requested_model="deepseek/deepseek-v4-flash",
        provider_route="DeepInfra,GMICloud",
        temperature=0.0,
        top_p=1.0,
        seed=7,
    )


def _initial_state(feedback_arm="truthful", *, model_call_budget=100, token_budget=1_000_000):
    return initial_agent_state(
        instrument_id="adaptive-fixture",
        feedback_arm=feedback_arm,
        source=_SOURCE,
        source_sha256=_SOURCE_HASH,
        candidate=_candidate(),
        conditions=(CONDITION,),
        run_config=_run_config(),
        model_call_budget=model_call_budget,
        token_budget=token_budget,
        goal="Qualify the fixture skill across the visible debug distribution.",
    )


def _inject(state, candidate, *, checkpoint_dir=None):
    suite = evaluate_debug_suite(candidate, (CONDITION,), evaluator=_evaluator)
    view, _ = arm_feedback_view(suite, state.feedback_arm)
    return append_verifier_record(state, suite, exposed_view=view, checkpoint_dir=checkpoint_dir)


def _submit_args(
    skill_py,
    evidence,
    *,
    diagnosis="single reading misses repeat precision",
    effect="add a repeated measurement",
):
    return {
        "diagnosis": diagnosis,
        "evidence_refs": [evidence],
        "skill_md": SKILL_MD,
        "skill_py": skill_py,
        "expected_effect": effect,
        "risks": ["simulation only"],
        "self_judgment": {"verdict": "ACCEPT", "basis": [evidence]},
    }


def _cycle(state, client, checkpoint_dir, *, compaction_byte_limit=None):
    return run_agent_cycle(
        state,
        client=client,
        evaluator=_evaluator,
        source=_SOURCE,
        conditions=(CONDITION,),
        checkpoint_dir=checkpoint_dir,
        compaction_byte_limit=compaction_byte_limit,
    )


def _is_stub(message):
    content = message.get("content")
    if not isinstance(content, str):
        return False
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(parsed, dict) and parsed.get("compacted") is True


def test_persistent_prompt_extends_frozen_contract_without_reserved_language():
    assert PERSISTENT_SYSTEM_PROMPT.startswith(ADAPTIVE_SKILL_ENGINEER_SYSTEM_PROMPT)
    assert PERSISTENT_SYSTEM_PROMPT.endswith(PERSISTENT_AGENT_CONTRACT)
    normalized = " ".join(PERSISTENT_AGENT_CONTRACT.lower().split())
    assert "persistent agent context" in normalized
    reserved = re.compile(r"\b" + "lay" + r"er[ _-]?[123]\b")
    assert reserved.search(normalized) is None


def test_rejected_verifier_record_appears_in_next_model_request(tmp_path):
    state = _inject(_initial_state(), _candidate(), checkpoint_dir=tmp_path)
    evidence = state.latest_verifier_record.conditions[0].failure_refs[0]
    state = _cycle(
        state, FakeClient([[("submit_repair", _submit_args(FAIL_ONE, evidence))]]), tmp_path
    )
    state = _inject(state, state.current_candidate, checkpoint_dir=tmp_path)
    capture = FakeClient([[("finish_candidate", {"status": "HOLD", "summary": "still failing"})]])
    _cycle(state, capture, tmp_path)
    request = capture.request_messages[0]
    blob = json.dumps(request)
    assert "repeat-precision" in blob
    assert any("verifier_evidence" in (message.get("content") or "") for message in request)


def test_prior_history_appears_across_two_verifier_cycles(tmp_path):
    state = _inject(_initial_state(), _candidate(), checkpoint_dir=tmp_path)
    evidence = state.latest_verifier_record.conditions[0].failure_refs[0]
    client = FakeClient(
        [
            [("read_current_skill", {})],
            [("submit_repair", _submit_args(FAIL_ONE, evidence))],
        ]
    )
    state = _cycle(state, client, tmp_path)
    state = _inject(state, state.current_candidate, checkpoint_dir=tmp_path)
    capture = FakeClient([[("finish_candidate", {"status": "HOLD", "summary": "review history"})]])
    _cycle(state, capture, tmp_path)
    request = capture.request_messages[0]
    assistants = [message for message in request if message["role"] == "assistant"]
    tools = [message for message in request if message["role"] == "tool"]
    assert len(assistants) >= 2
    assert any('"skill_py"' in (message.get("content") or "") for message in tools)
    assert any('"status":"captured"' in (message.get("content") or "") for message in tools)


def test_repair_ledger_records_failed_repair(tmp_path):
    state = _inject(_initial_state(), _candidate(), checkpoint_dir=tmp_path)
    evidence = state.latest_verifier_record.conditions[0].failure_refs[0]
    args = _submit_args(
        FAIL_ONE, evidence, diagnosis="single reading fails repeat gate", effect="repeat the read"
    )
    state = _cycle(state, FakeClient([[("submit_repair", args)]]), tmp_path)
    state = _inject(state, state.current_candidate, checkpoint_dir=tmp_path)
    entry = state.repair_ledger[-1]
    assert entry.outcome == "REJECT"
    assert "repeat-precision" in entry.failed_checks
    assert entry.diagnosis == "single reading fails repeat gate"
    assert entry.change_summary == "repeat the read"
    assert entry.evidence_refs == (evidence,)
    assert entry.candidate_sha256 == hashlib.sha256(FAIL_ONE.encode()).hexdigest()


def test_candidate_hashes_chain_parent_to_child(tmp_path):
    state = _inject(_initial_state(), _candidate(), checkpoint_dir=tmp_path)
    first_ref = state.latest_verifier_record.conditions[0].failure_refs[0]
    state = _cycle(
        state, FakeClient([[("submit_repair", _submit_args(FAIL_ONE, first_ref))]]), tmp_path
    )
    state = _inject(state, state.current_candidate, checkpoint_dir=tmp_path)
    second_ref = state.latest_verifier_record.conditions[0].failure_refs[0]
    state = _cycle(
        state, FakeClient([[("submit_repair", _submit_args(FAIL_TWO, second_ref))]]), tmp_path
    )
    state = _inject(state, state.current_candidate, checkpoint_dir=tmp_path)
    hashes = [entry.candidate_sha256 for entry in state.repair_ledger]
    assert hashes[0] == hashlib.sha256(FAIL_ONE.encode()).hexdigest()
    assert hashes[1] == hashlib.sha256(FAIL_TWO.encode()).hexdigest()
    chain = [hashlib.sha256(INITIAL.encode()).hexdigest(), *hashes]
    assert len(set(chain)) == len(chain)
    assert _candidate_hash(state.current_candidate) == hashes[-1]


def test_duplicate_candidate_submission_is_rejected(tmp_path):
    state = _inject(_initial_state(), _candidate(), checkpoint_dir=tmp_path)
    evidence = state.latest_verifier_record.conditions[0].failure_refs[0]
    before = _candidate_hash(state.current_candidate)
    client = FakeClient(
        [
            [("submit_repair", _submit_args(INITIAL, evidence))],
            [("finish_candidate", {"status": "HOLD", "summary": "cannot repair"})],
        ]
    )
    state = _cycle(state, client, tmp_path)
    assert state.status == "HOLD"
    assert _candidate_hash(state.current_candidate) == before
    duplicates = [entry for entry in state.repair_ledger if entry.outcome == "DUPLICATE"]
    assert len(duplicates) == 1
    error_result = next(
        message
        for message in reversed(state.messages)
        if message["role"] == "tool"
        and "duplicate candidate hash" in (message.get("content") or "")
    )
    assert "duplicate candidate hash" in error_result["content"]


def test_truthful_and_none_arms_do_not_share_post_branch_evidence(tmp_path):
    base = _initial_state("truthful")
    truthful = branch_agent_state(base, feedback_arm="truthful")
    none = branch_agent_state(base, feedback_arm="none")
    suite = evaluate_debug_suite(_candidate(), (CONDITION,), evaluator=_evaluator)
    truthful_view, _ = arm_feedback_view(suite, "truthful")
    none_view, _ = arm_feedback_view(suite, "none")
    truthful = append_verifier_record(truthful, suite, exposed_view=truthful_view)
    none = append_verifier_record(none, suite, exposed_view=none_view)
    assert truthful.messages[:2] == base.messages
    assert none.messages[:2] == base.messages
    truthful_blob = json.dumps(list(truthful.messages))
    none_blob = json.dumps(list(none.messages))
    failure_ref = suite.conditions[0].failure_refs[0]
    assert "repeat-precision" in truthful_blob
    assert failure_ref in truthful_blob
    assert "repeat-precision" not in none_blob
    assert failure_ref not in none_blob
    assert none_view == {
        "evidence_ref": "feedback:withheld",
        "status": "withheld",
        "message": "execution evidence is withheld in this comparison arm",
    }
    none_args = _submit_args(
        FAIL_ONE,
        "feedback:withheld",
        diagnosis="binary outcome indicates a defect",
        effect="apply a conservative revision",
    )
    none = _cycle(none, FakeClient([[("submit_repair", none_args)]]), tmp_path)
    replay = evaluate_debug_suite(none.current_candidate, (CONDITION,), evaluator=_evaluator)
    replay_view, _ = arm_feedback_view(replay, "none")
    none = append_verifier_record(none, replay, exposed_view=replay_view, checkpoint_dir=tmp_path)
    assert "repeat-precision" not in json.dumps(list(none.messages))
    assert none.repair_ledger[-1].failed_checks == ("repeat-precision",)
    assert none.latest_verifier_record.verdict == "REJECT"


def test_budget_exhaustion_yields_budget_exhausted_without_further_calls(tmp_path):
    state = _inject(_initial_state(model_call_budget=1), _candidate(), checkpoint_dir=tmp_path)
    client = FakeClient(
        [
            [("read_current_skill", {})],
            [("finish_candidate", {"status": "HOLD", "summary": "unused"})],
        ]
    )
    state = _cycle(state, client, tmp_path)
    assert state.status == "BUDGET_EXHAUSTED"
    assert client.call_count == 1


def test_compaction_preserves_anchors_and_is_idempotent():
    state = _initial_state()
    messages = list(state.messages)
    for index in range(20):
        messages.append(
            {
                "role": "tool",
                "tool_call_id": f"filler-{index}",
                "content": json.dumps({"filler": "x" * 700, "index": index}),
            }
        )
    digest = "a" * 64
    messages.append(
        {
            "role": "tool",
            "tool_call_id": "hashed",
            "content": json.dumps({"candidate_sha256": digest}),
        }
    )
    messages.append(
        {
            "role": "user",
            "content": json.dumps(
                {
                    "verifier_evidence": {"evidence_ref": "feedback:withheld"},
                    "repair_ledger": [],
                    "remaining_model_calls": 1,
                    "remaining_tokens": 1,
                }
            ),
        }
    )
    for index in range(8):
        messages.append({"role": "user", "content": json.dumps({"tail": index})})
    ledger = (
        RepairLedgerEntry(
            candidate_sha256=digest,
            failed_checks=(),
            diagnosis="d",
            evidence_refs=("feedback:withheld",),
            change_summary="s",
            outcome="REJECT",
        ),
    )
    big = state.model_copy(update={"messages": tuple(messages), "repair_ledger": ledger})
    full_size = len(canonical_json(big.messages))
    limit = 6000
    assert full_size > limit
    compacted = compact_messages(big, byte_limit=limit)
    assert compacted.messages[0] == big.messages[0]
    assert compacted.messages[1] == big.messages[1]
    assert compacted.messages[-8:] == big.messages[-8:]
    assert any(digest in (message.get("content") or "") for message in compacted.messages)
    assert any(
        "verifier_evidence" in (message.get("content") or "") for message in compacted.messages
    )
    assert any(_is_stub(message) for message in compacted.messages)
    assert len(canonical_json(compacted.messages)) < full_size
    twice = compact_messages(compacted, byte_limit=limit)
    assert canonical_json(twice.messages) == canonical_json(compacted.messages)
    assert compact_messages(big, byte_limit=10_000_000) is big


def test_reasoning_content_preserved_in_persisted_assistant_message(tmp_path):
    state = _inject(_initial_state(), _candidate(), checkpoint_dir=tmp_path)
    client = FakeClient([[("finish_candidate", {"status": "HOLD", "summary": "insufficient"})]])
    state = _cycle(state, client, tmp_path)
    assistants = [message for message in state.messages if message["role"] == "assistant"]
    assert assistants
    assert all(message.get("reasoning_content") == "preserved reasoning" for message in assistants)


def test_resume_produces_same_next_state_as_uninterrupted_run(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    reference = _inject(_initial_state(), _candidate(), checkpoint_dir=dir_a)
    evidence = reference.latest_verifier_record.conditions[0].failure_refs[0]
    reference = _cycle(
        reference, FakeClient([[("submit_repair", _submit_args(FAIL_ONE, evidence))]]), dir_a
    )
    reference = _inject(reference, reference.current_candidate, checkpoint_dir=dir_a)
    final_a = _cycle(
        reference,
        FakeClient([[("finish_candidate", {"status": "REJECT", "summary": "no repair"})]]),
        dir_a,
    )

    resumed_seed = _inject(_initial_state(), _candidate(), checkpoint_dir=dir_b)
    _cycle(resumed_seed, FakeClient([[("submit_repair", _submit_args(FAIL_ONE, evidence))]]), dir_b)
    resumed = resume_agent_state(dir_b)
    assert resumed is not None
    resumed = _inject(resumed, resumed.current_candidate, checkpoint_dir=dir_b)
    final_b = _cycle(
        resumed,
        FakeClient([[("finish_candidate", {"status": "REJECT", "summary": "no repair"})]]),
        dir_b,
    )
    assert canonical_json(final_a) == canonical_json(final_b)


def test_completed_model_calls_are_not_repeated_after_resume(tmp_path):
    state = _inject(_initial_state(), _candidate(), checkpoint_dir=tmp_path)
    evidence = state.latest_verifier_record.conditions[0].failure_refs[0]
    state = _cycle(
        state, FakeClient([[("submit_repair", _submit_args(FAIL_ONE, evidence))]]), tmp_path
    )
    state = _inject(state, state.current_candidate, checkpoint_dir=tmp_path)
    state = _cycle(
        state,
        FakeClient([[("finish_candidate", {"status": "REJECT", "summary": "done"})]]),
        tmp_path,
    )
    assert state.status == "REJECT"
    resumed = resume_agent_state(tmp_path)
    assert resumed is not None
    assert canonical_json(resumed) == canonical_json(state)
    raising = RaisingClient([])
    again = _cycle(resumed, raising, tmp_path)
    assert raising.call_count == 0
    assert canonical_json(again) == canonical_json(resumed)


def test_repeated_failed_strategy_count_detects_consecutive_repeats():
    def entry(checks, outcome):
        return RepairLedgerEntry(
            candidate_sha256=hashlib.sha256(str(checks).encode()).hexdigest(),
            failed_checks=checks,
            diagnosis="d",
            evidence_refs=(),
            change_summary="s",
            outcome=outcome,
        )

    ledger = (
        entry(("a",), "REJECT"),
        entry(("a",), "REJECT"),
        entry(("b",), "REJECT"),
        entry(("a", "b"), "DUPLICATE"),
    )
    state = _initial_state().model_copy(update={"repair_ledger": ledger})
    assert repeated_failed_strategy_count(state) == 1
