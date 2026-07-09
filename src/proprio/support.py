"""Substrate-support checks and future distribution-hook protocol."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np
import yaml

from proprio.artifacts import source_sha256, write_bytes, write_canonical_json, write_jsonl
from proprio.schema import CheckResult, Provenance, StatusLabel, SupportRecord
from proprio.xrd_generator import generate_calibrant_frame
from proprio.xrd_types import SyntheticFrame


@runtime_checkable
class DistributionSupportHook(Protocol):
    """Typed seam where a future trained-policy distribution binds."""

    support_contract_id: str

    def evaluate(self, evidence: SyntheticFrame, *, calibrant: str) -> SupportRecord: ...


def load_support_contract() -> dict[str, Any]:
    resource = files("proprio").joinpath("data/substrate-support.yaml")
    return yaml.safe_load(resource.read_text(encoding="utf-8"))


def _provenance(contract_sha256: str) -> Provenance:
    return Provenance(
        producer="proprio.support.substrate_support",
        producer_version="0.1.0",
        input_refs=(f"support_contract_sha256:{contract_sha256}",),
        implementation_sha256=source_sha256(Path(__file__)),
    )


def _check(
    *,
    check_id: str,
    passed: bool,
    summary: str,
    metric_name: str,
    metric_value: float,
    threshold: float,
    comparator: str,
    provenance: Provenance,
    details: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        status=StatusLabel.SUCCEEDED if passed else StatusLabel.FAILED,
        summary=summary,
        metric_name=metric_name,
        metric_value=metric_value,
        threshold=threshold,
        comparator=comparator,  # type: ignore[arg-type]
        details=details or {},
        provenance=provenance,
    )


class SubstrateSupportDetector:
    """Deterministic support detector for the v0.1 synthetic substrate."""

    future_policy_distribution_hook = "proprio.distribution_support.v1"

    def __init__(self, contract: dict[str, Any] | None = None) -> None:
        self.contract = contract or load_support_contract()
        self.support_contract_id = str(self.contract["support_contract_id"])
        resource = files("proprio").joinpath("data/substrate-support.yaml")
        self.contract_sha256 = hashlib.sha256(resource.read_bytes()).hexdigest()

    def evaluate(self, evidence: SyntheticFrame, *, calibrant: str) -> SupportRecord:
        frame = np.asarray(evidence.frame)
        allowed_shapes = [tuple(value) for value in self.contract["allowed_shapes"]]
        shape_ok = tuple(frame.shape) in allowed_shapes
        calibrant_ok = calibrant in set(self.contract["allowed_calibrants"])
        finite_fraction = float(np.mean(np.isfinite(frame))) if frame.size else 0.0
        finite_ok = finite_fraction >= float(self.contract["finite_fraction_min"])
        finite_values = frame[np.isfinite(frame)]
        minimum = float(np.min(finite_values)) if finite_values.size else float("-inf")
        intensity_ok = minimum >= float(self.contract["intensity_min"])
        wavelength = evidence.geometry.wavelength_m
        nominal = float(self.contract["wavelength_m"]["nominal"])
        relative_error = abs(wavelength - nominal) / nominal
        wavelength_ok = relative_error <= float(self.contract["wavelength_m"]["relative_tolerance"])
        required_min = float(self.contract["radial_range_deg"]["required_min"])
        required_max = float(self.contract["radial_range_deg"]["required_max"])
        radial_min, radial_max = evidence.geometry.radial_range_deg
        radial_ok = radial_min <= required_min and radial_max >= required_max
        provenance = _provenance(self.contract_sha256)
        checks = (
            _check(
                check_id="supported-frame-shape",
                passed=shape_ok,
                summary="frame shape is declared by the substrate support contract",
                metric_name="shape_supported",
                metric_value=float(shape_ok),
                threshold=1.0,
                comparator="ge",
                provenance=provenance,
                details={"observed_shape": list(frame.shape)},
            ),
            _check(
                check_id="supported-calibrant",
                passed=calibrant_ok,
                summary="calibrant is declared by the substrate support contract",
                metric_name="calibrant_supported",
                metric_value=float(calibrant_ok),
                threshold=1.0,
                comparator="ge",
                provenance=provenance,
                details={"calibrant": calibrant},
            ),
            _check(
                check_id="finite-input",
                passed=finite_ok,
                summary="input contains the required finite-value fraction",
                metric_name="finite_fraction",
                metric_value=finite_fraction,
                threshold=float(self.contract["finite_fraction_min"]),
                comparator="ge",
                provenance=provenance,
            ),
            _check(
                check_id="nonnegative-intensity",
                passed=intensity_ok,
                summary="finite detector intensities are nonnegative",
                metric_name="minimum_intensity",
                metric_value=minimum,
                threshold=float(self.contract["intensity_min"]),
                comparator="ge",
                provenance=provenance,
            ),
            _check(
                check_id="supported-wavelength",
                passed=wavelength_ok,
                summary="wavelength lies inside the declared Cu-Kalpha support interval",
                metric_name="relative_wavelength_error",
                metric_value=relative_error,
                threshold=float(self.contract["wavelength_m"]["relative_tolerance"]),
                comparator="le",
                provenance=provenance,
            ),
            _check(
                check_id="supported-radial-range",
                passed=radial_ok,
                summary="radial observation range covers the declared interval",
                metric_name="radial_range_supported",
                metric_value=float(radial_ok),
                threshold=1.0,
                comparator="ge",
                provenance=provenance,
                details={"observed_range_deg": [radial_min, radial_max]},
            ),
        )
        status = (
            StatusLabel.SUCCEEDED
            if all(check.status is StatusLabel.SUCCEEDED for check in checks)
            else StatusLabel.FAILED
        )
        return SupportRecord(
            status=status,
            support_contract_id=self.support_contract_id,
            checks=checks,
            future_policy_distribution_hook=self.future_policy_distribution_hook,
        )


def _out_case(kind: str, index: int, base_seed: int) -> tuple[SyntheticFrame, str]:
    case = generate_calibrant_frame(seed=base_seed + index)
    if kind == "novel_calibrant":
        return case, "ceo2"
    if kind == "wavelength_out_of_range":
        geometry = case.geometry.model_copy(
            update={"wavelength_m": case.geometry.wavelength_m * 1.20}
        )
        return replace(case, geometry=geometry), case.truth.calibrant
    if kind == "corrupted_nonfinite":
        frame = case.frame.copy()
        frame[0, 0] = np.nan
        return replace(case, frame=frame), case.truth.calibrant
    if kind == "negative_intensity":
        frame = case.frame.copy()
        frame[0, 0] = -1.0
        return replace(case, frame=frame), case.truth.calibrant
    if kind == "unsupported_shape":
        return replace(case, frame=case.frame[:-1]), case.truth.calibrant
    raise ValueError(kind)


def run_support_battery(output_dir: Path) -> dict[str, Any]:
    contract = load_support_contract()
    battery = contract["battery"]
    detector = SubstrateSupportDetector(contract)
    base_seed = int(battery["seed"])
    rows: list[dict[str, Any]] = []
    for index in range(int(battery["in_support_cases"])):
        calibrant = "si" if index % 10 == 0 else "lab6"
        case = generate_calibrant_frame(calibrant=calibrant, seed=base_seed + index)
        record = detector.evaluate(case, calibrant=calibrant)
        rows.append(
            {
                "case_id": f"support-in-{index:04d}",
                "class": "in_support",
                "expected_in_support": True,
                "status": record.status.value,
                "failed_checks": [
                    check.check_id for check in record.checks if check.status is StatusLabel.FAILED
                ],
            }
        )
    out_kinds = (
        "novel_calibrant",
        "wavelength_out_of_range",
        "corrupted_nonfinite",
        "negative_intensity",
        "unsupported_shape",
    )
    for kind_index, kind in enumerate(out_kinds):
        for index in range(int(battery["out_cases_per_class"])):
            case, calibrant = _out_case(kind, index, base_seed + (kind_index + 1) * 100_000)
            record = detector.evaluate(case, calibrant=calibrant)
            rows.append(
                {
                    "case_id": f"support-{kind}-{index:04d}",
                    "class": kind,
                    "expected_in_support": False,
                    "status": record.status.value,
                    "failed_checks": [
                        check.check_id
                        for check in record.checks
                        if check.status is StatusLabel.FAILED
                    ],
                }
            )
    in_rows = [row for row in rows if row["expected_in_support"]]
    out_rows = [row for row in rows if not row["expected_in_support"]]
    false_alarms = sum(row["status"] != StatusLabel.SUCCEEDED for row in in_rows)
    detections = sum(row["status"] != StatusLabel.SUCCEEDED for row in out_rows)
    false_alarm_rate = false_alarms / len(in_rows)
    detection_rate = detections / len(out_rows)
    by_class = {
        kind: {
            "count": len(selected := [row for row in out_rows if row["class"] == kind]),
            "detected": sum(row["status"] != StatusLabel.SUCCEEDED for row in selected),
        }
        for kind in out_kinds
    }
    summary = {
        "schema_version": "proprio.substrate_support_battery.v0.1",
        "support_contract_id": detector.support_contract_id,
        "contract_sha256": detector.contract_sha256,
        "in_support_count": len(in_rows),
        "out_of_support_count": len(out_rows),
        "false_alarms": false_alarms,
        "false_alarm_rate": false_alarm_rate,
        "false_alarm_rate_max": float(battery["false_alarm_rate_max"]),
        "detections": detections,
        "detection_rate": detection_rate,
        "detection_rate_min": float(battery["detection_rate_min"]),
        "by_class": by_class,
        "verdict": (
            "PASS"
            if false_alarm_rate <= float(battery["false_alarm_rate_max"])
            and detection_rate >= float(battery["detection_rate_min"])
            else "FAIL"
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    resource = files("proprio").joinpath("data/substrate-support.yaml")
    write_bytes(output_dir / "substrate-support.yaml", resource.read_bytes(), "application/yaml")
    write_jsonl(output_dir / "battery.jsonl", rows)
    write_canonical_json(output_dir / "summary.json", summary)
    report = "\n".join(
        [
            "# Proprio v0.1 substrate-support battery",
            "",
            f"Verdict: **{summary['verdict']}**",
            "",
            f"- In-support false-alarm rate: {false_alarm_rate:.6f} "
            f"(bar <= {float(battery['false_alarm_rate_max']):.6f})",
            f"- Out-of-support detection rate: {detection_rate:.6f} "
            f"(bar >= {float(battery['detection_rate_min']):.6f})",
            "",
            "This support contract describes the synthetic substrate, not DSV4's training data.",
            "A future trained-policy distribution binds through `DistributionSupportHook`.",
            "",
        ]
    )
    write_bytes(output_dir / "report.md", report.encode(), "text/markdown")
    return summary
