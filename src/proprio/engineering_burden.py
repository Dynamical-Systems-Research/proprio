"""Measured instrument-specific verifier and simulator integration burden."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import write_canonical_json
from proprio.confirmatory_qualification import evaluate_confirmatory_skill
from proprio.confirmatory_skills import render_confirmatory_repair
from proprio.instrument_types import SimulationScenario

ROOT = Path(__file__).resolve().parents[2]
LOG = Path(__file__).with_name("data") / "engineering-burden-log.yaml"

FAMILY_WORK = {
    "optical_measurement": {
        "simulator_symbols": [
            "_PlateReaderController",
            "AbsorbancePlateController",
            "FluorescencePlateController",
        ],
        "verifier_symbols": ["_verify_optical"],
        "source_bundles": ["absorbance-plate-read", "fluorescence-plate-read"],
        "invalid_classes": 4,
        "external_runtime": "none; PyLabRobot public interface used as a source reference",
    },
    "calibrated_delivery": {
        "simulator_symbols": ["CalibratedPumpController", "DualPumpController"],
        "verifier_symbols": ["_verify_delivery"],
        "source_bundles": ["calibrated-pump-dose", "dual-pump-blend"],
        "invalid_classes": 4,
        "external_runtime": "none; PyLabRobot public interface used as a source reference",
    },
    "thermal_control": {
        "simulator_symbols": [
            "_ThermalController",
            "IsothermalController",
            "ThermalCycleController",
        ],
        "verifier_symbols": ["_verify_thermal"],
        "source_bundles": ["isothermal-hold", "thermal-cycle"],
        "invalid_classes": 4,
        "external_runtime": "none; PyLabRobot public interface used as a source reference",
    },
}


def _source_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _code_loc(path: Path, *, start: int | None = None, end: int | None = None) -> int:
    lines = _source_lines(path)
    selected = lines[(start or 1) - 1 : end]
    return sum(bool(line.strip()) and not line.lstrip().startswith("#") for line in selected)


def _symbol_loc(path: Path, names: list[str]) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted(set(names) - set(nodes))
    if missing:
        raise ValueError(f"missing burden symbols in {path.name}: {missing}")
    return sum(
        _code_loc(path, start=nodes[name].lineno, end=nodes[name].end_lineno) for name in names
    )


def _markdown_loc(path: Path) -> int:
    return sum(bool(line.strip()) for line in _source_lines(path))


def _physical_checks(instrument_id: str) -> int:
    gate = evaluate_confirmatory_skill(
        instrument_id,
        render_confirmatory_repair(instrument_id),
        scenario=SimulationScenario.REPAIR,
    )
    return sum(
        check.check_id not in {"static-safety", "runtime-completed"} for check in gate.checks
    )


def measure_engineering_burden() -> dict[str, Any]:
    simulator_path = ROOT / "src/proprio/confirmatory_instruments.py"
    verifier_path = ROOT / "src/proprio/confirmatory_verifiers.py"
    rows: dict[str, Any] = {}
    for family, config in FAMILY_WORK.items():
        bundles = [
            ROOT / "sources/confirmatory" / item / "source.md" for item in config["source_bundles"]
        ]
        rows[family] = {
            "instrument_count": len(bundles),
            "instrument_specific_simulator_loc": _symbol_loc(
                simulator_path, config["simulator_symbols"]
            ),
            "instrument_specific_adapter_loc": 0,
            "instrument_specific_verifier_loc": _symbol_loc(
                verifier_path, config["verifier_symbols"]
            ),
            "source_bundle_loc": sum(_markdown_loc(path) for path in bundles),
            "physical_checks_by_instrument": {
                instrument_id: _physical_checks(instrument_id)
                for instrument_id in config["source_bundles"]
            },
            "labeled_invalid_classes": config["invalid_classes"],
            "external_simulator_loc_authored": 0,
            "external_runtime": config["external_runtime"],
            "person_hours": "unavailable",
        }

    microscopy_source = ROOT / "sources/confirmatory/microscope-autofocus/source.md"
    microscopy_verifier = ROOT / "src/proprio/microscopy_verifier.py"
    microscopy_adapter = ROOT / "src/proprio/microscopy.py"
    microscopy_metrology = ROOT / "src/proprio/microscopy_metrology.py"
    locked = yaml.safe_load(LOG.read_text(encoding="utf-8"))
    rows["optical_microscopy"] = {
        "instrument_count": 1,
        "instrument_specific_simulator_loc": 0,
        "instrument_specific_adapter_loc": _code_loc(microscopy_adapter),
        "instrument_specific_verifier_loc": _code_loc(microscopy_verifier),
        "source_bundle_loc": _markdown_loc(microscopy_source),
        "metrology_harness_loc": _code_loc(microscopy_metrology),
        "physical_checks_by_instrument": {"microscope-autofocus": 10},
        "labeled_invalid_classes": 8,
        "external_simulator_loc_authored": 0,
        "external_runtime": (
            "OpenFlexure server revision d26b93e1, external GPL-3.0 process via public API"
        ),
        "person_hours": "unavailable",
    }
    generic_paths = [
        ROOT / "src/proprio/instrument_agent.py",
        ROOT / "src/proprio/instrument_qualification.py",
        ROOT / "src/proprio/replication_study.py",
        ROOT / "src/proprio/independent_review.py",
    ]
    result = {
        "schema_version": "proprio.engineering_burden.v0.1",
        "measurement_unit": "nonblank non-comment source lines plus declared checks and classes",
        "families": rows,
        "shared_generic_framework_loc": sum(_code_loc(path) for path in generic_paths),
        "shared_confirmatory_metrology_loc": _code_loc(
            ROOT / "src/proprio/confirmatory_metrology.py"
        )
        + _code_loc(ROOT / "src/proprio/confirmatory_skills.py"),
        "prospective_execution_window": locked["prospective_execution_window"],
        "person_time_limitation": locked["measurement_policy"],
        "verdict": "PASS",
    }
    return result


def run_engineering_burden(output_dir: Path) -> dict[str, Any]:
    result = measure_engineering_burden()
    write_canonical_json(output_dir / "summary.json", result)
    return result
