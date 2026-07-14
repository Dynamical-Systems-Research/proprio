import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from proprio.catalog import validate_catalog
from proprio.schema import canonical_json
from proprio.skill_publication import (
    PUBLISHED_SKILLS,
    PublishedSkill,
    build_skill_library,
    build_skill_verification,
    publish_skill_library,
)

ROOT = Path(__file__).resolve().parents[1]

RESTORED_CODE_HASHES = {
    "absorbance-plate-read": "8927d96c2081de2050ee796d45f1fdcd7f0531d35f979bee4acc2101b3f7b0a9",
    "calibrated-pump-dose": "1b17847ba8a931d5b60de736785103f901a408ff503545e307f4c14d6d52b8a1",
    "dual-pump-blend": "1c6f2ce64419ea351bd8e76645f5e9daec6f395f20663a9a672f37e51887f7a4",
    "fluorescence-plate-read": "0469cd57902d5afedd62a4c1149c5371983a793766dcf292702965b94bf90869",
    "isothermal-hold": "315fde59767a6912c32beda8e3d95a900dd6894b1324e29f189588634bf95bbd",
    "thermal-cycle": "8a110adca40437ae7f9068c42c841d7736bf04d42c05b58cc5839f08b5b1cde4",
}


@pytest.mark.skipif(
    os.environ.get("PROPRIO_OPENFLEXURE_LIVE") != "1",
    reason="full publication replay requires the pinned native OpenFlexure server",
)
def test_skill_library_rebuild_is_deterministic_and_passing() -> None:
    publication, records, catalog = build_skill_library(ROOT)

    assert publication["verdict"] == "PASS"
    assert publication["failed_skills"] == []
    assert publication["published_skills"] == len(PUBLISHED_SKILLS) == 12
    assert catalog == json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    for skill_id, record in records.items():
        checked_in = json.loads(
            (ROOT / "skills" / skill_id / "references" / "verification.json").read_text(
                encoding="utf-8"
            )
        )
        assert canonical_json(record) == canonical_json(checked_in)


def test_qualified_skills_preserve_the_validated_implementations() -> None:
    catalog = validate_catalog(ROOT)
    entries = {entry.id: entry for entry in catalog.skills}

    for skill_id, expected_hash in RESTORED_CODE_HASHES.items():
        entry = entries[skill_id]
        assert entry.status == "simulation_qualified"
        assert entry.verification.code_sha256 == expected_hash
        verification = json.loads((ROOT / entry.verification.artifact).read_text(encoding="utf-8"))
        assert verification["visible"]["verdict"] == "ADMIT"
        assert verification["locked"]["verdict"] == "ADMIT"
        assert verification["evolution"] is None


def test_every_simulation_skill_declares_one_provider() -> None:
    for skill in PUBLISHED_SKILLS:
        if skill.status == "reference":
            assert skill.provider_instrument_id is None
        else:
            assert skill.provider_instrument_id is not None


def test_keithley_publication_replays_the_common_runtime() -> None:
    skill = next(row for row in PUBLISHED_SKILLS if row.skill_id.startswith("keithley"))
    record = build_skill_verification(ROOT, skill)

    assert record["verdict"] == "PASS"
    assert record["candidate_execution"] == {
        "decision": "ADMIT",
        "verdict": "PASS",
        "visible_evidence_read": True,
    }
    assert record["visible"]["verdict"] == "ADMIT"
    assert record["locked"]["verdict"] == "ADMIT"
    assert record["evolution"] is None
    assert "evidence" not in record


def test_staged_skill_requires_registered_evolution() -> None:
    staged = PublishedSkill(
        "keithley-2450-measure-current",
        "1.0.0",
        "Keithley 2450-style SMU",
        "simulation_staged",
        "proprio.keithley.keithley-2450-measure-current",
        "skills/keithley-2450-measure-current/scripts/operate.py",
    )
    with pytest.raises(ValueError, match="no registered evolution conditions"):
        build_skill_verification(ROOT, staged)


def test_failed_publication_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    existing = tmp_path / "catalog.json"
    existing.write_text("unchanged", encoding="utf-8")
    failed_record = {
        "candidate_execution": {"verdict": "PASS"},
        "visible": {"verdict": "ADMIT"},
        "locked": {"verdict": "REJECT"},
        "evolution": None,
        "verdict": "FAIL",
    }

    monkeypatch.setattr(
        "proprio.skill_publication.build_skill_library",
        lambda _root: (
            {"verdict": "FAIL", "failed_skills": ["broken-skill"]},
            {"broken-skill": failed_record},
            {},
        ),
    )

    with pytest.raises(RuntimeError, match="locked=REJECT"):
        publish_skill_library(tmp_path)
    assert existing.read_text(encoding="utf-8") == "unchanged"
    assert not (tmp_path / "skills").exists()


def test_publication_rolls_back_a_mid_commit_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [
        tmp_path / "skills" / skill_id / "references" / "verification.json"
        for skill_id in ("first", "second")
    ]
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True)
        path.write_text(f"old-{index}\n", encoding="utf-8")
    catalog = tmp_path / "catalog.json"
    catalog.write_text("old-catalog\n", encoding="utf-8")
    monkeypatch.setattr(
        "proprio.skill_publication.build_skill_library",
        lambda _root: (
            {"verdict": "PASS", "failed_skills": []},
            {"first": {"verdict": "PASS"}, "second": {"verdict": "PASS"}},
            {"skills": []},
        ),
    )
    real_replace = os.replace
    calls = 0

    def fail_second_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publication failure")
        real_replace(source, destination)

    monkeypatch.setattr("proprio.skill_publication.os.replace", fail_second_replace)

    with pytest.raises(OSError, match="injected publication failure"):
        publish_skill_library(tmp_path)
    assert [path.read_text(encoding="utf-8") for path in paths] == ["old-0\n", "old-1\n"]
    assert catalog.read_text(encoding="utf-8") == "old-catalog\n"


def test_openflexure_parent_is_compact_and_hash_bound() -> None:
    skill = next(row for row in PUBLISHED_SKILLS if row.skill_id.startswith("openflexure"))
    assert skill.parent_code_path is not None
    parent = ROOT / skill.parent_code_path
    assert hashlib.sha256(parent.read_bytes()).hexdigest() == (
        "d486c179f0b299ffd0ab978579caecf3febd1c65296d3c12fc5eeb91c7adddb8"
    )


def test_xrd_reference_is_excluded_from_verified_skill_claim() -> None:
    skill = next(row for row in PUBLISHED_SKILLS if row.status == "reference")
    record = build_skill_verification(ROOT, skill)
    assert record["verified_skill_claim"] is False
    assert "excluded from the simulator-verified skill claim" in record["claim_boundary"]


def test_packages_are_flat_and_have_only_public_skill_surfaces() -> None:
    allowed = {"SKILL.md", "agents", "references", "scripts"}

    for package in (ROOT / "skills").iterdir():
        if not package.is_dir():
            continue
        assert {path.name for path in package.iterdir()} <= allowed
        assert (package / "SKILL.md").is_file()
        assert (package / "agents" / "openai.yaml").is_file()
        assert (package / "references" / "verification.json").is_file()


def test_remote_release_surface_excludes_research_archives() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert not (ROOT / "cassettes").exists()
    assert not (ROOT / "docs" / "technical-report.md").exists()
    assert "google-deepmind" not in readme.lower()
    assert "npx skills add Dynamical-Systems-Research/proprio" in readme

    history = subprocess.run(
        [
            "git",
            "rev-list",
            "--objects",
            "--branches",
            "--tags",
            "--remotes=origin",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert not any(
        len(row.split(" ", 1)) == 2 and row.split(" ", 1)[1].startswith("cassettes/")
        for row in history
    )


def test_compact_study_evidence_supports_public_claims() -> None:
    studies = ROOT / "artifacts" / "evidence" / "studies"

    causal = json.loads((studies / "causal-synthesis.json").read_text())
    assert (causal["pairs"], causal["truthful_successes"], causal["none_successes"]) == (18, 14, 0)

    replication = json.loads((studies / "replication.json").read_text())
    assert (replication["instrument_count"], replication["replicate_count"]) == (7, 70)

    confirmatory = json.loads((studies / "confirmatory.json").read_text())
    assert confirmatory["instrument_count"] == 6
    assert confirmatory["unsafe_promotions"] == 0

    cross_family = json.loads((studies / "cross-family.json").read_text())
    assert [row["model_calls_to_first_qualified"] for row in cross_family["families"]] == [
        6,
        6,
        3,
    ]
    assert sum(row["invalid_promotion_count"] for row in cross_family["families"]) == 0

    evolution = json.loads((studies / "evolution.json").read_text())
    assert (evolution["staged_proposals"], evolution["unsafe_promotions"]) == (8, 0)
