"""Shared data-only types for XRD generation and verification engines."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import files
from typing import Any

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field


class ValidityFault(StrEnum):
    VALID = "valid"
    GEOMETRY_MISCALIBRATION = "geometry_miscalibration"
    ZERO_SHIFT = "zero_shift"
    SAMPLE_DISPLACEMENT = "sample_displacement"
    SATURATION = "saturation"
    DEAD_TIME = "dead_time"
    INSUFFICIENT_COUNTS = "insufficient_counts"
    CAKE_INTEGRATION_FAILURE = "cake_integration_failure"
    UNINDEXED_PEAK = "unindexed_peak"
    CHI2_LOWER_TAIL = "chi2_lower_tail"


class XRDGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    geometry_id: str
    shape: tuple[int, int]
    pixel_size_m: float = Field(gt=0)
    distance_m: float = Field(gt=0)
    center_y_px: float
    center_x_px: float
    wavelength_m: float = Field(gt=0)
    detector_max_counts: float = Field(gt=0)
    exposure_s: float = Field(gt=0)
    radial_range_deg: tuple[float, float]
    radial_bins: int = Field(gt=32)


class FrameTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    exposure_s: float = Field(gt=0)
    real_time_s: float = Field(gt=0)
    live_time_s: float = Field(gt=0)
    detector_max_counts: float = Field(gt=0)
    reported_variance_scale: float = Field(gt=0)
    telemetry_available: bool = True


class SyntheticTruth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    calibrant: str
    fault_class: ValidityFault
    expected_valid: bool
    seed: int
    injected_parameters: dict[str, float]


@dataclass(frozen=True)
class SyntheticFrame:
    frame: np.ndarray
    geometry: XRDGeometry
    telemetry: FrameTelemetry
    truth: SyntheticTruth


def load_preregistration() -> dict[str, Any]:
    resource = files("proprio").joinpath("data/metrology-preregistration.yaml")
    return yaml.safe_load(resource.read_text(encoding="utf-8"))


def geometry_from_preregistration(config: dict[str, Any] | None = None) -> XRDGeometry:
    config = config or load_preregistration()
    return XRDGeometry.model_validate(config["instrument"])
