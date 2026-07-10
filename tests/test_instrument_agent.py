import json
from types import SimpleNamespace

from proprio.instrument_agent import SKILL_ENGINEER_SYSTEM_PROMPT, DSV4InstrumentAgent
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_sources import load_instrument_source
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    JudgeReview,
    SimulationScenario,
    combine_hybrid_verdict,
)

INITIAL_SKILL = """def run(controller):
    controller.reset()
    controller.pick_up_tip()
    controller.aspirate(120.0)
    controller.dispense(120.0)
    controller.drop_tip()
    return {"transferred_ul": 120.0}
"""

REPAIRED_SKILL = """def run(controller):
    controller.reset()
    controller.pick_up_tip()
    controller.aspirate(60.0)
    controller.dispense(60.0)
    controller.aspirate(60.0)
    controller.dispense(60.0)
    controller.drop_tip()
    return {"transferred_ul": 120.0}
"""

SKILL_MD = """---
name: ot2-transfer
description: Transfer a validated volume with an OT-2-style controller.
---
# Run
Execute the source-declared transfer and preserve cleanup semantics.
"""


class FakeMessage:
    def __init__(self, calls: list[tuple[str, dict]]):
        self.content = None
        self.reasoning_content = "preserved reasoning"
        self.tool_calls = [
            SimpleNamespace(
                id=f"call-{index}",
                function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
            )
            for index, (name, arguments) in enumerate(calls)
        ]

    def model_dump(self, mode: str = "json") -> dict:
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
    def __init__(self, message: FakeMessage):
        self.choices = [SimpleNamespace(message=message)]

    def model_dump(self, mode: str = "json") -> dict:
        del mode
        return {"choices": [{"message": self.choices[0].message.model_dump()}]}


class FakeCompletions:
    def __init__(self, turns: list[list[tuple[str, dict]]]):
        self.turns = iter(turns)

    def create(self, **kwargs) -> FakeResponse:
        assert kwargs["tools"]
        assert kwargs["temperature"] == 0.0
        return FakeResponse(FakeMessage(next(self.turns)))


class FakeDSV4Client:
    model = "dsv4"

    def __init__(self, turns: list[list[tuple[str, dict]]]):
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(turns)))


def initial_candidate() -> CandidatePackage:
    _, source_hash = load_instrument_source("ot2-transfer")
    return CandidatePackage(
        instrument_id="ot2-transfer",
        skill_md=SKILL_MD,
        skill_py=INITIAL_SKILL,
        self_judgment={"verdict": "ACCEPT", "basis": ["source faithful"]},
        source_sha256=source_hash,
        prompt_sha256="0" * 64,
        model="dsv4",
        raw_response={},
    )


def test_instrument_neutral_prompt_contains_no_held_out_specifics() -> None:
    lowered = SKILL_ENGINEER_SYSTEM_PROMPT.lower()
    for term in ("ot2", "hamilton", "battery", "powder", "hall", "keithley", "xrd"):
        assert term not in lowered


def test_tool_use_draft_preserves_reasoning_and_source_provenance() -> None:
    client = FakeDSV4Client(
        [
            [("read_source_bundle", {})],
            [
                (
                    "submit_initial_candidate",
                    {
                        "skill_md": SKILL_MD,
                        "skill_py": INITIAL_SKILL,
                        "self_judgment": {
                            "verdict": "ACCEPT",
                            "basis": ["source faithful"],
                        },
                    },
                )
            ],
        ]
    )
    candidate = DSV4InstrumentAgent(client=client).draft("ot2-transfer")
    assert candidate.skill_py == INITIAL_SKILL
    assert candidate.source_sha256 == load_instrument_source("ot2-transfer")[1]
    assert all(
        response["preserved_assistant_message"]["reasoning_content"] == "preserved reasoning"
        for response in candidate.raw_response["responses"]
    )


def test_draft_cannot_submit_before_a_prior_source_inspection_turn() -> None:
    submission = {
        "skill_md": SKILL_MD,
        "skill_py": INITIAL_SKILL,
        "self_judgment": {"verdict": "ACCEPT", "basis": ["source faithful"]},
    }
    client = FakeDSV4Client(
        [
            [("submit_initial_candidate", submission)],
            [("read_source_bundle", {})],
            [("submit_initial_candidate", submission)],
        ]
    )
    candidate = DSV4InstrumentAgent(client=client).draft("ot2-transfer")
    assert candidate.raw_response["tool_events"][0]["result"]["status"] == "error"
    assert candidate.raw_response["tool_events"][-1]["result"]["status"] == "captured"


def test_truthful_tool_use_episode_repairs_and_replays() -> None:
    repair_arguments = {
        "diagnosis": "The reported 75 uL stroke limit rejects the 120 uL stroke.",
        "evidence_refs": ["stroke-capacity"],
        "skill_md": SKILL_MD,
        "skill_py": REPAIRED_SKILL,
        "expected_effect": "Two 60 uL strokes preserve 120 uL total within capacity.",
        "risks": ["reported capacity may drift again"],
        "self_judgment": {"verdict": "ACCEPT", "basis": ["feedback grounded"]},
    }
    client = FakeDSV4Client(
        [
            [("run_simulator", {})],
            [("submit_repair", repair_arguments)],
            [("run_simulator", {})],
            [("finish_repair", {"status": "CANDIDATE", "summary": "replay passed"})],
        ]
    )
    episode = DSV4InstrumentAgent(client=client).repair(
        initial_candidate(), feedback_arm=FeedbackArm.TRUTHFUL
    )
    assert episode.initial_gate.verdict == "REJECT"
    assert episode.final_gate.verdict == "ADMIT"
    assert episode.agent_status == "CANDIDATE"
    assert len(episode.submissions) == 1
    assert [event["name"] for event in episode.tool_events] == [
        "run_simulator",
        "submit_repair",
        "run_simulator",
        "finish_repair",
    ]


def test_repair_cannot_edit_before_feedback_or_finish_before_replay() -> None:
    repair_arguments = {
        "diagnosis": "The reported stroke limit requires a split transfer.",
        "evidence_refs": ["stroke-capacity"],
        "skill_md": SKILL_MD,
        "skill_py": REPAIRED_SKILL,
        "expected_effect": "Two strokes preserve total volume.",
        "risks": [],
        "self_judgment": {"verdict": "ACCEPT", "basis": ["feedback grounded"]},
    }
    client = FakeDSV4Client(
        [
            [("submit_repair", repair_arguments)],
            [("run_simulator", {})],
            [("submit_repair", repair_arguments)],
            [("finish_repair", {"status": "CANDIDATE", "summary": "done"})],
            [("run_simulator", {})],
            [("finish_repair", {"status": "CANDIDATE", "summary": "replayed"})],
        ]
    )
    episode = DSV4InstrumentAgent(client=client).repair(
        initial_candidate(), feedback_arm=FeedbackArm.TRUTHFUL
    )
    assert episode.tool_events[0]["result"]["status"] == "error"
    assert episode.tool_events[3]["result"]["status"] == "error"
    assert episode.final_gate.verdict == "ADMIT"
    assert episode.agent_status == "CANDIDATE"


def test_evolution_repair_requires_history_after_latest_submission() -> None:
    repair_arguments = {
        "diagnosis": "The reported stroke limit requires a split transfer.",
        "evidence_refs": ["stroke-capacity"],
        "skill_md": SKILL_MD,
        "skill_py": REPAIRED_SKILL,
        "expected_effect": "Two strokes preserve total volume.",
        "risks": [],
        "self_judgment": {"verdict": "ACCEPT", "basis": ["feedback grounded"]},
    }
    client = FakeDSV4Client(
        [
            [("run_simulator", {})],
            [("submit_repair", repair_arguments)],
            [("run_simulator", {})],
            [("finish_repair", {"status": "CANDIDATE", "summary": "target passed"})],
            [("run_history", {})],
            [("finish_repair", {"status": "CANDIDATE", "summary": "history passed"})],
        ]
    )
    episode = DSV4InstrumentAgent(client=client).repair(
        initial_candidate(),
        feedback_arm=FeedbackArm.TRUTHFUL,
        require_history=True,
        history_scenarios=(SimulationScenario.NOMINAL,),
    )
    assert episode.tool_events[3]["result"]["status"] == "error"
    assert episode.tool_events[4]["result"]["all_admit"] is True
    assert episode.agent_status == "CANDIDATE"


def test_history_tool_rejects_target_scenario_leakage() -> None:
    client = FakeDSV4Client(
        [
            [("run_history", {})],
            [("finish_repair", {"status": "HOLD", "summary": "no target evidence"})],
        ]
    )
    episode = DSV4InstrumentAgent(client=client).repair(
        initial_candidate(),
        feedback_arm=FeedbackArm.NONE,
        scenario=SimulationScenario.REPAIR,
        require_history=True,
        history_scenarios=(SimulationScenario.NOMINAL, SimulationScenario.REPAIR),
    )
    assert episode.tool_events[0]["result"]["status"] == "error"
    assert "target scenario cannot be exposed" in episode.tool_events[0]["result"]["error"]
    assert episode.agent_status == "HOLD"


def test_stateful_judge_must_reason_after_inspecting_tools() -> None:
    repair_client = FakeDSV4Client(
        [
            [("run_simulator", {})],
            [
                (
                    "submit_repair",
                    {
                        "diagnosis": "stroke limit changed",
                        "evidence_refs": ["stroke-capacity"],
                        "skill_md": SKILL_MD,
                        "skill_py": REPAIRED_SKILL,
                        "expected_effect": "split strokes",
                        "risks": [],
                        "self_judgment": {
                            "verdict": "ACCEPT",
                            "basis": ["feedback grounded"],
                        },
                    },
                )
            ],
            [("run_simulator", {})],
            [("finish_repair", {"status": "CANDIDATE", "summary": "replayed"})],
        ]
    )
    episode = DSV4InstrumentAgent(client=repair_client).repair(
        initial_candidate(), feedback_arm=FeedbackArm.TRUTHFUL
    )
    review = {
        "verdict": "ACCEPT",
        "critical_findings": [],
        "evidence_refs": ["replay"],
        "summary": "evidence supports the repair",
    }
    judge_client = FakeDSV4Client(
        [
            [
                ("read_source_bundle", {}),
                ("read_skill_versions", {}),
                ("read_skill_diff", {}),
                ("read_execution_evidence", {}),
                ("run_replay", {}),
                ("submit_review", review),
            ],
            [("submit_review", review)],
        ]
    )
    judged = DSV4InstrumentAgent(client=judge_client).judge(episode)
    assert judged.status == "completed"
    assert judged.tool_events[-2]["result"]["status"] == "error"
    execution_evidence = next(
        event["result"]
        for event in judged.tool_events
        if event["name"] == "read_execution_evidence"
    )
    exposed_refs = {
        event["result"].get("evidence_ref")
        for event in execution_evidence["protocol_events"]
        if event["name"] == "run_simulator"
    }
    assert any(ref and ref.startswith("gate:") for ref in exposed_refs)
    assert judged.review is not None
    assert judged.review.verdict == "ACCEPT"


def test_hybrid_verdict_never_overrides_hard_failure() -> None:
    hard = evaluate_instrument_skill(
        "ot2-transfer", INITIAL_SKILL, scenario=SimulationScenario.REPAIR
    )
    accepting_judge = JudgeReview(
        verdict="ACCEPT",
        critical_findings=(),
        evidence_refs=("gate",),
        summary="accepted",
    )
    verdict = combine_hybrid_verdict(hard, accepting_judge)
    assert verdict.verdict == "REJECT"
    assert verdict.hard_verdict == "REJECT"


def test_critical_finding_vetoes_an_accept_label() -> None:
    hard = evaluate_instrument_skill("ot2-transfer", INITIAL_SKILL)
    inconsistent = JudgeReview(
        verdict="ACCEPT",
        critical_findings=("candidate overfits one fixture",),
        evidence_refs=("replay",),
        summary="accept despite critical issue",
    )
    verdict = combine_hybrid_verdict(hard, inconsistent)
    assert hard.verdict == "ADMIT"
    assert verdict.verdict == "REJECT"
    assert verdict.judge_verdict == "REJECT"


def test_hybrid_verdict_holds_when_judge_is_unavailable() -> None:
    hard = evaluate_instrument_skill("ot2-transfer", INITIAL_SKILL)
    verdict = combine_hybrid_verdict(hard, None)
    assert hard.verdict == "ADMIT"
    assert verdict.verdict == "HOLD"
