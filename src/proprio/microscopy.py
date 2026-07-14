"""OpenFlexure public API adapter and bounded microscope controller."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

import numpy as np

from proprio.microscopy_verifier import MicroscopyObservation

INSTRUMENT_ID = "microscope-autofocus"
FAMILY = "optical_microscopy"
OPENFLEXURE_REVISION = "d26b93e1be1093e9d696b634dd1f7dde3bb7142a"


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

    def close(self) -> None:
        """Close an unreleased transport without falsifying the release check."""

        if not self.released:
            self.backend.close()

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
