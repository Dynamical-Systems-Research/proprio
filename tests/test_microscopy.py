from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from proprio.instrument_types import SimulationScenario
from proprio.microscopy import MicroscopyController, evaluate_microscope_skill
from proprio.microscopy_metrology import run_microscopy_metrology
from proprio.microscopy_verifier import focus_scores


class FakeMicroscopeBackend:
    def __init__(self, sharp: np.ndarray) -> None:
        self.sharp = sharp
        self.z = 0
        self.calibration_required = True
        self.closed = False

    def clear_buffers(self) -> None:
        return None

    def prepare_sample(self) -> None:
        return None

    def set_noise_level(self, value: float) -> None:
        assert value == 2.0

    def move_to(self, x: int, y: int, z: int) -> None:
        assert (x, y) == (0, 0)
        self.z = z

    def calibrate(self) -> None:
        self.calibration_required = False

    def autofocus(self, dz_steps: int) -> dict:
        lower = self.z - dz_steps // 2
        upper = self.z + dz_steps // 2
        self.z = 0 if lower <= 0 <= upper else min((lower, upper), key=abs)
        return {"selected_z": self.z, "sweep_steps": dz_steps}

    def settle(self) -> None:
        return None

    def capture(self) -> np.ndarray:
        sigma = abs(self.z) / 100.0
        return gaussian_filter(self.sharp, sigma=max(sigma, 0.01))

    def position(self) -> tuple[int, int, int]:
        return (0, 0, self.z)

    def close(self) -> None:
        self.closed = True


def _sharp_image(size: int = 256) -> np.ndarray:
    y, x = np.indices((size, size))
    return (((x // 8 + y // 8) % 2) * 180 + 40).astype(np.float64)


def _source(sweep_steps: int) -> str:
    return f"""def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    controller.fast_autofocus({sweep_steps})
    controller.settle()
    controller.capture_frame()
    controller.release()
    return {{"capture": "focused"}}
"""


def test_independent_focus_implementations_separate_blur() -> None:
    sharp = _sharp_image()
    blurred = gaussian_filter(sharp, sigma=8.0)
    sharp_scores = focus_scores(sharp)
    blurred_scores = focus_scores(blurred)
    assert sharp_scores.fft_high_frequency > blurred_scores.fft_high_frequency * 10
    assert sharp_scores.laplacian_variance > blurred_scores.laplacian_variance * 10


def test_microscope_gate_rejects_an_undersized_sweep() -> None:
    sharp = _sharp_image()
    rejected = evaluate_microscope_skill(
        _source(1600),
        scenario=SimulationScenario.REPAIR,
        controller=MicroscopyController(FakeMicroscopeBackend(sharp), start_z=1200),
    )
    admitted = evaluate_microscope_skill(
        _source(3200),
        scenario=SimulationScenario.REPAIR,
        controller=MicroscopyController(FakeMicroscopeBackend(sharp), start_z=1200),
    )
    assert rejected.verdict == "REJECT"
    assert admitted.verdict == "ADMIT"
    assert "calibrated-focus-reference" in {
        check.check_id for check in rejected.checks if not check.passed
    }


def test_microscopy_metrology_reports_each_invalid_class(tmp_path: Path) -> None:
    sharp = _sharp_image(384)
    before = gaussian_filter(sharp, sigma=8.0)
    underfocused = gaussian_filter(sharp, sigma=3.0)
    summary = run_microscopy_metrology(
        before,
        sharp,
        underfocused,
        output_dir=tmp_path,
        cases_per_class=300,
    )
    assert summary["verdict"] == "PASS"
    assert summary["cases_per_class"] == 300
    assert summary["false_valid"] == 0
    assert summary["false_reject_rate"] <= 0.05
    assert summary["alternate_implementation"]["valid_concordance_rate"] >= 0.90
