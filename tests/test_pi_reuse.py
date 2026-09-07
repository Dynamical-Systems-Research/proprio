"""Real simulator regressions for the study's trace-derived result adapter."""

import hashlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from proprio import instrument_qualification
from proprio.flake_search_simulator import FlakeSearchController
from proprio.instrument_plugins import instrument_registry
from proprio.instrument_types import SimulationScenario

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.pi_reuse import runtime as behavioral

# Same documented nominal mechanics as the existing provider regression fixture.
# This is test code, never supplied to study agents.
GOOD = """def run(controller):
    controller.reset()
    controller.read_chip_state()
    controller.calibrate_region()
    for row in range(4):
        controller.autofocus()
        for col in range(4):
            controller.move_to_tile(col, row)
            controller.capture_tile()
    controller.read_chip_state()
    for index in range(12):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(0)
    controller.release()
"""
CASES = [{"parameters": {"seed": 321785}}]


def grade(code=GOOD, cases=CASES):
    return behavioral.evaluate(code, cases)[0]


def test_no_return_is_admitted_and_source_and_compiler_are_preserved():
    compiler = instrument_qualification.compile_instrument_skill
    gate = grade()
    assert gate["verdict"] == "ADMIT", gate
    assert gate["result"] == {"status_code": 0}
    assert gate["skill_sha256"] == hashlib.sha256(GOOD.encode()).hexdigest()
    assert instrument_qualification.compile_instrument_skill is compiler
    legacy = (
        instrument_registry(behavioral.INSTRUMENT)
        .evaluate(
            behavioral.INSTRUMENT,
            GOOD,
            scenario=SimulationScenario.NOMINAL,
            condition=CASES[0]["parameters"],
        )
        .model_dump(mode="json")
    )
    assert legacy["verdict"] == "REJECT"
    assert "run must return a dictionary" in legacy["runtime_error"]


def test_optional_return_is_not_a_second_result_authority():
    gate = grade(GOOD + '    return {"status_code": 3}\n')
    assert gate["verdict"] == "ADMIT"
    assert gate["result"] == {"status_code": 0}


@pytest.mark.parametrize(
    "source,error",
    [
        (
            GOOD.replace("    controller.complete_scan(0)\n    controller.release()\n", ""),
            "exactly one complete_scan",
        ),
        (GOOD + "    controller.complete_scan(0)\n", "complete_scan already called"),
        (GOOD.replace("complete_scan(0)", "complete_scan(99)"), "unsupported status_code"),
        (GOOD + "    x = 1 / 0\n", "ZeroDivisionError"),
        (GOOD + "    return 1 / 0\n", "ZeroDivisionError"),
    ],
)
def test_missing_duplicate_invalid_completion_and_runtime_errors_remain_failures(source, error):
    gate = grade(source)
    assert gate["verdict"] == "REJECT"
    assert error in gate["runtime_error"]


def test_release_and_fault_checks_are_not_bypassed():
    no_release = grade(GOOD.replace("    controller.release()\n", ""))
    assert no_release["verdict"] == "REJECT"
    assert any(
        c["check_id"] == "resource-release" and not c["passed"] for c in no_release["checks"]
    )
    bad_light = grade(cases=[{"parameters": {"seed": 321785, "illumination_shift": 0.85}}])
    assert bad_light["verdict"] == "REJECT"
    assert bad_light["result"] == {"status_code": 0}
    assert not behavioral.outcome(bad_light, 3)["passed"]


def test_completion_disagreement_with_telemetry_rejects():
    original = FlakeSearchController.telemetry

    def inconsistent(controller):
        telemetry = original(controller)
        telemetry["status_code"] = 3
        return telemetry

    with patch.object(FlakeSearchController, "telemetry", inconsistent):
        gate = grade()
    assert gate["verdict"] == "REJECT"
    assert "agreeing with telemetry" in gate["runtime_error"]


def test_wrong_expected_stop_cannot_count_as_honest_completion():
    gate = grade()
    outcome = behavioral.outcome(gate, 3)
    assert not outcome["passed"]
    assert outcome["invalid_completed_operation"]


def test_static_safety_is_unchanged():
    gate = grade("def run(controller):\n    import os\n")
    assert gate["verdict"] == "REJECT"
    assert gate["checks"][0]["check_id"] == "static-safety"
    assert gate["trace"] == []


def test_incomplete_smoke_has_valid_result_but_fails_behavior():
    gate = grade(
        "def run(controller):\n    controller.reset()\n"
        "    controller.complete_scan(4)\n    controller.release()\n"
    )
    assert gate["runtime_error"] is None
    assert gate["result"] == {"status_code": 4}
    assert gate["verdict"] == "REJECT"
    assert not behavioral.outcome(gate, 0)["passed"]


def test_published_comparison_replays_all_cases():
    from research.pi_reuse.replay import DEFAULT, replay

    result = replay(DEFAULT)
    assert result["successful_consumers"] == {"before": 4, "after": 6}


def test_replay_rejects_rebound_consumer_even_with_updated_bundle_manifest(tmp_path):
    import json
    import shutil

    from proprio.artifacts import file_sha256, write_canonical_json
    from research.pi_reuse.replay import DEFAULT, replay

    evidence = tmp_path / "evidence"
    shutil.copytree(DEFAULT, evidence)
    relative = "consumers/consumer-1-before-1.py"
    (evidence / relative).write_text("def run(controller):\n    return\n")
    manifest = json.loads((evidence / "manifest.json").read_text())
    manifest["files"][relative] = file_sha256(evidence / relative)
    write_canonical_json(evidence / "manifest.json", manifest)
    with pytest.raises(ValueError, match="Consumer identity differs"):
        replay(evidence)
