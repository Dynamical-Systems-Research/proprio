from pathlib import Path

import pytest

from proprio.catalog import validate_catalog
from proprio.skill_library import package_confirmatory_skills

ROOT = Path(__file__).resolve().parents[1]


def test_packaging_refuses_incomplete_confirmatory_evidence(tmp_path: Path) -> None:
    cassette_dir = tmp_path / "cassettes"
    cassette_dir.mkdir()
    with pytest.raises(ValueError, match="has not passed"):
        package_confirmatory_skills(cassette_dir, tmp_path, tmp_path / "evidence")


def test_release_catalog_contains_exact_confirmatory_packages() -> None:
    catalog = validate_catalog(ROOT)
    packaged = {entry.id for entry in catalog.skills if entry.status == "simulation_qualified"}
    assert {
        "absorbance-plate-read",
        "calibrated-pump-dose",
        "dual-pump-blend",
        "fluorescence-plate-read",
        "isothermal-hold",
        "keithley-2450-measure-current",
        "thermal-cycle",
    }.issubset(packaged)
