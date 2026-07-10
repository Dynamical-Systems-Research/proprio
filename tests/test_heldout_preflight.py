from pathlib import Path

from proprio.heldout_preflight import import_heldout_preflight_evidence

ROOT = Path(__file__).resolve().parents[1]


def test_heldout_panel_fails_closed_before_model_generation(tmp_path: Path) -> None:
    raw = ROOT / "artifacts/evidence/heldout-generalization/preflight/raw"
    summary = import_heldout_preflight_evidence(
        tmp_path,
        preregistration_path=(
            ROOT / "src/proprio/data/heldout-generalization-preregistration.yaml"
        ),
        evidence_paths=(
            raw / "octoprint-virtual-printer.json",
            raw / "pymodaq-mock-spectrometer.json",
            raw / "sinstruments-pace-pressure-controller.json",
        ),
    )
    assert summary["registered_families"] == 3
    assert summary["families_failing_preflight"] == 3
    assert summary["families_passing_preflight"] == 0
    assert summary["model_calls"] == 0
    assert summary["model_generation_performed"] is False
    assert summary["family_replacement_performed"] is False
    assert summary["aggregate_rescue_performed"] is False
    assert summary["verdict"] == "FAIL"
    assert all(row["honest_status"] == "HOLD" for row in summary["rows"])
