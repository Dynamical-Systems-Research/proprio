from __future__ import annotations

import json
from pathlib import Path

from proprio.external_instruments import (
    EXTERNAL_INSTRUMENTS,
    VALID_FIXTURES,
    evaluate_external_skill,
    load_external_source,
    verify_helao,
)
from proprio.instrument_types import CandidatePackage
from proprio.skill_search import evaluate_debug_suite

ROOT = Path(__file__).resolve().parents[1]


def test_generalization_panel_has_three_distinct_external_instruments() -> None:
    assert set(EXTERNAL_INSTRUMENTS) == {
        "north-pipette-calibration",
        "helao-gamry-cv",
        "clslab-light-spectrometer",
    }
    assert len({definition.family for definition in EXTERNAL_INSTRUMENTS.values()}) == 3
    for instrument_id in EXTERNAL_INSTRUMENTS:
        source, digest = load_external_source(instrument_id)
        assert instrument_id.split("-")[0] in source.lower()
        assert len(digest) == 64
        assert "controller." in source


def test_helao_verifier_uses_registered_endpoints_not_candidate_arguments() -> None:
    trace = [
        {"operation": operation}
        for operation in (
            "reset",
            "connect",
            "get_limits",
            "read_zero_offset",
            "set_zero_compensation",
            "potential_cycle",
            "disconnect",
        )
    ]
    telemetry = {
        "connected": False,
        "disconnected": True,
        "maximum_scan_rate_v_s": 0.2,
        "zero_offset_v": 0.0,
        "compensation_v": 0.0,
        "parameters": {
            "lower_v": -0.5,
            "upper_v": 0.3,
            "scan_rate_v_s": 0.2,
        },
        "data": {
            "time_s": [float(index) for index in range(64)],
            "potential_v": [-0.5 + 0.8 * index / 63 for index in range(64)],
            "current_ma_cm2": [-1.0 + 2.0 * index / 63 for index in range(64)],
        },
        "violations": [],
    }
    checks = {check.check_id: check for check in verify_helao("x", "y", trace, telemetry)}
    assert checks["potential-sweep-fidelity"].passed is False
    assert checks["potential-sweep-fidelity"].evidence["expected_max_v"] == 0.5


def test_registered_calibration_changes_create_repairable_failures() -> None:
    for instrument_id, definition in EXTERNAL_INSTRUMENTS.items():
        _, source_hash = load_external_source(instrument_id)
        candidate = CandidatePackage(
            instrument_id=instrument_id,
            skill_md=f"---\nname: {instrument_id}\ndescription: Test fixture.\n---\n",
            skill_py=VALID_FIXTURES[instrument_id],
            self_judgment={"verdict": "ACCEPT", "basis": ["test"]},
            source_sha256=source_hash,
            prompt_sha256="test",
            model="test",
            raw_response={},
        )
        acquisition = evaluate_debug_suite(
            candidate,
            definition.acquisition_conditions,
            evaluator=evaluate_external_skill,
        )
        changed = evaluate_debug_suite(
            candidate,
            definition.visible_conditions,
            evaluator=evaluate_external_skill,
        )
        evolution = evaluate_debug_suite(
            candidate,
            definition.evolution_conditions,
            evaluator=evaluate_external_skill,
        )
        assert acquisition.verdict == "ADMIT"
        assert changed.verdict == "REJECT"
        assert evolution.verdict == "REJECT"


def test_external_preflight_and_metrology_evidence_passes_fail_closed_bars() -> None:
    evidence_root = ROOT / "artifacts/evidence/cross-family/qualification"
    for instrument_id in EXTERNAL_INSTRUMENTS:
        preflight = json.loads(
            (evidence_root / "eligibility" / instrument_id / "preflight.json").read_text()
        )
        metrology = json.loads(
            (evidence_root / "metrology" / instrument_id / "summary.json").read_text()
        )
        assert preflight["verdict"] == "PASS"
        assert {case["expected_verdict"] for case in preflight["cases"]} == {
            "ADMIT",
            "REJECT",
            "HOLD",
        }
        assert all(case["passed"] for case in preflight["cases"])
        for case in preflight["cases"]:
            gates = [
                json.dumps(gate, sort_keys=True, separators=(",", ":"))
                for gate in case["observed"]["gates"]
            ]
            assert len(set(gates)) == 1
        assert metrology["verdict"] == "PASS"
        assert metrology["cases_per_class"] == 300
        assert metrology["total_false_admits"] == 0
        assert metrology["valid"]["false_reject_rate"] <= 0.05
        assert all(group["cases"] == 300 for group in metrology["invalid"].values())
