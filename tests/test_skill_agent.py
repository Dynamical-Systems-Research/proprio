import hashlib
import json
from types import SimpleNamespace

from proprio.agent_runtime import _is_retryable_transport_error, _transport_retry_delay
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    GateCheck,
    HardGateResult,
    SimulationScenario,
)
from proprio.skill_agent import (
    QUALIFIED_SKILL_SYSTEM_PROMPT,
    SkillAgent,
)
from proprio.skill_search import DebugCondition, evaluate_debug_suite

INITIAL = "def run(controller):\n    controller.measure(1.0)\n    return {'value': 1.0}\n"
REPAIRED = """def run(controller):
    best = 0.0
    for index in range(3):
        reading = controller.measure(0.5)
        if reading["value"] > best:
            best = reading["value"]
    return {"value": best}
"""
SKILL_MD = "---\nname: simulated-fixture\ndescription: Measure safely.\n---\n# Run\nMeasure.\n"


def test_malformed_provider_json_is_retryable_transport_corruption() -> None:
    error = json.JSONDecodeError("truncated", "{", 1)
    assert _is_retryable_transport_error(error) == (True, None)


def test_rate_limit_backoff_is_longer_than_generic_transport_backoff() -> None:
    assert _transport_retry_delay(429, 1) == 30.0
    assert _transport_retry_delay(429, 2) == 60.0
    assert _transport_retry_delay(502, 2) == 4.0


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
    def __init__(self, message):
        self.choices = [SimpleNamespace(message=message)]

    def model_dump(self, mode="json"):
        del mode
        return {"choices": [{"message": self.choices[0].message.model_dump()}]}


class FakeClient:
    model = "deepseek/deepseek-v4-flash"

    def __init__(self, turns):
        self.turns = iter(turns)

    def create_chat_completion(self, **kwargs):
        assert kwargs["tools"]
        return FakeResponse(FakeMessage(next(self.turns)))


class ReasoningOnlyThenToolClient(FakeClient):
    def __init__(self, turns):
        super().__init__(turns)
        self.request_messages = []
        self.first = True

    def create_chat_completion(self, **kwargs):
        self.request_messages.append(json.loads(json.dumps(kwargs["messages"])))
        if self.first:
            self.first = False
            return FakeResponse(FakeMessage([]))
        return super().create_chat_completion(**kwargs)


class RetryableTransportError(Exception):
    status_code = 502


class TransientFailureThenToolClient(FakeClient):
    def __init__(self, turns):
        super().__init__(turns)
        self.failed = False

    def create_chat_completion(self, **kwargs):
        if not self.failed:
            self.failed = True
            raise RetryableTransportError("transient upstream failure")
        return super().create_chat_completion(**kwargs)


class MissingChoicesThenToolClient(FakeClient):
    def __init__(self, turns):
        super().__init__(turns)
        self.failed = False

    def create_chat_completion(self, **kwargs):
        if not self.failed:
            self.failed = True
            return SimpleNamespace(
                choices=None,
                model_dump=lambda mode="json": {"choices": None, "mode": mode},
            )
        return super().create_chat_completion(**kwargs)


def _source_loader(instrument_id: str):
    assert instrument_id == "simulated-fixture"
    source = "# controller.measure(step) returns {'value': float}; repeat noisy measurements"
    return source, hashlib.sha256(source.encode()).hexdigest()


def _candidate() -> CandidatePackage:
    _, source_hash = _source_loader("simulated-fixture")
    return CandidatePackage(
        instrument_id="simulated-fixture",
        skill_md=SKILL_MD,
        skill_py=INITIAL,
        self_judgment={"verdict": "ACCEPT", "basis": ["source"]},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model="deepseek/deepseek-v4-flash",
        raw_response={},
    )


def _evaluator(instrument_id, source, *, scenario, condition=None):
    del condition
    assert instrument_id == "simulated-fixture"
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


def test_skill_prompt_declares_bounded_feedback_driven_execution() -> None:
    normalized = " ".join(QUALIFIED_SKILL_SYSTEM_PROMPT.split())
    assert "for ... in range(...)" in normalized
    assert "direct simulator-state reads" in normalized
    assert "finish the agent episode as HOLD" in normalized
    assert "the skill cannot set verifier thresholds" in normalized
    assert "maximum safe repetition budget" not in normalized


def test_agent_repairs_only_after_debug_evidence_and_replay() -> None:
    condition = DebugCondition(
        condition_id="noise-repeat",
        scenario=SimulationScenario.NOMINAL,
        repetitions=3,
    )
    initial_suite = evaluate_debug_suite(_candidate(), (condition,), evaluator=_evaluator)
    evidence = initial_suite.conditions[0].failure_refs[0]
    client = FakeClient(
        [
            [("run_debug_suite", {})],
            [
                (
                    "submit_repair",
                    {
                        "diagnosis": "one observation does not satisfy repeat precision",
                        "evidence_refs": [evidence],
                        "skill_md": SKILL_MD,
                        "skill_py": REPAIRED,
                        "expected_effect": "three measurements clear repeat precision",
                        "risks": ["simulation only"],
                        "self_judgment": {
                            "verdict": "ACCEPT",
                            "basis": [evidence],
                        },
                    },
                )
            ],
            [("run_debug_suite", {})],
            [("finish_candidate", {"status": "CANDIDATE", "summary": "suite passed"})],
        ]
    )
    agent = SkillAgent(
        client=client,
        source_loader=_source_loader,
        evaluator=_evaluator,
        families={"simulated-fixture": "fixture"},
    )
    episode = agent.repair_candidate(_candidate(), (condition,))
    assert episode.agent_status == "CANDIDATE"
    assert episode.initial_suite.verdict == "REJECT"
    assert episode.final_suite.verdict == "ADMIT"


def test_reasoning_only_response_is_preserved_and_recovered() -> None:
    condition = DebugCondition(
        condition_id="noise-repeat",
        scenario=SimulationScenario.NOMINAL,
        repetitions=3,
    )
    initial_suite = evaluate_debug_suite(_candidate(), (condition,), evaluator=_evaluator)
    evidence = initial_suite.conditions[0].failure_refs[0]
    client = ReasoningOnlyThenToolClient(
        [
            [("run_debug_suite", {})],
            [
                (
                    "submit_repair",
                    {
                        "diagnosis": "one observation does not satisfy repeat precision",
                        "evidence_refs": [evidence],
                        "skill_md": SKILL_MD,
                        "skill_py": REPAIRED,
                        "expected_effect": "three measurements clear repeat precision",
                        "risks": ["simulation only"],
                        "self_judgment": {"verdict": "ACCEPT", "basis": [evidence]},
                    },
                )
            ],
            [("run_debug_suite", {})],
            [("finish_candidate", {"status": "CANDIDATE", "summary": "suite passed"})],
        ]
    )
    agent = SkillAgent(
        client=client,
        source_loader=_source_loader,
        evaluator=_evaluator,
        families={"simulated-fixture": "fixture"},
    )
    episode = agent.repair_candidate(_candidate(), (condition,))
    assert episode.agent_status == "CANDIDATE"
    assert episode.raw_responses[0]["transport_recovery"] == "reasoning-only-no-action"
    recovery_messages = client.request_messages[1]
    assert recovery_messages[-2]["content"] == "[reasoning-only response; no action emitted]"
    assert recovery_messages[-2]["reasoning_content"] == "preserved reasoning"
    assert recovery_messages[-1]["role"] == "user"
    assert episode.submission is not None
    assert episode.submission.evidence_refs == (evidence,)
    assert all(
        row["preserved_assistant_message"]["reasoning_content"] == "preserved reasoning"
        for row in episode.raw_responses
    )


def test_retryable_transport_failure_is_recorded_without_spending_model_turn(
    monkeypatch,
) -> None:
    monkeypatch.setattr("proprio.agent_runtime.time.sleep", lambda _: None)
    condition = DebugCondition(
        condition_id="noise-repeat",
        scenario=SimulationScenario.NOMINAL,
        repetitions=3,
    )
    initial_suite = evaluate_debug_suite(_candidate(), (condition,), evaluator=_evaluator)
    evidence = initial_suite.conditions[0].failure_refs[0]
    client = TransientFailureThenToolClient(
        [
            [("run_debug_suite", {})],
            [
                (
                    "submit_repair",
                    {
                        "diagnosis": "one observation does not satisfy repeat precision",
                        "evidence_refs": [evidence],
                        "skill_md": SKILL_MD,
                        "skill_py": REPAIRED,
                        "expected_effect": "three measurements clear repeat precision",
                        "risks": ["simulation only"],
                        "self_judgment": {"verdict": "ACCEPT", "basis": [evidence]},
                    },
                )
            ],
            [("run_debug_suite", {})],
            [("finish_candidate", {"status": "CANDIDATE", "summary": "suite passed"})],
        ]
    )
    agent = SkillAgent(
        client=client,
        source_loader=_source_loader,
        evaluator=_evaluator,
        families={"simulated-fixture": "fixture"},
    )
    episode = agent.repair_candidate(_candidate(), (condition,))
    assert episode.agent_status == "CANDIDATE"
    transport = episode.raw_responses[0]
    assert transport["schema_version"] == "proprio.model_transport_error.v0.2"
    assert transport["status_code"] == 502
    assert transport["model_turn"] == 0
    assert transport["will_retry"]


def test_missing_choice_response_is_recorded_and_retried(monkeypatch) -> None:
    monkeypatch.setattr("proprio.agent_runtime.time.sleep", lambda _: None)
    condition = DebugCondition(
        condition_id="noise-repeat",
        scenario=SimulationScenario.NOMINAL,
        repetitions=3,
    )
    initial_suite = evaluate_debug_suite(_candidate(), (condition,), evaluator=_evaluator)
    evidence = initial_suite.conditions[0].failure_refs[0]
    client = MissingChoicesThenToolClient(
        [
            [("run_debug_suite", {})],
            [
                (
                    "submit_repair",
                    {
                        "diagnosis": "one observation does not satisfy repeat precision",
                        "evidence_refs": [evidence],
                        "skill_md": SKILL_MD,
                        "skill_py": REPAIRED,
                        "expected_effect": "three measurements clear repeat precision",
                        "risks": ["simulation only"],
                        "self_judgment": {"verdict": "ACCEPT", "basis": [evidence]},
                    },
                )
            ],
            [("run_debug_suite", {})],
            [("finish_candidate", {"status": "CANDIDATE", "summary": "suite passed"})],
        ]
    )
    agent = SkillAgent(
        client=client,
        source_loader=_source_loader,
        evaluator=_evaluator,
        families={"simulated-fixture": "fixture"},
    )
    episode = agent.repair_candidate(_candidate(), (condition,))
    assert episode.agent_status == "CANDIDATE"
    transport = episode.raw_responses[0]
    assert transport["schema_version"] == "proprio.model_transport_invalid_response.v0.2"
    assert transport["error_type"] == "missing-choice-or-message"
    assert transport["model_turn"] == 0
    assert transport["will_retry"]


def test_no_feedback_arm_withholds_check_identity_and_cannot_claim_candidate() -> None:
    condition = DebugCondition(
        condition_id="noise-repeat",
        scenario=SimulationScenario.NOMINAL,
        repetitions=1,
    )
    client = FakeClient(
        [
            [("run_debug_suite", {})],
            [("finish_candidate", {"status": "HOLD", "summary": "evidence withheld"})],
        ]
    )
    agent = SkillAgent(
        client=client,
        source_loader=_source_loader,
        evaluator=_evaluator,
        families={"simulated-fixture": "fixture"},
    )
    episode = agent.repair_candidate(
        _candidate(),
        (condition,),
        feedback_arm=FeedbackArm.NONE,
    )
    result = next(
        event["result"] for event in episode.tool_events if event["name"] == "run_debug_suite"
    )
    assert episode.feedback_arm is FeedbackArm.NONE
    assert episode.agent_status == "HOLD"
    assert result == {
        "evidence_ref": "feedback:withheld",
        "status": "withheld",
        "message": "execution evidence is withheld in this comparison arm",
    }
    assert "repeat-precision" not in str(result)


def test_mismatched_arm_can_receive_a_coherent_opposite_fault_suite() -> None:
    actual = DebugCondition(
        condition_id="actual-noise",
        scenario=SimulationScenario.NOMINAL,
        parameters=(("fault", 1.0),),
    )
    opposite = DebugCondition(
        condition_id="opposite-range",
        scenario=SimulationScenario.NOMINAL,
        parameters=(("fault", 2.0),),
    )

    def evaluator(instrument_id, source, *, scenario, condition=None):
        fault = dict(condition or {})["fault"]
        check_id = "noise-precision" if fault == 1.0 else "range-coverage"
        return HardGateResult(
            instrument_id=instrument_id,
            family="fixture",
            scenario=scenario,
            verdict="REJECT",
            status="failed",
            checks=(GateCheck(check_id=check_id, passed=False),),
            trace=(),
            telemetry={},
            result={},
            runtime_error=None,
            skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
            simulator_sha256="1" * 64,
            verifier_sha256="2" * 64,
        )

    candidate = _candidate()
    initial_suite = evaluate_debug_suite(candidate, (actual,), evaluator=evaluator)
    mismatched_suite = evaluate_debug_suite(candidate, (opposite,), evaluator=evaluator)
    client = FakeClient(
        [
            [("run_debug_suite", {})],
            [("finish_candidate", {"status": "HOLD", "summary": "opposite evidence"})],
        ]
    )
    agent = SkillAgent(
        client=client,
        source_loader=_source_loader,
        evaluator=evaluator,
        families={"simulated-fixture": "fixture"},
    )
    episode = agent.repair_candidate(
        candidate,
        (actual,),
        feedback_arm=FeedbackArm.MISMATCHED,
        initial_suite=initial_suite,
        mismatched_suite=mismatched_suite,
    )
    result = next(
        event["result"] for event in episode.tool_events if event["name"] == "run_debug_suite"
    )
    assert "range-coverage" in str(result)
    assert "noise-precision" not in str(result)
    assert "feedback:mismatched:opposite-range" in str(result)
