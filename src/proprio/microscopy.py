"""External OpenFlexure simulator adapter and microscope skill qualification."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from proprio.artifacts import source_sha256, write_canonical_json
from proprio.instrument_qualification import compile_instrument_skill
from proprio.instrument_types import GateCheck, HardGateResult, SimulationScenario
from proprio.microscopy_verifier import MicroscopyObservation, verify_microscopy_observation

INSTRUMENT_ID = "microscope-autofocus"
FAMILY = "optical_microscopy"
OPENFLEXURE_REVISION = "d26b93e1be1093e9d696b634dd1f7dde3bb7142a"
ALLOWED_METHODS = frozenset(
    {
        "reset",
        "full_auto_calibrate",
        "fast_autofocus",
        "settle",
        "capture_frame",
        "release",
    }
)
START_Z = {
    SimulationScenario.NOMINAL: 800,
    SimulationScenario.REPAIR: 1200,
    SimulationScenario.DRIFT: 1800,
    SimulationScenario.UNAVAILABLE: 800,
}
ROOT = Path(__file__).resolve().parents[2]


def load_microscopy_source(instrument_id: str) -> tuple[str, str]:
    if instrument_id != INSTRUMENT_ID:
        raise KeyError(instrument_id)
    checkout = ROOT / "sources" / "confirmatory" / instrument_id / "source.md"
    packaged = Path(__file__).with_name("sources") / "confirmatory" / instrument_id / "source.md"
    path = checkout if checkout.is_file() else packaged
    text = path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


class MicroscopeBackend(Protocol):
    calibration_required: bool

    def clear_buffers(self) -> None: ...

    def prepare_sample(self) -> None: ...

    def set_noise_level(self, value: float) -> None: ...

    def move_to(self, x: int, y: int, z: int) -> None: ...

    def calibrate(self) -> None: ...

    def autofocus(self, dz_steps: int) -> dict[str, Any]: ...

    def settle(self) -> None: ...

    def capture(self) -> np.ndarray: ...

    def position(self) -> tuple[int, int, int]: ...

    def close(self) -> None: ...


class OpenFlexureBackend:
    """Thin client over the public OpenFlexure LabThings API."""

    def __init__(self, base_url: str) -> None:
        try:
            import labthings_fastapi as lt
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - exercised in the external lane
            raise RuntimeError(
                "OpenFlexure live qualification requires the 'openflexure' optional dependencies"
            ) from exc
        self._image_type = Image
        prefix = base_url.rstrip("/") + "/api/v3"
        self.camera = lt.ThingClient.from_url(prefix + "/camera/")
        self.stage = lt.ThingClient.from_url(prefix + "/stage/")
        self.autofocus_client = lt.ThingClient.from_url(prefix + "/autofocus/")

    @property
    def calibration_required(self) -> bool:
        return bool(self.camera.calibration_required)

    def clear_buffers(self) -> None:
        self.camera.clear_buffers()

    def prepare_sample(self) -> None:
        sample, _ = self.camera.image_is_sample()
        if not sample:
            self.camera.load_sample()

    def set_noise_level(self, value: float) -> None:
        self.camera.set_property("noise_level", float(value))

    def move_to(self, x: int, y: int, z: int) -> None:
        self.stage.move_to_xyz_position(xyz_pos=[int(x), int(y), int(z)])

    def calibrate(self) -> None:
        self.camera.full_auto_calibrate()

    def autofocus(self, dz_steps: int) -> dict[str, Any]:
        payload = self.autofocus_client.fast_autofocus(
            dz=int(dz_steps),
            start="centre",
            sharpness_metric=1,
            record=1,
        )
        return {
            "sweep_steps": int(dz_steps),
            "sample_count": len(payload.get("jpeg_sizes", [])),
        }

    def settle(self) -> None:
        self.camera.settle()

    def capture(self) -> np.ndarray:
        image = self._image_type.open(self.camera.grab_jpeg().open())
        return np.asarray(image.convert("RGB"), dtype=np.float64)

    def position(self) -> tuple[int, int, int]:
        return tuple(int(value) for value in self.stage.get_xyz_position())

    def close(self) -> None:
        seen: set[int] = set()
        for thing in (self.camera, self.stage, self.autofocus_client):
            client = thing.client
            if id(client) in seen:
                continue
            seen.add(id(client))
            close = getattr(client, "close", None)
            if callable(close):
                close()


class MicroscopyController:
    def __init__(self, backend: MicroscopeBackend, *, start_z: int) -> None:
        self.backend = backend
        self.start_z = int(start_z)
        self.trace: list[dict[str, Any]] = []
        self.baseline: np.ndarray | None = None
        self.frame: np.ndarray | None = None
        self.calibrated = False
        self.released = False
        self._position = (0, 0, self.start_z)

    def _log(self, operation: str, **values: Any) -> None:
        self.trace.append({"sequence": len(self.trace), "operation": operation, **values})

    def reset(self) -> None:
        self.backend.clear_buffers()
        self.backend.prepare_sample()
        self.backend.set_noise_level(2.0)
        self.backend.move_to(0, 0, self.start_z)
        self.backend.settle()
        self.baseline = self.backend.capture()
        self._position = self.backend.position()
        self._log(
            "reset",
            start_position=list(self._position),
            baseline_sha256=hashlib.sha256(self.baseline.tobytes()).hexdigest(),
        )

    def full_auto_calibrate(self) -> None:
        self.backend.calibrate()
        self.calibrated = not self.backend.calibration_required
        self._log("full_auto_calibrate", calibration_required=not self.calibrated)

    def fast_autofocus(self, dz_steps: int) -> None:
        result = self.backend.autofocus(int(dz_steps))
        self._position = self.backend.position()
        self._log("fast_autofocus", dz_steps=int(dz_steps), position=list(self._position), **result)

    def settle(self) -> None:
        self.backend.settle()
        self._log("settle")

    def capture_frame(self) -> None:
        self.frame = self.backend.capture()
        self._position = self.backend.position()
        self._log(
            "capture_frame",
            shape=list(self.frame.shape),
            frame_sha256=hashlib.sha256(self.frame.tobytes()).hexdigest(),
            position=list(self._position),
        )

    def release(self) -> None:
        self.backend.clear_buffers()
        self._position = self.backend.position()
        self.backend.close()
        self.released = True
        self._log("release")

    def observation(self) -> MicroscopyObservation:
        return MicroscopyObservation(
            baseline=self.baseline,
            frame=self.frame,
            operations=tuple(str(row["operation"]) for row in self.trace),
            calibrated=self.calibrated,
            released=self.released,
            final_z=self._position[2],
        )

    def telemetry(self) -> dict[str, Any]:
        return {
            "start_z": self.start_z,
            "position": list(self._position),
            "calibrated": self.calibrated,
            "released": self.released,
            "baseline_shape": None if self.baseline is None else list(self.baseline.shape),
            "frame_shape": None if self.frame is None else list(self.frame.shape),
            "baseline_sha256": None
            if self.baseline is None
            else hashlib.sha256(self.baseline.tobytes()).hexdigest(),
            "frame_sha256": None
            if self.frame is None
            else hashlib.sha256(self.frame.tobytes()).hexdigest(),
        }


def _static_failure(source: str, exc: Exception, scenario: SimulationScenario) -> HardGateResult:
    error = f"{type(exc).__name__}: {exc}"
    return HardGateResult(
        instrument_id=INSTRUMENT_ID,
        family=FAMILY,
        scenario=scenario,
        verdict="REJECT",
        status="failed",
        checks=(GateCheck(check_id="static-safety", passed=False, evidence={"error": error}),),
        trace=(),
        telemetry={},
        result=None,
        runtime_error=error,
        skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
        simulator_sha256=hashlib.sha256(OPENFLEXURE_REVISION.encode()).hexdigest(),
        verifier_sha256=source_sha256(Path(__file__).with_name("microscopy_verifier.py")),
    )


def evaluate_microscope_skill(
    source: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    controller: MicroscopyController,
) -> HardGateResult:
    """Execute one skill and qualify only exported trace and image evidence."""

    try:
        function = compile_instrument_skill(source, ALLOWED_METHODS)
    except Exception as exc:
        return _static_failure(source, exc, scenario)
    result: dict[str, Any] | None = None
    runtime_error: str | None = None
    try:
        raw = function(controller)
        if not isinstance(raw, dict):
            raise ValueError("run must return a dictionary")
        result = raw
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
    checks = (
        GateCheck(
            check_id="static-safety",
            passed=True,
            evidence={"allowed_methods": sorted(ALLOWED_METHODS)},
        ),
        GateCheck(
            check_id="runtime-completed",
            passed=runtime_error is None,
            evidence={"error": runtime_error},
        ),
        *verify_microscopy_observation(controller.observation()),
    )
    admitted = all(check.passed for check in checks)
    return HardGateResult(
        instrument_id=INSTRUMENT_ID,
        family=FAMILY,
        scenario=scenario,
        verdict="ADMIT" if admitted else "REJECT",
        status="succeeded" if admitted else "failed",
        checks=checks,
        trace=tuple(controller.trace),
        telemetry=controller.telemetry(),
        result=result,
        runtime_error=runtime_error,
        skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
        simulator_sha256=hashlib.sha256(OPENFLEXURE_REVISION.encode()).hexdigest(),
        verifier_sha256=source_sha256(Path(__file__).with_name("microscopy_verifier.py")),
    )


def evaluate_live_microscopy_skill(
    instrument_id: str,
    source: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    condition: Mapping[str, float] | None = None,
    base_url: str = "http://127.0.0.1:5100",
) -> HardGateResult:
    if instrument_id != INSTRUMENT_ID:
        raise KeyError(instrument_id)
    if scenario is SimulationScenario.UNAVAILABLE:
        error = RuntimeError("external OpenFlexure simulator unavailable")
        failed = _static_failure(source, error, scenario)
        return failed.model_copy(update={"verdict": "HOLD", "status": "unavailable"})
    values = dict(condition or {})
    unknown = set(values) - {"start_z"}
    if unknown:
        raise ValueError(f"unsupported microscope condition fields: {sorted(unknown)}")
    start_z = int(values.get("start_z", START_Z[scenario]))
    controller = MicroscopyController(OpenFlexureBackend(base_url), start_z=start_z)
    return evaluate_microscope_skill(source, scenario=scenario, controller=controller)


def capture_live_microscopy_reference(
    output_dir: Path,
    *,
    base_url: str = "http://127.0.0.1:5100",
) -> dict[str, Any]:
    """Capture raw external-simulator frames for verifier metrology and inspection."""

    def source(dz_steps: int) -> str:
        return f"""def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus({dz_steps})
    controller.settle()
    controller.capture_frame()
    controller.release()
    return {{"capture": "focused"}}
"""

    output_dir.mkdir(parents=True, exist_ok=True)
    under_controller = MicroscopyController(OpenFlexureBackend(base_url), start_z=1200)
    under_gate = evaluate_microscope_skill(
        source(2000),
        scenario=SimulationScenario.REPAIR,
        controller=under_controller,
    )
    focused_controller = MicroscopyController(OpenFlexureBackend(base_url), start_z=1200)
    focused_gate = evaluate_microscope_skill(
        source(3200),
        scenario=SimulationScenario.REPAIR,
        controller=focused_controller,
    )
    frames = {
        "baseline": under_controller.baseline,
        "underfocused": under_controller.frame,
        "focused": focused_controller.frame,
    }
    if any(frame is None for frame in frames.values()):
        raise RuntimeError("OpenFlexure reference capture did not produce all required frames")
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - external lane dependency
        raise RuntimeError("reference PNG export requires Pillow") from exc
    frame_rows = {}
    for name, value in frames.items():
        assert value is not None
        np.save(output_dir / f"{name}.npy", value, allow_pickle=False)
        Image.fromarray(np.clip(value, 0, 255).astype(np.uint8)).save(output_dir / f"{name}.png")
        frame_rows[name] = {
            "shape": list(value.shape),
            "sha256": hashlib.sha256(value.tobytes()).hexdigest(),
        }
    summary = {
        "schema_version": "proprio.microscopy_reference_capture.v0.1",
        "simulator_revision": OPENFLEXURE_REVISION,
        "base_url": base_url,
        "frames": frame_rows,
        "undersized_sweep": under_gate.model_dump(mode="json"),
        "expanded_sweep": focused_gate.model_dump(mode="json"),
        "verdict": "PASS"
        if under_gate.verdict == "REJECT" and focused_gate.verdict == "ADMIT"
        else "FAIL",
    }
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
