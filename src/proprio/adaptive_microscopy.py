"""OpenFlexure development adapter for bounded adaptive skill search."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from proprio.adaptive_microscopy_verifier import (
    adaptive_verifier_sha256,
    verify_adaptive_microscopy,
)
from proprio.instrument_qualification import compile_instrument_skill
from proprio.instrument_types import GateCheck, HardGateResult, SimulationScenario
from proprio.microscopy import (
    FAMILY,
    INSTRUMENT_ID,
    OPENFLEXURE_REVISION,
    MicroscopyController,
    OpenFlexureBackend,
)

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_METHODS = frozenset(
    {
        "reset",
        "full_auto_calibrate",
        "fast_autofocus",
        "move_z",
        "settle",
        "capture_focus_series",
        "release",
    }
)


def load_adaptive_microscopy_source(instrument_id: str) -> tuple[str, str]:
    if instrument_id != INSTRUMENT_ID:
        raise KeyError(instrument_id)
    checkout = ROOT / "sources" / "development" / instrument_id / "source.md"
    packaged = Path(__file__).with_name("sources") / "development" / instrument_id / "source.md"
    path = checkout if checkout.is_file() else packaged
    text = path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


def _tenengrad(image: np.ndarray) -> float:
    gray = np.asarray(image, dtype=np.float64)
    if gray.ndim == 3:
        gray = 0.2126 * gray[..., 0] + 0.7152 * gray[..., 1] + 0.0722 * gray[..., 2]
    horizontal = np.diff(gray, axis=1)
    vertical = np.diff(gray, axis=0)
    return float(np.mean(horizontal**2) + np.mean(vertical**2))


class AdaptiveMicroscopyController(MicroscopyController):
    """Adds observation-returning actions without exposing simulator internals."""

    def __init__(
        self,
        backend: Any,
        *,
        start_z: int,
        measurement_noise_level: float = 2.0,
        stage_bias_steps: int = 0,
        correction_direction: int = 1,
    ) -> None:
        super().__init__(backend, start_z=start_z)
        self.measurement_noise_level = float(measurement_noise_level)
        self.stage_bias_steps = int(stage_bias_steps)
        if correction_direction not in {-1, 1}:
            raise ValueError("correction direction must be -1 or 1")
        self.correction_direction = int(correction_direction)
        self.frames: list[np.ndarray] = []

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
            autofocus_noise_level=2.0,
            baseline_sha256=hashlib.sha256(self.baseline.tobytes()).hexdigest(),
        )

    def fast_autofocus(self, dz_steps: int) -> dict[str, float]:
        super().fast_autofocus(dz_steps)
        if self.stage_bias_steps:
            x, y, z = self._position
            self.backend.move_to(x, y, z + self.stage_bias_steps)
            self._position = self.backend.position()
            self.trace[-1]["position"] = list(self._position)
        return {"sweep_steps": float(dz_steps), "position_z": float(self._position[2])}

    def move_z(self, delta_steps: int) -> dict[str, float]:
        delta = int(delta_steps)
        if delta < -1000 or delta > 1000:
            raise ValueError("relative z correction must be within -1000 to 1000 steps")
        x, y, z = self._position
        applied_delta = delta * self.correction_direction
        self.backend.move_to(x, y, z + applied_delta)
        self._position = self.backend.position()
        self._log(
            "move_z",
            delta_steps=delta,
            applied_delta_steps=applied_delta,
            position=list(self._position),
        )
        return {"position_z": float(self._position[2])}

    def capture_focus_series(self, repeats: int) -> dict[str, float]:
        count = int(repeats)
        if count < 2 or count > 5:
            raise ValueError("focus series requires two to five repeats")
        if self.baseline is None:
            raise RuntimeError("reset must capture a baseline before a focus series")
        self.backend.set_noise_level(self.measurement_noise_level)
        baseline_score = _tenengrad(self.baseline)
        gains: list[float] = []
        for repeat in range(count):
            frame = self.backend.capture()
            self.frame = frame
            self.frames.append(frame)
            self._position = self.backend.position()
            gain = _tenengrad(frame) / max(baseline_score, 1e-12)
            gains.append(gain)
            self._log(
                "capture_frame",
                repeat=repeat,
                shape=list(frame.shape),
                frame_sha256=hashlib.sha256(frame.tobytes()).hexdigest(),
                position=list(self._position),
            )
        mean = float(np.mean(gains))
        spread = float(np.std(gains, ddof=1) / max(abs(mean), 1e-12))
        return {
            "repeats": float(count),
            "median_focus_gain": float(np.median(gains)),
            "minimum_focus_gain": float(min(gains)),
            "relative_spread": spread,
            "position_z": float(self._position[2]),
        }


class AdaptiveOpenFlexureBackend(OpenFlexureBackend):
    """Prepare the simulated sample without assuming persisted background calibration."""

    def prepare_sample(self) -> None:
        try:
            self.camera.remove_sample()
        except Exception as exc:
            if "Sample is already removed." not in str(exc):
                raise
        try:
            self.camera.load_sample()
        except Exception as exc:
            if "Sample is already in place." not in str(exc):
                raise

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
            "jpeg_times": list(payload.get("jpeg_times", [])),
            "jpeg_sizes": list(payload.get("jpeg_sizes", [])),
            "stage_times": list(payload.get("stage_times", [])),
            "stage_positions": list(payload.get("stage_positions", [])),
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
        verifier_sha256=adaptive_verifier_sha256(),
    )


def evaluate_adaptive_microscopy_skill(
    source: str,
    *,
    scenario: SimulationScenario,
    controller: AdaptiveMicroscopyController,
) -> HardGateResult:
    try:
        function = compile_instrument_skill(source, ALLOWED_METHODS)
    except Exception as exc:
        failure = _static_failure(source, exc, scenario)
        controller.backend.close()
        return failure
    result: dict[str, Any] | None = None
    runtime_error: str | None = None
    try:
        raw = function(controller)
        if not isinstance(raw, dict):
            raise ValueError("run must return a dictionary")
        result = raw
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
    if scenario is SimulationScenario.UNAVAILABLE:
        gate = HardGateResult(
            instrument_id=INSTRUMENT_ID,
            family=FAMILY,
            scenario=scenario,
            verdict="HOLD",
            status="unavailable",
            checks=(
                GateCheck(
                    check_id="simulator-available",
                    passed=False,
                    evidence={"error": runtime_error or "simulator unavailable"},
                ),
            ),
            trace=tuple(controller.trace),
            telemetry=controller.telemetry(),
            result=result,
            runtime_error=runtime_error,
            skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
            simulator_sha256=hashlib.sha256(OPENFLEXURE_REVISION.encode()).hexdigest(),
            verifier_sha256=adaptive_verifier_sha256(),
        )
        if not controller.released:
            controller.backend.close()
        return gate
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
        *verify_adaptive_microscopy(
            controller.observation(),
            tuple(controller.frames),
            tuple(controller.trace),
        ),
    )
    admitted = all(check.passed for check in checks)
    telemetry = {
        **controller.telemetry(),
        "measurement_noise_level": controller.measurement_noise_level,
        "repeat_count": len(controller.frames),
        "frame_sha256s": [
            hashlib.sha256(frame.tobytes()).hexdigest() for frame in controller.frames
        ],
    }
    gate = HardGateResult(
        instrument_id=INSTRUMENT_ID,
        family=FAMILY,
        scenario=scenario,
        verdict="ADMIT" if admitted else "REJECT",
        status="succeeded" if admitted else "failed",
        checks=checks,
        trace=tuple(controller.trace),
        telemetry=telemetry,
        result=result,
        runtime_error=runtime_error,
        skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
        simulator_sha256=hashlib.sha256(OPENFLEXURE_REVISION.encode()).hexdigest(),
        verifier_sha256=adaptive_verifier_sha256(),
    )
    if not controller.released:
        controller.backend.close()
    return gate


def evaluate_live_adaptive_microscopy(
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
        error = "external simulator unavailable"
        return HardGateResult(
            instrument_id=INSTRUMENT_ID,
            family=FAMILY,
            scenario=scenario,
            verdict="HOLD",
            status="unavailable",
            checks=(
                GateCheck(
                    check_id="simulator-available",
                    passed=False,
                    evidence={"error": error},
                ),
            ),
            trace=(),
            telemetry={},
            result=None,
            runtime_error=error,
            skill_sha256=hashlib.sha256(source.encode()).hexdigest(),
            simulator_sha256=hashlib.sha256(OPENFLEXURE_REVISION.encode()).hexdigest(),
            verifier_sha256=adaptive_verifier_sha256(),
        )
    values = dict(condition or {})
    unknown = set(values) - {
        "start_z",
        "measurement_noise_level",
        "stage_bias_steps",
        "correction_direction",
    }
    if unknown:
        raise ValueError(f"unsupported microscope condition fields: {sorted(unknown)}")
    defaults = {
        SimulationScenario.NOMINAL: 800,
        SimulationScenario.REPAIR: 1200,
        SimulationScenario.DRIFT: 1800,
    }
    controller = AdaptiveMicroscopyController(
        AdaptiveOpenFlexureBackend(base_url),
        start_z=int(values.get("start_z", defaults[scenario])),
        measurement_noise_level=float(values.get("measurement_noise_level", 2.0)),
        stage_bias_steps=int(values.get("stage_bias_steps", 0)),
        correction_direction=int(values.get("correction_direction", 1)),
    )
    return evaluate_adaptive_microscopy_skill(
        source,
        scenario=scenario,
        controller=controller,
    )
