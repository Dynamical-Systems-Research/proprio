"""Bluesky/Ophyd execution and procedural fault detection."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
from bluesky import RunEngine
from bluesky import plan_stubs as bps
from ophyd.sim import SynAxis, SynSignal

from proprio.artifacts import source_sha256, write_jsonl
from proprio.schema import (
    ArtifactRef,
    CheckResult,
    OperationAction,
    ProceduralRecord,
    Provenance,
    StatusLabel,
)


class ProceduralFault(StrEnum):
    NONE = "none"
    MOTOR_STALL = "motor_stall"
    TIMEOUT = "timeout"
    ABORTED_PLAN = "aborted_plan"
    DROPPED_FRAME = "dropped_frame"
    UNREACHABLE_SETPOINT = "unreachable_setpoint"


@dataclass(frozen=True)
class ScanConfig:
    start_deg: float = 10.0
    stop_deg: float = 14.0
    points: int = 5
    frame_shape: tuple[int, int] = (32, 32)
    setpoint_tolerance_deg: float = 1e-6


@dataclass(frozen=True)
class ProceduralExecution:
    fault: ProceduralFault
    record: ProceduralRecord
    raw_documents: tuple[dict[str, Any], ...]
    raw_event_stream: ArtifactRef | None
    detected: bool


class SimulatedAreaDetector(SynSignal):
    """Small deterministic area detector backed by ``ophyd.sim``."""

    def __init__(
        self,
        *,
        motor: SynAxis,
        frame_shape: tuple[int, int],
        fault: ProceduralFault,
        name: str = "xrd_detector",
    ) -> None:
        self.motor = motor
        self.frame_shape = frame_shape
        self.fault = fault
        self.point_index = 0
        super().__init__(func=self._frame, name=name)

    def set_point_index(self, index: int) -> None:
        self.point_index = index

    def _frame(self) -> np.ndarray:
        height, width = self.frame_shape
        y, x = np.indices((height, width), dtype=np.float64)
        cy = (height - 1) / 2.0
        cx = (width - 1) / 2.0
        radius = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        target_radius = 6.0 + 0.2 * float(self.motor.position)
        frame = 10.0 + 500.0 * np.exp(-0.5 * ((radius - target_radius) / 0.8) ** 2)
        if self.fault is ProceduralFault.DROPPED_FRAME and self.point_index == 2:
            return frame[: height // 2]
        return frame


def _provenance(*, seed: int | None = None) -> Provenance:
    return Provenance(
        producer="proprio.procedural",
        producer_version="0.1.0",
        seed=seed,
        implementation_sha256=source_sha256(Path(__file__)),
    )


def _action(
    *,
    action_id: str,
    action_type: str,
    command: dict[str, Any],
    observation: dict[str, Any],
    status: StatusLabel,
    reason: str = "",
    logical_index: int,
) -> OperationAction:
    return OperationAction(
        action_id=action_id,
        action_type=action_type,
        command=command,
        observation=observation,
        status=status,
        reason=reason,
        started_logical_ns=logical_index * 100,
        ended_logical_ns=logical_index * 100 + 99,
        provenance=_provenance(),
    )


def _scan_plan(
    *,
    motor: SynAxis,
    detector: SimulatedAreaDetector,
    config: ScanConfig,
    fault: ProceduralFault,
    actions: list[OperationAction],
    operation_id: str,
) -> Generator[Any, Any, None]:
    yield from bps.open_run(
        md={
            "purpose": "proprio-procedural-validation",
            "fault_class": fault.value,
            "expected_points": config.points,
            "proprio_operation_id": operation_id,
        }
    )
    logical_index = 0
    actions.append(
        _action(
            action_id="load-sample",
            action_type="load_sample",
            command={"sample": "synthetic-calibrant"},
            observation={"sample_present": True},
            status=StatusLabel.SUCCEEDED,
            logical_index=logical_index,
        )
    )

    targets = np.linspace(config.start_deg, config.stop_deg, config.points)
    for point_index, target in enumerate(targets):
        logical_index += 1
        if fault is ProceduralFault.UNREACHABLE_SETPOINT and point_index == 1:
            unreachable = config.stop_deg + 1000.0
            actions.append(
                _action(
                    action_id=f"move-{point_index}",
                    action_type="move_goniometer",
                    command={"target_deg": unreachable},
                    observation={"readback_deg": float(motor.position)},
                    status=StatusLabel.FAILED,
                    reason="target is outside the declared simulated travel range",
                    logical_index=logical_index,
                )
            )
            yield from bps.close_run(exit_status="fail", reason="injected unreachable setpoint")
            return
        if fault is ProceduralFault.MOTOR_STALL and point_index == 1:
            actions.append(
                _action(
                    action_id=f"move-{point_index}",
                    action_type="move_goniometer",
                    command={"target_deg": float(target)},
                    observation={"readback_deg": float(motor.position)},
                    status=StatusLabel.FAILED,
                    reason="motor readback did not advance before timeout",
                    logical_index=logical_index,
                )
            )
            yield from bps.close_run(exit_status="fail", reason="injected motor stall")
            return

        yield from bps.mv(motor, float(target))
        readback = float(motor.position)
        move_status = (
            StatusLabel.SUCCEEDED
            if abs(readback - float(target)) <= config.setpoint_tolerance_deg
            else StatusLabel.FAILED
        )
        actions.append(
            _action(
                action_id=f"move-{point_index}",
                action_type="move_goniometer",
                command={"target_deg": float(target)},
                observation={"readback_deg": readback},
                status=move_status,
                reason="" if move_status is StatusLabel.SUCCEEDED else "readback mismatch",
                logical_index=logical_index,
            )
        )

        logical_index += 1
        if fault is ProceduralFault.TIMEOUT and point_index == 1:
            actions.append(
                _action(
                    action_id=f"acquire-{point_index}",
                    action_type="acquire_frame",
                    command={"point_index": point_index},
                    observation={"frame_received": False},
                    status=StatusLabel.FAILED,
                    reason="detector trigger exceeded its acquisition deadline",
                    logical_index=logical_index,
                )
            )
            yield from bps.close_run(exit_status="fail", reason="injected detector timeout")
            return

        detector.set_point_index(point_index)
        readings = yield from bps.trigger_and_read([detector, motor])
        frame = np.asarray(readings[detector.name]["value"])
        actions.append(
            _action(
                action_id=f"acquire-{point_index}",
                action_type="acquire_frame",
                command={"point_index": point_index},
                observation={
                    "frame_received": True,
                    "frame_shape": list(frame.shape),
                },
                status=StatusLabel.SUCCEEDED,
                logical_index=logical_index,
            )
        )

        if fault is ProceduralFault.ABORTED_PLAN and point_index == 1:
            yield from bps.close_run(exit_status="abort", reason="injected partial-plan abort")
            return

    yield from bps.close_run(exit_status="success")


def _check(
    *,
    check_id: str,
    passed: bool,
    summary: str,
    metric_name: str,
    metric_value: float,
    threshold: float,
    comparator: str,
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
        provenance=_provenance(),
    )


def _build_record(
    *,
    documents: list[dict[str, Any]],
    actions: list[OperationAction],
    config: ScanConfig,
) -> ProceduralRecord:
    stop_docs = [row["doc"] for row in documents if row["name"] == "stop"]
    exit_status = str(stop_docs[-1].get("exit_status", "missing")) if stop_docs else "missing"
    run_ok = exit_status == "success"

    events = [row["doc"] for row in documents if row["name"] == "event"]
    event_count_ok = len(events) == config.points
    observed_shapes: list[list[int]] = []
    for event in events:
        frame = np.asarray(event["data"].get("xrd_detector", []))
        observed_shapes.append(list(frame.shape))
    frame_shape_ok = bool(observed_shapes) and all(
        tuple(shape) == config.frame_shape for shape in observed_shapes
    )

    move_actions = [row for row in actions if row.action_type == "move_goniometer"]
    setpoints_ok = bool(move_actions) and all(
        row.status is StatusLabel.SUCCEEDED for row in move_actions
    )

    checks = (
        _check(
            check_id="run-exit-status",
            passed=run_ok,
            summary=f"RunEngine exit_status={exit_status}",
            metric_name="successful_stop",
            metric_value=float(run_ok),
            threshold=1.0,
            comparator="ge",
            details={"exit_status": exit_status},
        ),
        _check(
            check_id="event-count",
            passed=event_count_ok,
            summary=f"received {len(events)} of {config.points} expected events",
            metric_name="event_count",
            metric_value=float(len(events)),
            threshold=float(config.points),
            comparator="ge",
        ),
        _check(
            check_id="frame-shape",
            passed=frame_shape_ok,
            summary="all frames match the declared detector shape"
            if frame_shape_ok
            else "one or more frames are missing or truncated",
            metric_name="shape_valid_fraction",
            metric_value=(
                sum(tuple(shape) == config.frame_shape for shape in observed_shapes) / config.points
            ),
            threshold=1.0,
            comparator="ge",
            details={"observed_shapes": observed_shapes},
        ),
        _check(
            check_id="setpoint-reached",
            passed=setpoints_ok,
            summary="every declared move reached its target"
            if setpoints_ok
            else "at least one target was unreachable or stalled",
            metric_name="successful_move_fraction",
            metric_value=(
                sum(row.status is StatusLabel.SUCCEEDED for row in move_actions)
                / max(1, len(move_actions))
            ),
            threshold=1.0,
            comparator="ge",
        ),
    )
    event_refs = [
        f"event:{int(event.get('seq_num', index + 1))}" for index, event in enumerate(events)
    ]
    stable_actions: list[OperationAction] = []
    for action in actions:
        if action.action_type == "load_sample":
            refs = ("start",)
        elif action.action_id.startswith(("move-", "acquire-")):
            point_index = int(action.action_id.rsplit("-", 1)[1])
            refs = (event_refs[point_index],) if point_index < len(event_refs) else ("stop",)
        else:
            refs = ()
        stable_actions.append(action.model_copy(update={"raw_document_refs": refs}))

    failed = [check for check in checks if check.status is StatusLabel.FAILED]
    if not failed:
        status = StatusLabel.SUCCEEDED
    elif run_ok:
        status = StatusLabel.DEGRADED
    else:
        status = StatusLabel.FAILED
    return ProceduralRecord(status=status, actions=tuple(stable_actions), checks=checks)


def run_procedural(
    *,
    fault: ProceduralFault = ProceduralFault.NONE,
    config: ScanConfig | None = None,
    raw_output: Path | None = None,
    operation_id: str | None = None,
) -> ProceduralExecution:
    """Execute one simulated scan and classify its procedural outcome."""

    config = config or ScanConfig()
    operation_id = operation_id or f"procedural-{fault.value}"
    motor = SynAxis(name="goniometer", value=config.start_deg, egu="degree")
    detector = SimulatedAreaDetector(
        motor=motor,
        frame_shape=config.frame_shape,
        fault=fault,
    )
    actions: list[OperationAction] = []
    documents: list[dict[str, Any]] = []

    def collect(name: str, doc: dict[str, Any]) -> None:
        documents.append({"name": name, "doc": doc})

    engine = RunEngine({})
    engine(
        _scan_plan(
            motor=motor,
            detector=detector,
            config=config,
            fault=fault,
            actions=actions,
            operation_id=operation_id,
        ),
        collect,
    )
    record = _build_record(documents=documents, actions=actions, config=config)
    raw_ref = write_jsonl(raw_output, documents) if raw_output is not None else None
    detected = (
        record.status is StatusLabel.SUCCEEDED
        if fault is ProceduralFault.NONE
        else record.status is not StatusLabel.SUCCEEDED
    )
    return ProceduralExecution(
        fault=fault,
        record=record,
        raw_documents=tuple(documents),
        raw_event_stream=raw_ref,
        detected=detected,
    )


def run_fault_battery(output_dir: Path | None = None) -> dict[str, Any]:
    """Run every procedural failure class and report detection separately."""

    results: list[dict[str, Any]] = []
    for fault in ProceduralFault:
        raw_output = output_dir / f"{fault.value}.raw.jsonl" if output_dir else None
        execution = run_procedural(fault=fault, raw_output=raw_output)
        results.append(
            {
                "fault_class": fault.value,
                "status": execution.record.status.value,
                "detected": execution.detected,
                "failed_checks": [
                    check.check_id
                    for check in execution.record.checks
                    if check.status is StatusLabel.FAILED
                ],
                "raw_event_stream": (
                    execution.raw_event_stream.model_dump(mode="json")
                    if execution.raw_event_stream
                    else None
                ),
            }
        )
    all_detected = all(row["detected"] for row in results)
    return {
        "schema_version": "proprio.procedural_fault_battery.v0.1",
        "all_detected": all_detected,
        "verdict": "PASS" if all_detected else "FAIL",
        "results": results,
    }
