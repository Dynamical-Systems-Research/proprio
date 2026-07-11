import hashlib
from collections.abc import Mapping

from proprio.instrument_types import (
    CandidatePackage,
    GateCheck,
    HardGateResult,
    SimulationScenario,
)
from proprio.skill_search import (
    DebugCondition,
    PreflightCase,
    RepairOutcome,
    evaluate_debug_suite,
    make_search_entry,
    run_archive_search,
    run_fixture_preflight,
    select_archive,
)


def _candidate(source: str, *, model: str = "fixture") -> CandidatePackage:
    return CandidatePackage(
        instrument_id="simulated-fixture",
        skill_md="---\nname: simulated-fixture\ndescription: Test fixture.\n---\n# Run\nTest.\n",
        skill_py=source,
        self_judgment={"verdict": "ACCEPT", "basis": ["fixture"]},
        source_sha256="1" * 64,
        prompt_sha256="2" * 64,
        model=model,
        raw_response={},
    )


def _gate(
    source: str,
    *,
    scenario: SimulationScenario,
    condition: Mapping[str, float] | None,
) -> HardGateResult:
    values = dict(condition or {})
    unavailable = scenario is SimulationScenario.UNAVAILABLE
    valid = "good" in source and not values.get("force_invalid", 0.0)
    status = "unavailable" if unavailable else ("succeeded" if valid else "failed")
    verdict = "HOLD" if unavailable else ("ADMIT" if valid else "REJECT")
    checks = (
        GateCheck(check_id="runtime-completed", passed=not unavailable),
        GateCheck(check_id="physical-signal", passed=valid, evidence={"observed": valid}),
        GateCheck(check_id="resource-release", passed=not unavailable),
    )
    return HardGateResult(
        instrument_id="simulated-fixture",
        family="fixture",
        scenario=scenario,
        verdict=verdict,
        status=status,
        checks=checks,
        trace=({"operation": "measure"},),
        telemetry=values,
        result={},
        runtime_error="unavailable" if unavailable else None,
        skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
        simulator_sha256="3" * 64,
        verifier_sha256="4" * 64,
    )


def _evaluator(instrument_id: str, source: str, *, scenario, condition=None):
    assert instrument_id == "simulated-fixture"
    return _gate(source, scenario=scenario, condition=condition)


def _condition(
    condition_id: str,
    scenario: SimulationScenario,
    *,
    force_invalid: float = 0.0,
) -> DebugCondition:
    return DebugCondition(
        condition_id=condition_id,
        scenario=scenario,
        parameters=(("force_invalid", force_invalid),) if force_invalid else (),
        repetitions=3,
    )


def test_fixture_preflight_requires_valid_invalid_and_unavailable_controls() -> None:
    good = _candidate("def run(controller):\n    return {'good': True}\n")
    bad = _candidate("def run(controller):\n    return {'bad': True}\n")
    report = run_fixture_preflight(
        (
            PreflightCase(
                case_id="valid",
                candidate=good,
                condition=_condition("valid", SimulationScenario.NOMINAL),
                expected_verdict="ADMIT",
            ),
            PreflightCase(
                case_id="invalid",
                candidate=bad,
                condition=_condition("invalid", SimulationScenario.NOMINAL),
                expected_verdict="REJECT",
                required_failed_checks=("physical-signal",),
            ),
            PreflightCase(
                case_id="unavailable",
                candidate=good,
                condition=_condition("unavailable", SimulationScenario.UNAVAILABLE),
                expected_verdict="HOLD",
            ),
        ),
        evaluator=_evaluator,
    )
    assert report.verdict == "PASS"


def test_preflight_reject_control_cannot_pass_for_a_procedural_failure() -> None:
    good = _candidate("def run(controller):\n    return {'good': True}\n")
    bad = _candidate("def run(controller):\n    return {'bad': True}\n")

    def confounded(instrument_id: str, source: str, *, scenario, condition=None):
        result = _evaluator(instrument_id, source, scenario=scenario, condition=condition)
        if "bad" not in source:
            return result
        checks = tuple(
            GateCheck(check_id=check.check_id, passed=False)
            if check.check_id == "runtime-completed"
            else check
            for check in result.checks
        )
        return result.model_copy(update={"checks": checks})

    report = run_fixture_preflight(
        (
            PreflightCase(
                case_id="valid",
                candidate=good,
                condition=_condition("valid-isolation", SimulationScenario.NOMINAL),
                expected_verdict="ADMIT",
            ),
            PreflightCase(
                case_id="invalid",
                candidate=bad,
                condition=_condition("invalid-isolation", SimulationScenario.NOMINAL),
                expected_verdict="REJECT",
                required_failed_checks=("physical-signal",),
            ),
            PreflightCase(
                case_id="unavailable",
                candidate=good,
                condition=_condition("hold-isolation", SimulationScenario.UNAVAILABLE),
                expected_verdict="HOLD",
            ),
        ),
        evaluator=confounded,
    )
    assert report.verdict == "FAIL"
    assert next(row for row in report.cases if row.case_id == "invalid").passed is False


def test_repeated_multi_condition_suite_is_conjunctive() -> None:
    candidate = _candidate("def run(controller):\n    return {'good': True}\n")
    suite = evaluate_debug_suite(
        candidate,
        (
            _condition("nominal", SimulationScenario.NOMINAL),
            _condition("invalid", SimulationScenario.DRIFT, force_invalid=1.0),
        ),
        evaluator=_evaluator,
    )
    assert suite.verdict == "REJECT"
    assert suite.conditions[0].verdict == "ADMIT"
    assert suite.conditions[1].admitted_repetitions == 0
    assert all(ref.endswith("physical-signal") for ref in suite.conditions[1].failure_refs)


def test_archive_prefers_worst_condition_coverage_and_structural_diversity() -> None:
    good = _candidate("def run(controller):\n    value = 1\n    return {'good': value}\n")
    bad = _candidate("def run(controller):\n    return {'bad': True}\n")
    conditions = (_condition("nominal", SimulationScenario.NOMINAL),)
    good_entry = make_search_entry(
        good,
        evaluate_debug_suite(good, conditions, evaluator=_evaluator),
        generation=0,
        parent_sha256=None,
    )
    bad_entry = make_search_entry(
        bad,
        evaluate_debug_suite(bad, conditions, evaluator=_evaluator),
        generation=0,
        parent_sha256=None,
    )
    assert select_archive((bad_entry, good_entry), limit=1) == (good_entry,)


def test_archive_search_runs_preflight_then_repairs_selected_failures() -> None:
    good = _candidate("def run(controller):\n    return {'good': True}\n")
    bad = _candidate("def run(controller):\n    return {'bad': True}\n")
    preflight = run_fixture_preflight(
        (
            PreflightCase(
                case_id="valid",
                candidate=good,
                condition=_condition("pre-valid", SimulationScenario.NOMINAL),
                expected_verdict="ADMIT",
            ),
            PreflightCase(
                case_id="invalid",
                candidate=bad,
                condition=_condition("pre-invalid", SimulationScenario.NOMINAL),
                expected_verdict="REJECT",
            ),
            PreflightCase(
                case_id="unavailable",
                candidate=good,
                condition=_condition("pre-hold", SimulationScenario.UNAVAILABLE),
                expected_verdict="HOLD",
            ),
        ),
        evaluator=_evaluator,
    )
    draft_seeds: list[int] = []
    repair_refs: list[tuple[str, ...]] = []

    def draft(seed: int) -> CandidatePackage:
        draft_seeds.append(seed)
        return bad.model_copy(update={"prompt_sha256": f"{seed:064x}"})

    def repair(parent: CandidatePackage, suite, seed: int) -> RepairOutcome:
        del parent
        repair_refs.append(tuple(ref for row in suite.conditions for ref in row.failure_refs))
        return RepairOutcome(
            candidate=good.model_copy(update={"prompt_sha256": f"{seed:064x}"}),
            record={"seed": seed, "agent_status": "CANDIDATE"},
        )

    report = run_archive_search(
        "simulated-fixture",
        conditions=(_condition("debug", SimulationScenario.NOMINAL),),
        evaluator=_evaluator,
        draft=draft,
        repair=repair,
        preflight=preflight,
        seed_base=100,
    )
    assert sorted(draft_seeds) == [100, 101, 102, 103]
    assert report.verdict == "CANDIDATE"
    assert report.selected is not None
    assert "good" in report.selected.skill_py
    assert report.model_candidates_generated == 6
    assert len(repair_refs) == 2
    assert all(refs for refs in repair_refs)
    assert [row.record["seed"] for row in report.repairs] == [104, 105]


def test_archive_cannot_promote_held_repair_even_if_replay_admits() -> None:
    good = _candidate("def run(controller):\n    return {'good': True}\n")
    bad = _candidate("def run(controller):\n    return {'bad': True}\n")
    preflight = run_fixture_preflight(
        (
            PreflightCase(
                case_id="valid",
                candidate=good,
                condition=_condition("pre-valid-held", SimulationScenario.NOMINAL),
                expected_verdict="ADMIT",
            ),
            PreflightCase(
                case_id="invalid",
                candidate=bad,
                condition=_condition("pre-invalid-held", SimulationScenario.NOMINAL),
                expected_verdict="REJECT",
            ),
            PreflightCase(
                case_id="unavailable",
                candidate=good,
                condition=_condition("pre-hold-held", SimulationScenario.UNAVAILABLE),
                expected_verdict="HOLD",
            ),
        ),
        evaluator=_evaluator,
    )

    def repair(parent: CandidatePackage, suite, seed: int) -> RepairOutcome:
        del parent, suite, seed
        return RepairOutcome(candidate=good, record={"agent_status": "HOLD"})

    report = run_archive_search(
        "simulated-fixture",
        conditions=(_condition("held-debug", SimulationScenario.NOMINAL),),
        evaluator=_evaluator,
        draft=lambda seed: bad.model_copy(update={"prompt_sha256": f"{seed:064x}"}),
        repair=repair,
        preflight=preflight,
        seed_base=200,
        repair_rounds=1,
    )
    assert report.verdict == "HOLD"
    assert report.selected is None
    held = [entry for entry in report.entries if entry.generation == 1]
    assert all(entry.suite.verdict == "ADMIT" for entry in held)
    assert all(not entry.promotion_eligible for entry in held)
    assert all(entry.promotion_blockers == ("agent-status:HOLD",) for entry in held)
