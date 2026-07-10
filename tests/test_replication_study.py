import pytest

from proprio.replication_study import (
    INSTRUMENT_IDS,
    initial_execution_succeeded,
    microscopy_locked_conditions,
    replication_seed,
    select_replication_ids,
)


def test_replication_seed_is_panel_global_and_unique() -> None:
    seeds = {
        replication_seed(instrument_id, replicate, seed_base=740900)
        for instrument_id in INSTRUMENT_IDS
        for replicate in range(10)
    }
    assert len(seeds) == len(INSTRUMENT_IDS) * 10
    assert replication_seed(INSTRUMENT_IDS[1], 0, seed_base=740900) == 741000


def test_microscopy_locked_conditions_are_deterministic_and_in_range() -> None:
    first = microscopy_locked_conditions(10)
    assert first == microscopy_locked_conditions(10)
    assert len({row["condition_id"] for row in first}) == 10
    assert all(1100.0 <= row["start_z"] <= 1400.0 for row in first)


def test_replication_shards_preserve_frozen_panel_indices() -> None:
    assert select_replication_ids((1, 4, 9), count=10) == (1, 4, 9)
    assert select_replication_ids(None, count=3) == (0, 1, 2)
    with pytest.raises(ValueError, match="unique"):
        select_replication_ids((1, 1), count=10)
    with pytest.raises(ValueError, match="inside"):
        select_replication_ids((10,), count=10)


def test_initial_execution_is_separate_from_measurement_admission() -> None:
    gate = {
        "status": "failed",
        "verdict": "REJECT",
        "runtime_error": None,
        "checks": [
            {"check_id": "static-safety", "passed": True},
            {"check_id": "runtime-completed", "passed": True},
            {"check_id": "fft-focus-improvement", "passed": False},
        ],
    }
    assert initial_execution_succeeded(gate) is True
    gate["checks"][1]["passed"] = False
    assert initial_execution_succeeded(gate) is False
