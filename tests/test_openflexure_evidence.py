import hashlib
from pathlib import Path

from proprio.artifacts import write_canonical_json
from proprio.openflexure_evidence import (
    ACQUISITION_LOCKED,
    EVOLUTION_LOCKED,
    _record_path,
    stage,
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()


def _record(root: Path, label: str, candidate: Path, verdict: str) -> None:
    path = _record_path(root, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(
        path,
        {
            "schema_version": "proprio.openflexure_full_loop.v0.1",
            "label": label,
            "candidate_sha256": _hash(candidate),
            "verdict": verdict,
        },
    )


def test_locked_conditions_are_frozen_and_keep_hidden_drift_direction() -> None:
    assert len(ACQUISITION_LOCKED) == 5
    assert len(EVOLUTION_LOCKED) == 5
    assert all(row["correction_direction"] == 1 for row in ACQUISITION_LOCKED)
    assert all(row["correction_direction"] == -1 for row in EVOLUTION_LOCKED)
    assert min(row["start_z"] for row in ACQUISITION_LOCKED) == -3200
    assert max(row["start_z"] for row in ACQUISITION_LOCKED) == 3200


def test_stage_requires_rejection_and_all_three_replays(tmp_path: Path) -> None:
    parent = tmp_path / "parent.py"
    rejected = tmp_path / "rejected.py"
    proposal = tmp_path / "proposal.py"
    parent.write_text("def run(controller):\n    return {'version': 1}\n", encoding="utf-8")
    rejected.write_text("def run(controller):\n    return {'version': 2}\n", encoding="utf-8")
    proposal.write_text("def run(controller):\n    return {'version': 3}\n", encoding="utf-8")
    _record(tmp_path, "acquisition-locked", parent, "PASS")
    _record(tmp_path, "drift-parent", parent, "FAIL")
    _record(tmp_path, "evolution-rejected", rejected, "FAIL")
    _record(tmp_path, "evolution-changed", proposal, "PASS")
    _record(tmp_path, "evolution-historical", proposal, "PASS")
    _record(tmp_path, "evolution-locked", proposal, "PASS")

    summary = stage(parent_path=parent, proposal_path=proposal, output_dir=tmp_path)

    assert summary["status"] == "STAGED"
    assert summary["hardware_validation_required"] is True
    assert summary["parent_skill_sha256"] == _hash(parent)
    assert summary["rollback_skill_sha256"] == _hash(parent)
    assert summary["proposal_skill_sha256"] == _hash(proposal)
    assert all(summary["checks"].values())


def test_stage_rejects_if_historical_replay_fails(tmp_path: Path) -> None:
    parent = tmp_path / "parent.py"
    rejected = tmp_path / "rejected.py"
    proposal = tmp_path / "proposal.py"
    parent.write_text("def run(controller):\n    return {'version': 1}\n", encoding="utf-8")
    rejected.write_text("def run(controller):\n    return {'version': 2}\n", encoding="utf-8")
    proposal.write_text("def run(controller):\n    return {'version': 3}\n", encoding="utf-8")
    _record(tmp_path, "acquisition-locked", parent, "PASS")
    _record(tmp_path, "drift-parent", parent, "FAIL")
    _record(tmp_path, "evolution-rejected", rejected, "FAIL")
    _record(tmp_path, "evolution-changed", proposal, "PASS")
    _record(tmp_path, "evolution-historical", proposal, "FAIL")
    _record(tmp_path, "evolution-locked", proposal, "PASS")

    summary = stage(parent_path=parent, proposal_path=proposal, output_dir=tmp_path)

    assert summary["status"] == "REJECTED"
    assert summary["checks"]["historical-replay-passed"] is False
