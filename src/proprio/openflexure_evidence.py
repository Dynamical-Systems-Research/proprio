"""Evidence-bound OpenFlexure acquisition and evolution command harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from proprio.adaptive_microscopy import (
    AdaptiveMicroscopyController,
    AdaptiveOpenFlexureBackend,
    evaluate_adaptive_microscopy_skill,
)
from proprio.artifacts import file_sha256, write_canonical_json
from proprio.instrument_types import HardGateResult, SimulationScenario
from proprio.microscopy import OPENFLEXURE_REVISION

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "sources/development/microscope-autofocus/source.md"
VERIFIER_PATH = Path(__file__).with_name("adaptive_microscopy_verifier.py")
THRESHOLDS_PATH = Path(__file__).with_name("data") / "adaptive-microscopy-thresholds.yaml"
SCHEMA_VERSION = "proprio.openflexure_full_loop.v0.1"

ACQUISITION_VISIBLE: Mapping[str, float] = {
    "start_z": -3300,
    "measurement_noise_level": 2.0,
    "stage_bias_steps": 400,
    "correction_direction": 1,
}
HISTORICAL_CONDITIONS: tuple[Mapping[str, float], ...] = (
    {"start_z": 800, "measurement_noise_level": 2.0},
    {
        "start_z": 1200,
        "measurement_noise_level": 2.0,
        "stage_bias_steps": 250,
        "correction_direction": 1,
    },
    ACQUISITION_VISIBLE,
)
ACQUISITION_LOCKED: tuple[Mapping[str, float], ...] = tuple(
    {
        "start_z": start_z,
        "measurement_noise_level": 2.0,
        "stage_bias_steps": bias,
        "correction_direction": 1,
    }
    for start_z, bias in ((-3200, 320), (-1700, 380), (0, 440), (1700, 360), (3200, 420))
)
DRIFT_CONDITION: Mapping[str, float] = {
    "start_z": 1800,
    "measurement_noise_level": 2.0,
    "stage_bias_steps": 400,
    "correction_direction": -1,
}
EVOLUTION_LOCKED: tuple[Mapping[str, float], ...] = tuple(
    {
        "start_z": start_z,
        "measurement_noise_level": 2.0,
        "stage_bias_steps": bias,
        "correction_direction": -1,
    }
    for start_z, bias in ((-3200, 300), (-1600, 460), (100, 350), (1700, 500), (3200, 410))
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _condition_id(prefix: str, condition: Mapping[str, float]) -> str:
    payload = json.dumps(dict(condition), sort_keys=True, separators=(",", ":"))
    return f"{prefix}-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


class VisibleController(AdaptiveMicroscopyController):
    """Emit controller operations without changing controller behavior."""

    def _show(self, operation: str, detail: str = "") -> None:
        suffix = f" {detail}" if detail else ""
        print(f"CONTROLLER {operation}{suffix}", flush=True)

    def reset(self) -> None:
        self._show("reset", f"start_z={self.start_z}")
        super().reset()

    def full_auto_calibrate(self) -> None:
        self._show("full_auto_calibrate")
        super().full_auto_calibrate()

    def fast_autofocus(self, dz_steps: int) -> dict[str, float]:
        self._show("fast_autofocus", f"dz_steps={dz_steps}")
        result = super().fast_autofocus(dz_steps)
        self._show("autofocus_readback", f"position_z={result['position_z']:.0f}")
        return result

    def move_z(self, delta_steps: int) -> dict[str, float]:
        self._show("move_z", f"commanded_delta={float(delta_steps):.0f}")
        result = super().move_z(delta_steps)
        self._show("stage_readback", f"position_z={result['position_z']:.0f}")
        return result

    def settle(self) -> None:
        self._show("settle")
        super().settle()

    def capture_focus_series(self, repeats: int) -> dict[str, float]:
        self._show("capture_focus_series", f"repeats={repeats}")
        result = super().capture_focus_series(repeats)
        self._show(
            "measurement",
            (
                f"position_z={result['position_z']:.0f} "
                f"relative_spread={result['relative_spread']:.4f}"
            ),
        )
        return result

    def release(self) -> None:
        self._show("release")
        super().release()


def _evaluate(
    source: str,
    *,
    scenario: SimulationScenario,
    condition: Mapping[str, float],
    simulator_url: str,
) -> HardGateResult:
    controller = VisibleController(
        AdaptiveOpenFlexureBackend(simulator_url),
        start_z=int(condition["start_z"]),
        measurement_noise_level=float(condition.get("measurement_noise_level", 2.0)),
        stage_bias_steps=int(condition.get("stage_bias_steps", 0)),
        correction_direction=int(condition.get("correction_direction", 1)),
    )
    return evaluate_adaptive_microscopy_skill(
        source,
        scenario=scenario,
        controller=controller,
    )


def _gate_payload(gate: HardGateResult) -> dict[str, Any]:
    return gate.model_dump(mode="json")


def _print_gate(gate: HardGateResult) -> None:
    print("GATE independent physical checks", flush=True)
    for check in gate.checks:
        state = "PASS" if check.passed else "FAIL"
        evidence = check.evidence
        detail = ""
        if check.check_id == "calibrated-focus-reference":
            detail = f" observed_z={evidence.get('observed_z')}"
        elif check.check_id == "autofocus-reference-covered" and "minimum_z" in evidence:
            detail = f" range=[{evidence['minimum_z']:.0f},{evidence['maximum_z']:.0f}]"
        elif check.check_id == "autofocus-peak-selected" and "final_z" in evidence:
            detail = f" final_z={evidence['final_z']} peak_z={evidence['peak_z']:.0f}"
        elif check.check_id == "acquisition-time-budget":
            detail = f" seconds={evidence.get('observed_seconds')}"
        print(f"CHECK {state} {check.check_id}{detail}", flush=True)
    print(f"DECISION {gate.verdict}", flush=True)
    print(
        f"HASH candidate={gate.skill_sha256[:12]} verifier={gate.verifier_sha256[:12]}",
        flush=True,
    )


def _record_path(output_dir: Path, label: str) -> Path:
    return output_dir / "runs" / f"{label}.json"


def _write_run(
    output_dir: Path,
    *,
    label: str,
    candidate_path: Path,
    scenario: SimulationScenario,
    conditions: Sequence[Mapping[str, float]],
    gates: Sequence[HardGateResult],
) -> dict[str, Any]:
    candidate = candidate_path.read_text(encoding="utf-8")
    cases = []
    for index, (condition, gate) in enumerate(zip(conditions, gates, strict=True)):
        cases.append(
            {
                "condition_id": _condition_id(f"{label}-{index:02d}", condition),
                "condition": dict(condition),
                "gate": _gate_payload(gate),
            }
        )
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "fresh_simulator_execution",
        "label": label,
        "captured_at_unix": time.time(),
        "scenario": scenario.value,
        "candidate_path": str(candidate_path),
        "candidate_sha256": _sha256_text(candidate),
        "simulator_revision": OPENFLEXURE_REVISION,
        "verifier_sha256": gates[0].verifier_sha256,
        "cases": cases,
        "passed_cases": sum(gate.verdict == "ADMIT" for gate in gates),
        "verdict": "PASS" if all(gate.verdict == "ADMIT" for gate in gates) else "FAIL",
    }
    path = _record_path(output_dir, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(path, record)
    return record


def run_phase(
    phase: str,
    *,
    candidate_path: Path,
    output_dir: Path,
    simulator_url: str,
) -> dict[str, Any]:
    source = candidate_path.read_text(encoding="utf-8")
    configurations: dict[
        str, tuple[SimulationScenario, tuple[Mapping[str, float], ...]]
    ] = {
        "acquisition-visible": (SimulationScenario.REPAIR, (ACQUISITION_VISIBLE,)),
        "acquisition-historical": (SimulationScenario.NOMINAL, HISTORICAL_CONDITIONS),
        "acquisition-locked": (SimulationScenario.REPAIR, ACQUISITION_LOCKED),
        "drift-parent": (SimulationScenario.DRIFT, (DRIFT_CONDITION,)),
        "evolution-changed": (SimulationScenario.DRIFT, (DRIFT_CONDITION,)),
        "evolution-historical": (SimulationScenario.NOMINAL, HISTORICAL_CONDITIONS),
        "evolution-locked": (SimulationScenario.DRIFT, EVOLUTION_LOCKED),
    }
    if phase not in configurations:
        raise ValueError(f"unknown phase: {phase}")
    scenario, conditions = configurations[phase]
    gates = []
    print(f"EXECUTION {phase} cases={len(conditions)}", flush=True)
    print(f"SIMULATOR revision={OPENFLEXURE_REVISION}", flush=True)
    print(f"CANDIDATE sha256={_sha256_text(source)}", flush=True)
    for index, condition in enumerate(conditions):
        print(f"CASE {index + 1}/{len(conditions)}", flush=True)
        gate = _evaluate(
            source,
            scenario=scenario,
            condition=condition,
            simulator_url=simulator_url,
        )
        gates.append(gate)
        _print_gate(gate)
    record = _write_run(
        output_dir,
        label=phase,
        candidate_path=candidate_path,
        scenario=scenario,
        conditions=conditions,
        gates=gates,
    )
    print(f"RECORD {_record_path(output_dir, phase)}", flush=True)
    print(f"SUITE {record['verdict']} {record['passed_cases']}/{len(conditions)}", flush=True)
    return record


def _read_record(output_dir: Path, label: str) -> dict[str, Any]:
    path = _record_path(output_dir, label)
    if not path.is_file():
        raise RuntimeError(f"missing required record: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def stage(
    *,
    parent_path: Path,
    proposal_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    parent = parent_path.read_text(encoding="utf-8")
    proposal = proposal_path.read_text(encoding="utf-8")
    parent_hash = _sha256_text(parent)
    proposal_hash = _sha256_text(proposal)
    admission = _read_record(output_dir, "acquisition-locked")
    drift = _read_record(output_dir, "drift-parent")
    rejected = _read_record(output_dir, "evolution-rejected")
    changed = _read_record(output_dir, "evolution-changed")
    historical = _read_record(output_dir, "evolution-historical")
    locked = _read_record(output_dir, "evolution-locked")
    checks = {
        "parent-was-admitted": (
            admission["candidate_sha256"] == parent_hash and admission["verdict"] == "PASS"
        ),
        "drift-invalidated-parent": (
            drift["candidate_sha256"] == parent_hash and drift["verdict"] == "FAIL"
        ),
        "evolution-proposal-was-rejected": (
            rejected["candidate_sha256"] not in {parent_hash, proposal_hash}
            and rejected["verdict"] == "FAIL"
        ),
        "changed-condition-passed": (
            changed["candidate_sha256"] == proposal_hash and changed["verdict"] == "PASS"
        ),
        "historical-replay-passed": (
            historical["candidate_sha256"] == proposal_hash
            and historical["verdict"] == "PASS"
        ),
        "locked-replay-passed": (
            locked["candidate_sha256"] == proposal_hash and locked["verdict"] == "PASS"
        ),
        "proposal-differs-from-parent": proposal_hash != parent_hash,
        "parent-immutable": _sha256_text(parent_path.read_text(encoding="utf-8")) == parent_hash,
    }
    staged = all(checks.values())
    summary = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "evolution_summary",
        "status": "STAGED" if staged else "REJECTED",
        "hardware_validation_required": True,
        "parent_skill_sha256": parent_hash,
        "rollback_skill_sha256": parent_hash,
        "proposal_skill_sha256": proposal_hash,
        "parent_immutable": checks["parent-immutable"],
        "checks": checks,
        "bindings": {
            "source": {
                "path": str(SOURCE_PATH.relative_to(ROOT)),
                "sha256": file_sha256(SOURCE_PATH),
            },
            "simulator_revision": OPENFLEXURE_REVISION,
            "verifier": {
                "path": str(VERIFIER_PATH.relative_to(ROOT)),
                "sha256": file_sha256(VERIFIER_PATH),
            },
            "thresholds": {
                "path": str(THRESHOLDS_PATH.relative_to(ROOT)),
                "sha256": file_sha256(THRESHOLDS_PATH),
            },
        },
    }
    write_canonical_json(output_dir / "summary.json", summary)
    for name, passed in checks.items():
        print(f"CHECK {'PASS' if passed else 'FAIL'} {name}", flush=True)
    print(f"DECISION {summary['status']}", flush=True)
    print(f"HASH parent={parent_hash[:12]} proposal={proposal_hash[:12]}", flush=True)
    print("Verified in simulation. Hardware validation remains separate.", flush=True)
    return summary


def snapshot_rejected(output_dir: Path, candidate_path: Path) -> dict[str, Any]:
    record = _read_record(output_dir, "evolution-changed")
    if record["verdict"] != "FAIL":
        raise RuntimeError("the current evolution-changed record is not rejected")
    source = candidate_path.read_text(encoding="utf-8")
    if record["candidate_sha256"] != _sha256_text(source):
        raise RuntimeError("rejected record does not match the supplied candidate")
    destination = _record_path(output_dir, "evolution-rejected")
    write_canonical_json(destination, {**record, "label": "evolution-rejected"})
    print(f"DECISION REJECT proposal={record['candidate_sha256'][:12]}", flush=True)
    return record


def snapshot_acquisition_rejected(output_dir: Path, candidate_path: Path) -> dict[str, Any]:
    record = _read_record(output_dir, "acquisition-visible")
    if record["verdict"] != "FAIL":
        raise RuntimeError("the current acquisition-visible record is not rejected")
    source = candidate_path.read_text(encoding="utf-8")
    if record["candidate_sha256"] != _sha256_text(source):
        raise RuntimeError("rejected record does not match the supplied candidate")
    destination = _record_path(output_dir, "acquisition-rejected")
    write_canonical_json(destination, {**record, "label": "acquisition-rejected"})
    print(f"DECISION REJECT candidate={record['candidate_sha256'][:12]}", flush=True)
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--simulator-url", default="http://127.0.0.1:5100")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("phase")
    run.add_argument("candidate", type=Path)
    rejected = subparsers.add_parser("snapshot-rejected")
    rejected.add_argument("candidate", type=Path)
    acquisition_rejected = subparsers.add_parser("snapshot-acquisition-rejected")
    acquisition_rejected.add_argument("candidate", type=Path)
    staged = subparsers.add_parser("stage")
    staged.add_argument("parent", type=Path)
    staged.add_argument("proposal", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run":
        record = run_phase(
            args.phase,
            candidate_path=args.candidate,
            output_dir=args.output_dir,
            simulator_url=args.simulator_url,
        )
        return 0 if record["verdict"] == "PASS" else 2
    elif args.command == "snapshot-rejected":
        snapshot_rejected(args.output_dir, args.candidate)
    elif args.command == "snapshot-acquisition-rejected":
        snapshot_acquisition_rejected(args.output_dir, args.candidate)
    else:
        summary = stage(
            parent_path=args.parent,
            proposal_path=args.proposal,
            output_dir=args.output_dir,
        )
        return 0 if summary["status"] == "STAGED" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
