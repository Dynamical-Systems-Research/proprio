import hashlib
import json
from pathlib import Path

import pytest

from proprio.method_freeze import (
    CAUSAL_DEVELOPMENT_EVIDENCE,
    REQUIRED_EVIDENCE,
    freeze_adaptive_method,
    verify_adaptive_method_freeze,
)


def write_evidence(root: Path, *, verdict: str = "PASS", repairs=None) -> None:
    for relative in REQUIRED_EVIDENCE.values():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema_version": "fixture", "verdict": verdict}),
            encoding="utf-8",
        )
    causal = root / CAUSAL_DEVELOPMENT_EVIDENCE
    causal.parent.mkdir(parents=True, exist_ok=True)
    causal.write_text(
        json.dumps(
            {
                "schema_version": "proprio.causal_development_lock.v0.2",
                "status": "EXPLORATORY_LOCKED",
                "confirmatory_status": "NOT_ESTABLISHED",
                "completed_trials": 4,
                "registered_trials": 30,
                "analysis": {"verdict": "INCOMPLETE"},
            }
        ),
        encoding="utf-8",
    )
    search = root / "adaptive-microscopy-development-v2/search.json"
    skill = "def run(controller):\n    return {'ok': True}\n"
    skill_sha = hashlib.sha256(skill.encode()).hexdigest()
    repair_rows = (
        [
            {
                "record": {
                    "agent_status": "CANDIDATE",
                    "initial_suite": {"verdict": "REJECT"},
                    "final_suite": {"verdict": "ADMIT"},
                }
            }
        ]
        if repairs is None
        else repairs
    )
    search.write_text(
        json.dumps(
            {
                "schema_version": "fixture",
                "verdict": "CANDIDATE",
                "selected": {"skill_py": skill},
                "entries": [
                    {
                        "suite": {"candidate_sha256": skill_sha, "verdict": "ADMIT"},
                        "promotion_eligible": True,
                        "promotion_blockers": [],
                    }
                ],
                "repairs": repair_rows,
            }
        ),
        encoding="utf-8",
    )


def test_method_freeze_requires_passing_artifacts_and_binds_inputs(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    write_evidence(generated)
    manifest = freeze_adaptive_method(tmp_path / "freeze", generated_root=generated)
    assert manifest["status"] == "FROZEN"
    assert manifest["method_sha256"]
    verification = verify_adaptive_method_freeze(tmp_path / "freeze" / "manifest.json")
    assert verification["verdict"] == "PASS"


def test_method_freeze_allows_direct_admission_but_rejects_failed_gate(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    write_evidence(generated, repairs=[])
    manifest = freeze_adaptive_method(tmp_path / "freeze", generated_root=generated)
    assert (
        manifest["evidence"]["adaptive_search_record"]["selection_mode"]
        == "direct-admit"
    )
    write_evidence(generated, verdict="FAIL")
    with pytest.raises(RuntimeError, match="did not pass"):
        freeze_adaptive_method(tmp_path / "freeze", generated_root=generated)


def test_method_freeze_rejects_causal_development_overclaim(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    write_evidence(generated)
    causal = generated / CAUSAL_DEVELOPMENT_EVIDENCE
    payload = json.loads(causal.read_text(encoding="utf-8"))
    payload["confirmatory_status"] = "PASS"
    causal.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="honest four-trial exploratory lock"):
        freeze_adaptive_method(tmp_path / "freeze", generated_root=generated)
