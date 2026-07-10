import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_heldout_panel_is_complete_and_bound_to_frozen_method() -> None:
    preregistration = yaml.safe_load(
        (ROOT / "src/proprio/data/heldout-generalization-preregistration.yaml").read_text(
            encoding="utf-8"
        )
    )
    freeze = json.loads(
        (ROOT / "artifacts/generated/adaptive-method-freeze/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert preregistration["study_status"] == (
        "preregistered_before_simulator_clone_import_or_execution"
    )
    assert preregistration["frozen_method"]["method_sha256"] == freeze["method_sha256"]
    families = preregistration["families"]
    assert len(families) == 3
    assert len({family["family_id"] for family in families}) == 3
    assert len({family["upstream"]["repository"] for family in families}) == 3
    assert all(len(family["generator_seeds"]) == 20 for family in families)
    assert all(len(set(family["generator_seeds"])) == 20 for family in families)
    assert all(len(family["drift_seeds"]) == 20 for family in families)
    assert all(len(family["failure_classes"]) == 8 for family in families)
    assert preregistration["binding_analysis"]["failed_family_replacement"] == "prohibited"
    assert preregistration["binding_analysis"]["aggregate_rescue"] == "prohibited"
