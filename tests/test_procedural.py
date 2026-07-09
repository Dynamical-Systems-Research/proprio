from __future__ import annotations

import json

import pytest

from proprio.procedural import ProceduralFault, run_fault_battery, run_procedural
from proprio.schema import StatusLabel


def test_happy_path_succeeds_and_emits_complete_run() -> None:
    execution = run_procedural()
    assert execution.detected
    assert execution.record.status is StatusLabel.SUCCEEDED
    stop = [row["doc"] for row in execution.raw_documents if row["name"] == "stop"][-1]
    assert stop["exit_status"] == "success"


@pytest.mark.parametrize("fault", [fault for fault in ProceduralFault if fault.value != "none"])
def test_each_fault_is_detected(fault: ProceduralFault) -> None:
    execution = run_procedural(fault=fault)
    assert execution.detected
    assert execution.record.status is not StatusLabel.SUCCEEDED


def test_truncated_frame_is_degraded_despite_successful_runengine_stop() -> None:
    execution = run_procedural(fault=ProceduralFault.DROPPED_FRAME)
    assert execution.record.status is StatusLabel.DEGRADED
    stop = [row["doc"] for row in execution.raw_documents if row["name"] == "stop"][-1]
    assert stop["exit_status"] == "success"
    frame_check = next(
        check for check in execution.record.checks if check.check_id == "frame-shape"
    )
    assert frame_check.status is StatusLabel.FAILED


def test_fault_battery_reports_each_class(tmp_path) -> None:
    report = run_fault_battery(tmp_path)
    assert report["all_detected"]
    assert report["verdict"] == "PASS"
    assert {row["fault_class"] for row in report["results"]} == {
        fault.value for fault in ProceduralFault
    }
    for row in report["results"]:
        raw = row["raw_event_stream"]
        assert raw is not None
        assert json.loads(
            (tmp_path / f"{row['fault_class']}.raw.jsonl").read_text().splitlines()[0]
        )
