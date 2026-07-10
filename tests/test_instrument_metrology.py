from pathlib import Path

from proprio.instrument_metrology import FAILURE_CLASSES, run_instrument_metrology
from proprio.reference_instruments import INSTRUMENTS


def test_instrument_metrology_measures_each_family_and_failure_class(tmp_path: Path) -> None:
    summary = run_instrument_metrology(tmp_path, cases_per_class=5)
    assert summary["verdict"] == "PASS"
    assert summary["false_admit"] == 0
    assert summary["false_reject"] == 0
    assert set(summary["instruments"]) == set(INSTRUMENTS)
    for instrument in summary["instruments"].values():
        assert set(instrument["invalid"]) == set(FAILURE_CLASSES)
        assert all(item["cases"] == 5 for item in instrument["invalid"].values())


def test_instrument_metrology_replay_is_byte_deterministic(tmp_path: Path) -> None:
    output = tmp_path / "battery"
    run_instrument_metrology(output, cases_per_class=3)
    first = (output / "cases.jsonl").read_bytes()
    run_instrument_metrology(output, cases_per_class=3)
    assert first == (output / "cases.jsonl").read_bytes()
