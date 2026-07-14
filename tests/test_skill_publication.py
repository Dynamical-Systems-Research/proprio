import json
import subprocess
from pathlib import Path

from proprio.catalog import validate_catalog
from proprio.schema import canonical_json
from proprio.skill_publication import PUBLISHED_SKILLS, build_skill_library

ROOT = Path(__file__).resolve().parents[1]

RESTORED_CODE_HASHES = {
    "absorbance-plate-read": "8927d96c2081de2050ee796d45f1fdcd7f0531d35f979bee4acc2101b3f7b0a9",
    "calibrated-pump-dose": "1b17847ba8a931d5b60de736785103f901a408ff503545e307f4c14d6d52b8a1",
    "dual-pump-blend": "1c6f2ce64419ea351bd8e76645f5e9daec6f395f20663a9a672f37e51887f7a4",
    "fluorescence-plate-read": "0469cd57902d5afedd62a4c1149c5371983a793766dcf292702965b94bf90869",
    "isothermal-hold": "315fde59767a6912c32beda8e3d95a900dd6894b1324e29f189588634bf95bbd",
    "thermal-cycle": "8a110adca40437ae7f9068c42c841d7736bf04d42c05b58cc5839f08b5b1cde4",
}


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


def test_restored_skills_preserve_the_validated_implementations() -> None:
    catalog = validate_catalog(ROOT)
    entries = {entry.id: entry for entry in catalog.skills}

    for skill_id, expected_hash in RESTORED_CODE_HASHES.items():
        entry = entries[skill_id]
        assert entry.status == "simulation_qualified"
        assert entry.verification.code_sha256 == expected_hash
        verification = json.loads((ROOT / entry.verification.artifact).read_text(encoding="utf-8"))
        assert verification["visible"]["verdict"] == "ADMIT"
        assert verification["locked"]["verdict"] == "ADMIT"
        assert verification["registered_evolution"]["verdict"] == "REJECT"


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
        ["git", "rev-list", "--objects", "--all"],
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
