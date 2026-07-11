from __future__ import annotations

import json
from pathlib import Path

import yaml

from proprio.generalization_method import freeze_generalization_method, verify_generalization_method

ROOT = Path(__file__).resolve().parents[1]


def test_v03_method_budget_is_generous_and_uniform() -> None:
    protocol = yaml.safe_load(
        (ROOT / "src/proprio/data/generalization-v0.3-method.yaml").read_text()
    )
    budget = protocol["search_budget_per_session"]
    assert budget["initial_drafts"] == 6
    assert budget["archive_survivors"] == 3
    assert budget["repair_rounds"] == 6
    assert budget["maximum_candidate_variants"] == 24
    assert budget["maximum_model_turns_per_repair"] == 16
    assert protocol["study"]["independent_sessions_per_family"] == 30
    assert protocol["promotion"]["model_self_judgment_can_promote"] is False


def test_v03_method_freeze_binds_passing_evidence(tmp_path: Path) -> None:
    manifest = freeze_generalization_method(tmp_path)
    assert manifest["status"] == "FROZEN_BEFORE_BINDING_PANEL"
    assert len(manifest["selected_instruments"]) == 3
    assert all(row["metrology"]["total_false_admits"] == 0 for row in manifest["evidence"].values())
    verification = verify_generalization_method(tmp_path / "manifest.json")
    assert verification["verdict"] == "PASS"
    on_disk = json.loads((tmp_path / "manifest.json").read_text())
    assert on_disk["method_sha256"] == manifest["method_sha256"]
