import hashlib
from importlib.resources import files
from pathlib import Path

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

import proprio.adaptive_microscopy_verifier as verifier
from proprio.adaptive_microscopy import (
    AdaptiveMicroscopyController,
    AdaptiveOpenFlexureBackend,
    evaluate_adaptive_microscopy_skill,
)
from proprio.adaptive_microscopy_verifier import (
    MAX_ACQUISITION_SECONDS,
    MAX_TEMPORAL_RSE,
    adaptive_verifier_sha256,
    verify_adaptive_microscopy,
)
from proprio.instrument_types import SimulationScenario


class FakeBackend:
    def __init__(self) -> None:
        y, x = np.indices((256, 256))
        self.sharp = (((x // 8 + y // 8) % 2) * 180 + 40).astype(np.float64)
        self.z = 0
        self.calibration_required = True
        self.capture_index = 0
        self.closed = False

    def clear_buffers(self) -> None: ...
    def prepare_sample(self) -> None: ...

    def set_noise_level(self, value: float) -> None:
        assert value == 2.0

    def move_to(self, x: int, y: int, z: int) -> None:
        assert (x, y) == (0, 0)
        self.z = z

    def calibrate(self) -> None:
        self.calibration_required = False

    def autofocus(self, dz_steps: int) -> dict:
        lower, upper = self.z - dz_steps // 2, self.z + dz_steps // 2
        self.z = 0 if lower <= 0 <= upper else min((lower, upper), key=abs)
        sampled = np.linspace(lower, upper, 50)
        sharpness = 1000.0 + 9000.0 * np.exp(-((sampled / 250.0) ** 2))
        return {
            "selected_z": self.z,
            "sweep_steps": dz_steps,
            "sample_count": len(sampled),
            "jpeg_times": list(np.arange(len(sampled), dtype=float)),
            "jpeg_sizes": list(sharpness),
            "stage_times": [0.0, float(len(sampled) - 1)],
            "stage_positions": [
                {"x": 0, "y": 0, "z": lower},
                {"x": 0, "y": 0, "z": upper},
            ],
        }

    def settle(self) -> None: ...

    def capture(self) -> np.ndarray:
        self.capture_index += 1
        sigma = max(abs(self.z) / 100.0, 0.01)
        frame = gaussian_filter(self.sharp, sigma=sigma)
        return frame + (self.capture_index % 2) * 0.02

    def position(self) -> tuple[int, int, int]:
        return (0, 0, self.z)

    def close(self) -> None:
        self.closed = True


class FakeCameraClient:
    def __init__(self, sample_present: bool) -> None:
        self.sample_present = sample_present
        self.remove_calls = 0
        self.load_calls = 0

    def remove_sample(self) -> None:
        if not self.sample_present:
            raise RuntimeError("Sample is already removed.")
        self.remove_calls += 1
        self.sample_present = False

    def load_sample(self) -> None:
        if self.sample_present:
            raise RuntimeError("Sample is already in place.")
        self.load_calls += 1
        self.sample_present = True


GOOD = """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    first = controller.fast_autofocus(2000)
    if first["position_z"] > 100 or first["position_z"] < -100:
        controller.fast_autofocus(4000)
    controller.settle()
    measurement = controller.capture_focus_series(3)
    controller.release()
    return {"position_z": measurement["position_z"], "repeats": measurement["repeats"]}
"""

BAD = """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus(2000)
    controller.settle()
    measurement = controller.capture_focus_series(2)
    controller.release()
    return {"position_z": measurement["position_z"]}
"""


def _evaluate(source: str, start_z: int):
    return evaluate_adaptive_microscopy_skill(
        source,
        scenario=SimulationScenario.REPAIR,
        controller=AdaptiveMicroscopyController(FakeBackend(), start_z=start_z),
    )


def test_adaptive_microscopy_uses_feedback_and_repeated_measurement() -> None:
    result = _evaluate(GOOD, 1600)
    assert result.verdict == "ADMIT"
    assert result.telemetry["repeat_count"] == 3
    assert len(result.telemetry["frame_sha256s"]) == 3
    assert result.result == {"position_z": 0.0, "repeats": 3.0}
    assert hashlib.sha256(GOOD.encode()).hexdigest() == result.skill_sha256
    resource = next(check for check in result.checks if check.check_id == "acquisition-time-budget")
    assert resource.passed
    assert resource.evidence["observed_seconds"] <= MAX_ACQUISITION_SECONDS


def test_external_sample_preparation_is_idempotent_after_an_interrupted_reset() -> None:
    for sample_present, expected_removals in ((True, 1), (False, 0)):
        backend = object.__new__(AdaptiveOpenFlexureBackend)
        backend.camera = FakeCameraClient(sample_present)
        backend.prepare_sample()
        assert backend.camera.remove_calls == expected_removals
        assert backend.camera.load_calls == 1
        assert backend.camera.sample_present


def test_external_sample_preparation_does_not_hide_unexpected_failures() -> None:
    backend = object.__new__(AdaptiveOpenFlexureBackend)
    backend.camera = FakeCameraClient(True)

    def fail_remove() -> None:
        raise RuntimeError("stage controller unavailable")

    backend.camera.remove_sample = fail_remove
    with pytest.raises(RuntimeError, match="stage controller unavailable"):
        backend.prepare_sample()


def test_adaptive_microscopy_rejects_combined_conservative_repairs() -> None:
    source = """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus(8000)
    controller.settle()
    measurement = controller.capture_focus_series(5)
    controller.release()
    return {"position_z": measurement["position_z"]}
"""
    result = _evaluate(source, 1600)
    check = next(check for check in result.checks if check.check_id == "acquisition-time-budget")
    assert result.verdict == "REJECT"
    assert not check.passed
    assert check.evidence["observed_seconds"] == 8.5


def test_rejected_skill_without_release_still_closes_transport() -> None:
    backend = FakeBackend()
    source = """def run(controller):
    controller.reset()
    return {"status": "incomplete"}
"""
    result = evaluate_adaptive_microscopy_skill(
        source,
        scenario=SimulationScenario.REPAIR,
        controller=AdaptiveMicroscopyController(backend, start_z=800),
    )
    assert result.verdict == "REJECT"
    assert backend.closed


def test_static_rejection_closes_transport() -> None:
    backend = FakeBackend()
    result = evaluate_adaptive_microscopy_skill(
        "def run(controller):\n    return len([])\n",
        scenario=SimulationScenario.REPAIR,
        controller=AdaptiveMicroscopyController(backend, start_z=800),
    )
    assert result.verdict == "REJECT"
    assert backend.closed


def test_adaptive_microscopy_stage_readback_supports_bounded_correction() -> None:
    uncorrected = AdaptiveMicroscopyController(FakeBackend(), start_z=1600, stage_bias_steps=300)
    rejected = evaluate_adaptive_microscopy_skill(
        GOOD,
        scenario=SimulationScenario.REPAIR,
        controller=uncorrected,
    )
    assert rejected.verdict == "REJECT"
    assert not next(
        check for check in rejected.checks if check.check_id == "autofocus-peak-selected"
    ).passed

    corrected_source = """def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    result = controller.fast_autofocus(4000)
    controller.move_z(0 - result["position_z"])
    controller.settle()
    measurement = controller.capture_focus_series(3)
    controller.release()
    return {"position_z": measurement["position_z"]}
"""
    corrected = evaluate_adaptive_microscopy_skill(
        corrected_source,
        scenario=SimulationScenario.REPAIR,
        controller=AdaptiveMicroscopyController(FakeBackend(), start_z=1600, stage_bias_steps=300),
    )
    assert corrected.verdict == "ADMIT"
    assert next(
        check for check in corrected.checks if check.check_id == "acquisition-time-budget"
    ).passed


def test_adaptive_microscopy_rejects_insufficient_repeat_evidence() -> None:
    result = _evaluate(BAD, 1600)
    failures = {check.check_id for check in result.checks if not check.passed}
    assert result.verdict == "REJECT"
    assert "calibrated-focus-reference" in failures
    assert "repeat-count" in failures


def test_absolute_focus_does_not_require_large_gain_from_a_near_focus_baseline() -> None:
    result = _evaluate(GOOD, 800)
    assert result.verdict == "ADMIT"
    assert "fft-focus-improvement" not in {check.check_id for check in result.checks}
    assert all(check.passed for check in result.checks)


def test_temporal_measurement_uncertainty_rejects_noisy_repeats() -> None:
    backend = FakeBackend()
    controller = AdaptiveMicroscopyController(backend, start_z=800)
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus(4000)
    controller.settle()
    base = backend.capture()
    rng = np.random.default_rng(42)
    controller.frames = [base + rng.normal(0.0, 30.0, base.shape) for _ in range(3)]
    controller.frame = controller.frames[-1]
    controller.release()
    checks = {
        check.check_id: check
        for check in verify_adaptive_microscopy(
            controller.observation(),
            tuple(controller.frames),
            tuple(controller.trace),
        )
    }
    assert MAX_TEMPORAL_RSE == 0.011
    assert not checks["temporal-measurement-uncertainty"].passed


def _qualified_controller() -> AdaptiveMicroscopyController:
    controller = AdaptiveMicroscopyController(FakeBackend(), start_z=1600)
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus(4000)
    controller.settle()
    controller.capture_focus_series(3)
    controller.release()
    return controller


def _checks(controller: AdaptiveMicroscopyController):
    return {
        check.check_id: check
        for check in verify_adaptive_microscopy(
            controller.observation(),
            tuple(controller.frames),
            tuple(controller.trace),
        )
    }


def test_autofocus_curve_rejects_truncation_flat_peak_and_peak_mismatch() -> None:
    truncated = _qualified_controller()
    sweep = next(row for row in truncated.trace if row["operation"] == "fast_autofocus")
    sweep["jpeg_times"] = sweep["jpeg_times"][:10]
    sweep["jpeg_sizes"] = sweep["jpeg_sizes"][:10]
    assert not _checks(truncated)["autofocus-curve-complete"].passed

    flat = _qualified_controller()
    sweep = next(row for row in flat.trace if row["operation"] == "fast_autofocus")
    sweep["jpeg_sizes"] = [1000.0] * len(sweep["jpeg_sizes"])
    assert not _checks(flat)["autofocus-peak-prominent"].passed

    mismatch = _qualified_controller()
    sweep = next(row for row in mismatch.trace if row["operation"] == "fast_autofocus")
    sweep["stage_positions"] = [{**row, "z": row["z"] + 500} for row in sweep["stage_positions"]]
    assert not _checks(mismatch)["autofocus-peak-selected"].passed


def test_verifier_identity_binds_code_and_operating_points() -> None:
    digest = hashlib.sha256()
    digest.update(Path(verifier.__file__).read_bytes())
    digest.update(
        files("proprio").joinpath("data/adaptive-microscopy-thresholds.yaml").read_bytes()
    )
    assert adaptive_verifier_sha256() == digest.hexdigest()
