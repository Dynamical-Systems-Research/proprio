from __future__ import annotations

import json

from proprio.metrology import run_metrology


def test_metrology_smoke_persists_per_class_evidence(tmp_path) -> None:
    summary = run_metrology(output_dir=tmp_path, cases_per_class=2)
    assert summary["verdict"] == "FAIL"  # Full N=300 sample-size bar is intentionally unmet.
    assert summary["cases_per_class_requested"] == 2
    assert all(row["false_valid"] == 0 for row in summary["invalid_classes"].values())
    assert (tmp_path / "scored_cases.jsonl").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "roc.json").exists()
    manifest = json.loads((tmp_path / "artifact-manifest.json").read_text())
    assert manifest["artifacts"]
