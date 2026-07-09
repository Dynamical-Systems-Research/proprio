from __future__ import annotations

import json

from proprio.reference_xrd import run_composition_battery, run_reference_xrd


def test_canonical_record_is_byte_identical_across_raw_runs(tmp_path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_reference_xrd(output_dir=first)
    run_reference_xrd(output_dir=second)
    assert (first / "self-observation.json").read_bytes() == (
        second / "self-observation.json"
    ).read_bytes()
    first_binding = json.loads((first / "raw/binding.json").read_text())
    second_binding = json.loads((second / "raw/binding.json").read_text())
    assert first_binding["canonical_record_id"] == second_binding["canonical_record_id"]
    assert first_binding["raw_start_uid"] != second_binding["raw_start_uid"]


def test_reset_is_idempotent(tmp_path) -> None:
    output = tmp_path / "same"
    first = run_reference_xrd(output_dir=output)
    first_bytes = (output / "self-observation.json").read_bytes()
    second = run_reference_xrd(output_dir=output)
    assert first["record_id"] == second["record_id"]
    assert first_bytes == (output / "self-observation.json").read_bytes()


def test_composition_catches_procedural_success_invalid_measurement(tmp_path) -> None:
    summary = run_composition_battery(tmp_path)
    assert summary["verdict"] == "PASS"
    assert summary["procedural_success_invalid_caught"]
