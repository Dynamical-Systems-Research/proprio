from __future__ import annotations

from dataclasses import replace

import numpy as np

from proprio.schema import StatusLabel
from proprio.support import DistributionSupportHook, SubstrateSupportDetector, run_support_battery
from proprio.xrd_generator import generate_calibrant_frame


def test_substrate_detector_implements_future_hook() -> None:
    detector = SubstrateSupportDetector()
    assert isinstance(detector, DistributionSupportHook)


def test_valid_substrate_frame_is_supported() -> None:
    case = generate_calibrant_frame(seed=3)
    record = SubstrateSupportDetector().evaluate(case, calibrant="lab6")
    assert record.status is StatusLabel.SUCCEEDED


def test_corrupted_frame_is_out_of_support() -> None:
    case = generate_calibrant_frame(seed=3)
    frame = case.frame.copy()
    frame[0, 0] = np.nan
    record = SubstrateSupportDetector().evaluate(replace(case, frame=frame), calibrant="lab6")
    assert record.status is StatusLabel.FAILED
    assert "finite-input" in {
        check.check_id for check in record.checks if check.status is StatusLabel.FAILED
    }


def test_support_battery_closes_detection_and_false_alarm_bars(tmp_path) -> None:
    summary = run_support_battery(tmp_path)
    assert summary["verdict"] == "PASS"
    assert summary["detection_rate"] >= 0.90
    assert summary["false_alarm_rate"] <= 0.10
