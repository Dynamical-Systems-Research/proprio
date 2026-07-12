from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from proprio.agent import resume_agent_state
from proprio.cross_family import (
    freeze_cross_family_method,
    run_cross_family_session,
    run_persistent_causal_pair,
    run_persistent_evolution_proposal,
    run_persistent_repair_trajectory,
    verify_cross_family_method,
)
from proprio.external_instruments import load_external_source as load_external_source
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    GateCheck,
    HardGateResult,
    SimulationScenario,
)
from proprio.schema import canonical_json
from proprio.skill_search import (
    DebugCondition,
    DebugSuiteResult,
    FixturePreflightReport,
    SearchReport,
    evaluate_debug_suite,
)

ROOT = Path(__file__).resolve().parents[1]

INITIAL = "def run(controller):\n    controller.measure(1.0)\n    return {'value': 1.0}\n"
REPAIRED = (
    "def run(controller):\n"
    "    best = 0.0\n"
    "    for index in range(3):\n"
    "        reading = controller.measure(0.5)\n"
    "        best = reading\n"
    "    return {'value': best}\n"
)
FAIL_ONE = "def run(controller):\n    controller.measure(2.0)\n    return {'value': 2.0}\n"
DRIFT_FIX = (
    "def run(controller):\n    controller.measure(0.25)  # drift-fix\n    return {'value': 0.25}\n"
)
SKILL_MD = "---\nname: simulated-fixture\ndescription: Measure safely.\n---\n# Run\nMeasure.\n"

_SOURCE = "# controller.measure(step) returns a float; repeat noisy measurements"
_SOURCE_HASH = hashlib.sha256(_SOURCE.encode()).hexdigest()

CONDITION = DebugCondition(
    condition_id="noise-repeat", scenario=SimulationScenario.NOMINAL, repetitions=3
)
DRIFT_CONDITION = DebugCondition(
    condition_id="drift-lock", scenario=SimulationScenario.DRIFT, repetitions=3
)


def _candidate(skill_py: str = INITIAL) -> CandidatePackage:
    return CandidatePackage(
        instrument_id="simulated-fixture",
        skill_md=SKILL_MD,
        skill_py=skill_py,
        self_judgment={"verdict": "ACCEPT", "basis": ["source"]},
        source_sha256=_SOURCE_HASH,
        prompt_sha256="0" * 64,
        model="deepseek/deepseek-v4-flash",
        raw_response={},
    )


def _make_evaluator(is_valid):
    def _evaluator(instrument_id, source, *, scenario, condition=None):
        valid = is_valid(source, scenario, condition or {})
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

    return _evaluator


_RANGE_EVALUATOR = _make_evaluator(lambda source, scenario, condition: "range(3)" in source)
_DRIFT_LOCKED_EVALUATOR = _make_evaluator(
    lambda source, scenario, condition: (
        "range(3)" in source and scenario is not SimulationScenario.DRIFT
    )
)


def _regressing_valid(source, scenario, condition):
    if "drift-fix" in source:
        return "historical" not in condition
    return "range(3)" in source and scenario is not SimulationScenario.DRIFT


_REGRESSING_EVALUATOR = _make_evaluator(_regressing_valid)


class FakeUsage:
    def __init__(self, total_tokens: int) -> None:
        self.total_tokens = total_tokens

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        del mode
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": 0,
            "completion_tokens": self.total_tokens,
        }


class FakeMessage:
    def __init__(self, calls, *, content=None) -> None:
        self.content = content
        self.reasoning_content = "preserved reasoning"
        self.tool_calls = [
            SimpleNamespace(
                id=f"call-{index}",
                function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
            )
            for index, (name, arguments) in enumerate(calls)
        ]

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
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
    def __init__(self, message: FakeMessage, *, total_tokens: int = 10) -> None:
        self.choices = [SimpleNamespace(message=message)]
        self.usage = FakeUsage(total_tokens)

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
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
    base_url = "http://localhost/v1"
    provider = ""

    def __init__(self, turns, *, total_tokens: int = 10) -> None:
        self.turns = iter(turns)
        self.total_tokens = total_tokens
        self.call_count = 0

    def create_chat_completion(self, **kwargs) -> FakeResponse:
        assert kwargs["tools"]
        self.call_count += 1
        return FakeResponse(FakeMessage(next(self.turns)), total_tokens=self.total_tokens)

    def close(self) -> None:
        return None


def _install_client(monkeypatch, turns, *, total_tokens: int = 10) -> None:
    def factory() -> FakeClient:
        return FakeClient(turns, total_tokens=total_tokens)

    monkeypatch.setattr("proprio.cross_family.OpenAICompatibleClient", factory)


def _submit_args(skill_py: str, evidence: str, *, verdict: str = "ACCEPT") -> dict[str, Any]:
    return {
        "diagnosis": "single reading misses repeat precision",
        "evidence_refs": [evidence],
        "skill_md": SKILL_MD,
        "skill_py": skill_py,
        "expected_effect": "repeat the measurement",
        "risks": ["simulation only"],
        "self_judgment": {"verdict": verdict, "basis": [evidence]},
    }


def _truthful_ref() -> str:
    suite = evaluate_debug_suite(_candidate(), (CONDITION,), evaluator=_RANGE_EVALUATOR)
    return suite.conditions[0].failure_refs[0]


def test_cross_family_method_declares_search_and_persistence_contract() -> None:
    protocol = yaml.safe_load((ROOT / "src/proprio/data/method.yaml").read_text(encoding="utf-8"))
    budget = protocol["search"]
    assert budget["initial_drafts"] == 6
    assert budget["archive_survivors"] == 3
    assert budget["repair_rounds"] == 6
    assert budget["maximum_candidate_variants"] == 24
    assert budget["maximum_model_turns_per_repair"] == 16
    persistent = protocol["persistence"]
    assert persistent["one_context_per_trajectory"] is True
    assert persistent["context_byte_limit"] == 240000
    assert protocol["evaluation"]["seed_base"] == 2400000
    assert protocol["evaluation"]["sessions_per_family"] == 1
    assert protocol["promotion"]["model_self_judgment_can_promote"] is False


def test_cross_family_freeze_binds_current_bytes_and_verifies(tmp_path: Path) -> None:
    manifest = freeze_cross_family_method(tmp_path)
    assert manifest["status"] == "FROZEN_BEFORE_BINDING_PANEL"
    assert manifest["schema_version"] == "proprio.cross_family_method_freeze.v0.4"
    assert "src/proprio/agent.py" in manifest["inputs"]
    assert "src/proprio/cross_family.py" in manifest["inputs"]
    assert "src/proprio/data/method.yaml" in manifest["inputs"]
    for dependency in ("artifacts.py", "catalog.py", "instrument_types.py", "schema.py"):
        assert f"src/proprio/{dependency}" in manifest["inputs"]
    assert (
        manifest["qualification_evidence_root"] == "artifacts/evidence/cross-family/qualification"
    )
    verification = verify_cross_family_method(tmp_path / "manifest.json")
    assert verification["verdict"] == "PASS"
    on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["method_sha256"] == manifest["method_sha256"]


def test_session_refuses_when_freeze_verification_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "proprio.cross_family.verify_cross_family_method", lambda _path: {"verdict": "FAIL"}
    )
    with pytest.raises(RuntimeError):
        run_cross_family_session(
            "helao-gamry-cv",
            tmp_path,
            freeze_path=tmp_path / "freeze.json",
        )


def test_trajectory_candidate_summary_carries_context_and_ledger_metrics(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setattr(
        "proprio.cross_family.load_external_source",
        lambda _instrument_id: (_SOURCE, _SOURCE_HASH),
    )
    monkeypatch.setattr("proprio.cross_family.evaluate_external_skill", _RANGE_EVALUATOR)
    evidence = _truthful_ref()
    _install_client(
        monkeypatch,
        [
            [("submit_repair", _submit_args(REPAIRED, evidence))],
            [("finish_candidate", {"status": "CANDIDATE", "summary": "admit"})],
        ],
    )
    result = run_persistent_repair_trajectory(
        _candidate(),
        definition=None,
        conditions=(CONDITION,),
        locked_conditions=(CONDITION,),
        feedback_arm=FeedbackArm.TRUTHFUL,
        seed=2_400_007,
        output_dir=tmp_path,
        verifier_cycles=4,
        model_call_budget=64,
        token_budget=600_000,
        compaction_byte_limit=240_000,
    )
    assert result["qualified"] is True
    assert result["agent_status"] == "CANDIDATE"
    assert result["visible_verdict"] == "ADMIT"
    assert result["locked_verdict"] == "ADMIT"
    assert result["repair_ledger"][-1]["outcome"] == "CANDIDATE"
    assert result["duplicate_candidate_count"] == 0
    assert result["repeated_failed_strategy_count"] == 0
    assert result["context_bytes_final"] > 0
    assert result["context_bytes_by_cycle"]
    assert result["parent_sha256"] == hashlib.sha256(INITIAL.encode()).hexdigest()
    assert result["final_sha256"] == hashlib.sha256((REPAIRED.rstrip() + "\n").encode()).hexdigest()
    assert result["candidate_chain_sha256"][0] == result["parent_sha256"]
    assert result["model_call_efficiency"] == 1.0 / result["consumed_model_calls"]
    progress = capsys.readouterr().err
    assert "[proprio] provider-call turn=1 attempt=1" in progress
    assert "[proprio] tool-result tool=submit_repair status=captured terminal=True" in progress
    assert "[proprio] agent-finish instrument=simulated-fixture status=CANDIDATE" in progress


def test_trajectory_budget_exhaustion_is_not_qualified(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "proprio.cross_family.load_external_source",
        lambda _instrument_id: (_SOURCE, _SOURCE_HASH),
    )
    monkeypatch.setattr("proprio.cross_family.evaluate_external_skill", _RANGE_EVALUATOR)
    _install_client(monkeypatch, [[("read_current_skill", {})]])
    result = run_persistent_repair_trajectory(
        _candidate(),
        definition=None,
        conditions=(CONDITION,),
        locked_conditions=(CONDITION,),
        feedback_arm=FeedbackArm.TRUTHFUL,
        seed=2_400_007,
        output_dir=tmp_path,
        verifier_cycles=4,
        model_call_budget=1,
        token_budget=600_000,
        compaction_byte_limit=240_000,
    )
    assert result["agent_status"] == "BUDGET_EXHAUSTED"
    assert result["qualified"] is False


def test_trajectory_locked_failure_prevents_qualification(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "proprio.cross_family.load_external_source",
        lambda _instrument_id: (_SOURCE, _SOURCE_HASH),
    )
    monkeypatch.setattr("proprio.cross_family.evaluate_external_skill", _DRIFT_LOCKED_EVALUATOR)
    evidence = _truthful_ref()
    _install_client(
        monkeypatch,
        [
            [("submit_repair", _submit_args(REPAIRED, evidence))],
            [("finish_candidate", {"status": "CANDIDATE", "summary": "admit"})],
        ],
    )
    result = run_persistent_repair_trajectory(
        _candidate(),
        definition=None,
        conditions=(CONDITION,),
        locked_conditions=(DRIFT_CONDITION,),
        feedback_arm=FeedbackArm.TRUTHFUL,
        seed=2_400_007,
        output_dir=tmp_path,
        verifier_cycles=4,
        model_call_budget=64,
        token_budget=600_000,
        compaction_byte_limit=240_000,
    )
    assert result["agent_status"] == "CANDIDATE"
    assert result["visible_verdict"] == "ADMIT"
    assert result["locked_verdict"] == "REJECT"
    assert result["qualified"] is False


def test_trajectory_duplicate_and_self_accept_cannot_admit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "proprio.cross_family.load_external_source",
        lambda _instrument_id: (_SOURCE, _SOURCE_HASH),
    )
    monkeypatch.setattr("proprio.cross_family.evaluate_external_skill", _RANGE_EVALUATOR)
    evidence = _truthful_ref()
    _install_client(
        monkeypatch,
        [
            [("submit_repair", _submit_args(FAIL_ONE, evidence, verdict="ACCEPT"))],
            [("submit_repair", _submit_args(FAIL_ONE, evidence, verdict="ACCEPT"))],
            [("finish_candidate", {"status": "CANDIDATE", "summary": "self-accepted"})],
            [("finish_candidate", {"status": "HOLD", "summary": "honest hold"})],
        ],
    )
    result = run_persistent_repair_trajectory(
        _candidate(),
        definition=None,
        conditions=(CONDITION,),
        locked_conditions=(CONDITION,),
        feedback_arm=FeedbackArm.TRUTHFUL,
        seed=2_400_007,
        output_dir=tmp_path,
        verifier_cycles=4,
        model_call_budget=64,
        token_budget=600_000,
        compaction_byte_limit=240_000,
    )
    assert result["agent_status"] == "HOLD"
    assert result["qualified"] is False
    assert result["visible_verdict"] == "REJECT"
    assert result["duplicate_candidate_count"] == 1
    outcomes = [entry["outcome"] for entry in result["repair_ledger"]]
    assert "REJECT" in outcomes
    assert "DUPLICATE" in outcomes
    resumed = resume_agent_state(tmp_path)
    blob = json.dumps(list(resumed.messages))
    assert "duplicate candidate hash" in blob
    assert "admitting replay" in blob


def test_resume_of_completed_trajectory_returns_cache_without_client(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "proprio.cross_family.load_external_source",
        lambda _instrument_id: (_SOURCE, _SOURCE_HASH),
    )
    monkeypatch.setattr("proprio.cross_family.evaluate_external_skill", _RANGE_EVALUATOR)
    evidence = _truthful_ref()
    _install_client(
        monkeypatch,
        [
            [("submit_repair", _submit_args(REPAIRED, evidence))],
            [("finish_candidate", {"status": "CANDIDATE", "summary": "admit"})],
        ],
    )
    first = run_persistent_repair_trajectory(
        _candidate(),
        definition=None,
        conditions=(CONDITION,),
        locked_conditions=(CONDITION,),
        feedback_arm=FeedbackArm.TRUTHFUL,
        seed=2_400_007,
        output_dir=tmp_path,
        verifier_cycles=4,
        model_call_budget=64,
        token_budget=600_000,
        compaction_byte_limit=240_000,
    )

    class _RaisingClient:
        def __init__(self) -> None:
            raise AssertionError("client constructed on a completed trajectory resume")

    monkeypatch.setattr("proprio.cross_family.OpenAICompatibleClient", _RaisingClient)
    again = run_persistent_repair_trajectory(
        _candidate(),
        definition=None,
        conditions=(CONDITION,),
        locked_conditions=(CONDITION,),
        feedback_arm=FeedbackArm.TRUTHFUL,
        seed=2_400_007,
        output_dir=tmp_path,
        verifier_cycles=4,
        model_call_budget=64,
        token_budget=600_000,
        compaction_byte_limit=240_000,
    )
    assert again == first


def test_causal_arms_share_prefix_and_isolate_post_branch(monkeypatch, tmp_path: Path) -> None:
    parent = _candidate()
    definition = SimpleNamespace(
        instrument_id="simulated-fixture",
        visible_conditions=(CONDITION,),
        locked_conditions=(CONDITION,),
        acquisition_conditions=(CONDITION,),
    )
    monkeypatch.setattr(
        "proprio.cross_family.load_external_source",
        lambda _instrument_id: (_SOURCE, _SOURCE_HASH),
    )
    monkeypatch.setattr("proprio.cross_family.evaluate_external_skill", _RANGE_EVALUATOR)
    monkeypatch.setattr(
        "proprio.cross_family._select_causal_parent",
        lambda _search, _instrument_id: parent,
    )
    truthful_ref = _truthful_ref()
    _install_client(
        monkeypatch,
        [
            [("submit_repair", _submit_args(FAIL_ONE, truthful_ref))],
            [("finish_candidate", {"status": "HOLD", "summary": "truthful hold"})],
            [("submit_repair", _submit_args(FAIL_ONE, "feedback:withheld"))],
            [("finish_candidate", {"status": "HOLD", "summary": "none hold"})],
        ],
    )
    result = run_persistent_causal_pair(
        None,
        definition=definition,
        seed=2_407_000,
        output_dir=tmp_path,
        compaction_byte_limit=240_000,
    )
    assert result["status"] == "ELIGIBLE"
    assert result["same_parent"] is True
    assert result["shared_prefix_sha256"] is not None

    truthful_state = resume_agent_state(tmp_path / "truthful")
    none_state = resume_agent_state(tmp_path / "none")
    assert truthful_state is not None
    assert none_state is not None
    assert truthful_state.messages[:2] == none_state.messages[:2]
    prefix_hash = hashlib.sha256(canonical_json(list(truthful_state.messages[:2]))).hexdigest()
    assert result["shared_prefix_sha256"] == prefix_hash

    truthful_blob = json.dumps(list(truthful_state.messages))
    none_blob = json.dumps(list(none_state.messages))
    assert "repeat-precision" in truthful_blob
    assert truthful_ref in truthful_blob
    assert "repeat-precision" not in none_blob
    assert truthful_ref not in none_blob
    assert "feedback:withheld" in none_blob


def test_historical_regression_prevents_evolution_staged(monkeypatch, tmp_path: Path) -> None:
    definition = SimpleNamespace(
        instrument_id="simulated-fixture",
        visible_conditions=(CONDITION,),
        locked_conditions=(DRIFT_CONDITION,),
        acquisition_conditions=(
            DebugCondition(
                condition_id="historical-acquire",
                scenario=SimulationScenario.NOMINAL,
                parameters=(("historical", 1.0),),
                repetitions=1,
            ),
        ),
        evolution_conditions=(
            DebugCondition(
                condition_id="deployment-drift",
                scenario=SimulationScenario.DRIFT,
                repetitions=1,
            ),
        ),
    )
    monkeypatch.setattr("proprio.cross_family.evaluate_external_skill", _REGRESSING_EVALUATOR)
    proposal = _candidate(DRIFT_FIX)
    monkeypatch.setattr(
        "proprio.cross_family.run_persistent_repair_trajectory",
        lambda *args, **kwargs: {
            "qualified": True,
            "locked_verdict": "ADMIT",
            "final_candidate": proposal.model_dump(mode="json"),
        },
    )
    result = run_persistent_evolution_proposal(
        _candidate(REPAIRED),
        definition=definition,
        seed=2_408_000,
        output_dir=tmp_path,
    )
    assert result["drift_detected"] is True
    assert result["acquisition_verdict"] == "REJECT"
    assert result["evolution_verdict"] == "ADMIT"
    assert result["status"] == "REJECTED"


def _fake_search(instrument_id: str, source_hash: str) -> SearchReport:
    candidate = CandidatePackage(
        instrument_id=instrument_id,
        skill_md=SKILL_MD,
        skill_py="def run(controller):\n    return {}\n",
        self_judgment={"verdict": "ACCEPT", "basis": []},
        source_sha256=source_hash,
        prompt_sha256="prompt",
        model="deepseek/deepseek-v4-flash",
        raw_response={},
    )
    suite = DebugSuiteResult(
        instrument_id=instrument_id,
        candidate_sha256="candidate",
        conditions=(),
        verdict="ADMIT",
    )
    return SearchReport(
        instrument_id=instrument_id,
        entries=(),
        repairs=(),
        selected=candidate,
        selected_suite=suite,
        initial_width=6,
        survivor_count=3,
        repair_rounds=6,
        model_candidates_generated=6,
        verdict="CANDIDATE",
    )


def test_session_summary_reports_full_evaluation_matrix(monkeypatch, tmp_path: Path) -> None:
    instrument_id = "helao-gamry-cv"
    _, source_hash = load_external_source(instrument_id)
    search = _fake_search(instrument_id, source_hash)
    admit_suite = DebugSuiteResult(
        instrument_id=instrument_id,
        candidate_sha256="candidate",
        conditions=(),
        verdict="ADMIT",
    )

    monkeypatch.setattr(
        "proprio.cross_family.verify_cross_family_method", lambda _path: {"verdict": "PASS"}
    )
    monkeypatch.setattr(
        "proprio.cross_family._read_json", lambda _path: {"method_sha256": "method"}
    )
    monkeypatch.setattr(
        "proprio.cross_family.run_external_preflight",
        lambda _instrument_id: FixturePreflightReport(cases=(), verdict="PASS"),
    )
    monkeypatch.setattr("proprio.cross_family.run_archive_search", lambda *args, **kwargs: search)

    def locked_after_seal(*args, **kwargs):
        assert (tmp_path / "selection-seal.json").is_file()
        return admit_suite

    monkeypatch.setattr("proprio.cross_family.evaluate_debug_suite", locked_after_seal)
    monkeypatch.setattr(
        "proprio.cross_family.run_persistent_causal_pair",
        lambda *args, **kwargs: {
            "status": "ELIGIBLE",
            "shared_prefix_sha256": "abc",
            "truthful_repair_regressed": False,
            "truthful_historical_verdict": "ADMIT",
            "outcomes": {
                "truthful": {
                    "qualified": True,
                    "consumed_model_calls": 5,
                    "consumed_tokens": 1000,
                    "repeated_failed_strategy_count": 0,
                    "duplicate_candidate_count": 0,
                    "compaction_applied": False,
                    "context_bytes_by_cycle": [10, 20],
                },
                "none": {
                    "qualified": False,
                    "consumed_model_calls": 4,
                    "consumed_tokens": 900,
                    "repeated_failed_strategy_count": 0,
                    "duplicate_candidate_count": 0,
                    "compaction_applied": False,
                    "context_bytes_by_cycle": [10, 20],
                },
            },
        },
    )
    monkeypatch.setattr(
        "proprio.cross_family.run_persistent_evolution_proposal",
        lambda *args, **kwargs: {
            "status": "STAGED",
            "drift_detected": True,
            "trajectory": {
                "qualified": True,
                "consumed_model_calls": 3,
                "consumed_tokens": 500,
                "repeated_failed_strategy_count": 0,
                "duplicate_candidate_count": 0,
                "compaction_applied": False,
            },
        },
    )
    monkeypatch.setattr(
        "proprio.cross_family._transport_evidence",
        lambda _path: {"verdict": "PASS", "total_cost_usd": 0.0},
    )

    summary = run_cross_family_session(
        instrument_id,
        tmp_path,
        session_index=0,
        freeze_path=tmp_path / "freeze.json",
        panel_manifest_sha256="panel",
    )
    assert summary["final_decision"] == "ADMIT"
    assert summary["verdict"] == "PASS"
    assert summary["invalid_promotion_count"] == 0
    assert summary["truthful_repair_qualified"] is True
    assert summary["none_repair_qualified"] is False
    assert summary["evolution_staged"] is True
    assert summary["historical_regression"] is False
    assert summary["shared_prefix_sha256"] == "abc"
    assert summary["model_calls_to_first_qualified"] == 5
    assert summary["tokens_to_first_qualified"] == 1000
    for key in (
        "initial_skill_executable",
        "initial_physical_validity",
        "locked_qualification",
        "drift_detected",
        "repeated_failed_strategy_count",
        "duplicate_candidate_count",
        "transport_valid",
        "qualification_per_model_call",
        "qualification_per_million_tokens",
        "total_cost_usd",
        "context_growth",
        "compactions_applied",
        "resume_idempotent",
    ):
        assert key in summary
    assert (tmp_path / "selection-seal.json").is_file()
    assert (tmp_path / "session-manifest.json").is_file()
