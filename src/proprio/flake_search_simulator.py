"""Reduced-order 2D flake-search simulator and bounded controller.

This module deliberately does not import verifier or provider code (mirrors the
separation documented at the top of xrd_generator.py). Ground truth is constructed
purely from a condition's `seed` parameter via `random.Random(seed)` -- no wall clock,
no global RNG (`random.random`/module-level `random` state is never touched).

Frozen-signature conflict, flagged explicitly (not silently resolved):
flake-search-preregistration.yaml's own top-of-file freeze-rationale comment states
"This preregistration keeps that scalar-only discipline for every atom below," and
runs/flake-search/sdd/task-3-brief.md restates "Method args/returns are scalars only,
per the frozen contract." But `controller_atoms.read_chip_state`'s own frozen signature
is `read_chip_state() -> {chip_id: str, state_nonce: int, corner_found: bool}` -- a
compound/dict return -- and `call_budget.nominal_path` counts `read_chip_state` at
exactly 2 calls total (pre-scan + post-scan), which is only arithmetically consistent
with a single call exposing all three fields at once (3 scalar accessors x 2 checks
would cost 6 calls, not 2, breaking the frozen 55-call nominal-path total recomputed in
task-2-report.md). `read_chip_state()` below therefore returns a dict, honoring its own
more specific frozen signature and the frozen call-budget arithmetic over the generic
summary comment's blanket claim. AST allowlist rules confirm dict returns are legal
(ast.Dict/ast.Subscript are both in ALLOWED_NODES; see the YAML's own top-of-file
comment). No frozen value was changed to resolve this; every other atom below is
strictly scalar, matching every other atom's own frozen signature exactly.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from proprio.flake_search_types import (
    DEBRIS_CIRCULARITY_MAX,
    DEBRIS_CONTRAST_MIN,
    DEBRIS_RADIUS_UM_MAX,
    FOCUS_SCORE_MIN,
    KNOWN_CONDITION_PARAMETERS,
    AcquisitionRecord,
    BlobObservation,
    BlobProvenance,
    CandidateRecord,
    DebrisSpec,
    FlakeSpec,
    GeometryConfig,
    ScanStatus,
    load_flake_search_preregistration,
)
from proprio.instrument_types import InstrumentRuntimeUnavailable, SimulationScenario

ALLOWED_METHODS = frozenset(
    {
        "reset",
        "read_chip_state",
        "calibrate_region",
        "move_to_tile",
        "autofocus",
        "capture_tile",
        "get_blob",
        "mark_candidate",
        "strong_blob_count",
        "mark_candidate_from_blob",
        "complete_scan",
        "release",
    }
)

# ---------------------------------------------------------------------------------------
# Noise-budget constants (ledger finding M2). Componentwise derivation of the end-to-end
# reported-vs-true chip-frame coordinate error, worst case, per axis, under the NOMINAL
# (non-fault) path:
#   stage positioning noise:            <= STAGE_NOISE_UM            (5.00 um)
#   tile-frame-to-chip-frame quantization: <= QUANTIZATION_STEP_UM / 2  (0.25 um)
#   corner-detection/homography residual:  <= HOMOGRAPHY_RESIDUAL_UM    (2.00 um)
#   ---------------------------------------------------------------------------
#   worst-case total:                                                  7.25 um
# COORDINATE_TOLERANCE_UM is frozen at 25.0 um (flake_search_types.COORDINATE_TOLERANCE_UM,
# sourced from checks.coordinate-integrity.rule). 7.25 <= 25.0 with a (25.0 - 7.25) / 25.0
# = 71% margin -- these noise magnitudes conform to the frozen tolerance with margin, as
# required. Each component is drawn from a BOUNDED (uniform, not Gaussian) distribution so
# the worst case above is a hard bound, not a statistical one: tests can assert every
# reported coordinate is within tolerance on every draw, not just on average.
STAGE_NOISE_UM = 5.0
QUANTIZATION_STEP_UM = 0.5
HOMOGRAPHY_RESIDUAL_UM = 2.0

# Simulator design choices with no frozen numeric value to derive from (documented so a
# future reader does not mistake these for frozen preregistration content):
NOMINAL_FOCUS_SCORE = 0.95
# illumination_shift is a signed fractional deviation from nominal illumination. The
# preregistration's own two example magnitudes are 0.15 (visible-mild-illumination,
# documented as "in-range but shifted") and 0.85 (locked-illumination-out-of-range,
# documented as "outside the documented in-range band for every tile"). No preregistration
# field gives the exact decision boundary between them; 0.5 sits strictly between the two
# and is not itself a frozen value.
ILLUMINATION_VALID_BAND = 0.5
FLAKE_CIRCULARITY_RANGE = (0.45, 0.95)
DEBRIS_RADIUS_UM_RANGE = (3.0, 15.0)
DEBRIS_CIRCULARITY_RANGE = (0.05, DEBRIS_CIRCULARITY_MAX - 0.01)
DEBRIS_CONTRAST_RANGE = (DEBRIS_CONTRAST_MIN, 0.95)


def _quantize(value: float, step: float) -> float:
    return round(value / step) * step


def _is_clipped(
    chip_x_um: float, chip_y_um: float, radius_um: float, geometry: GeometryConfig
) -> bool:
    x0, y0 = geometry.declared_region_origin_um
    width, height = geometry.declared_region_size_um
    x1, y1 = x0 + width, y0 + height
    return (
        chip_x_um - radius_um < x0
        or chip_x_um + radius_um > x1
        or chip_y_um - radius_um < y0
        or chip_y_um + radius_um > y1
    )


def _force_overlap_band(
    flakes: list[FlakeSpec], rng: random.Random, geometry: GeometryConfig, count: int
) -> list[FlakeSpec]:
    """Place `count` flakes deliberately within the tile-overlap band (dedup stress)."""

    grid_x, _grid_y = geometry.tiling_grid
    tile_w, _tile_h = geometry.tile_size_um
    origin_x, origin_y = geometry.declared_region_origin_um
    _region_w, region_h = geometry.declared_region_size_um
    boundaries_x = [origin_x + index * tile_w for index in range(1, grid_x)]
    band = geometry.tile_overlap_um / 4.0
    updated = list(flakes)
    for index in range(min(count, len(updated))):
        boundary_x = rng.choice(boundaries_x)
        chip_x = boundary_x + rng.uniform(-band, band)
        chip_y = rng.uniform(origin_y, origin_y + region_h)
        updated[index] = updated[index].model_copy(
            update={"chip_x_um": chip_x, "chip_y_um": chip_y}
        )
    return updated


def _force_edge_clipped(
    flakes: list[FlakeSpec], rng: random.Random, geometry: GeometryConfig, count: int
) -> list[FlakeSpec]:
    """Push `count` flakes so their disk crosses the declared-region boundary."""

    x0, y0 = geometry.declared_region_origin_um
    width, height = geometry.declared_region_size_um
    edges = ("left", "right", "top", "bottom")
    updated = list(flakes)
    for index in range(min(count, len(updated))):
        flake = updated[index]
        radius = flake.radius_um
        push = radius * 0.5
        edge = edges[index % len(edges)]
        if edge == "left":
            chip_x, chip_y = x0 + push - radius, rng.uniform(y0, y0 + height)
        elif edge == "right":
            chip_x, chip_y = x0 + width - push + radius, rng.uniform(y0, y0 + height)
        elif edge == "top":
            chip_x, chip_y = rng.uniform(x0, x0 + width), y0 + push - radius
        else:
            chip_x, chip_y = rng.uniform(x0, x0 + width), y0 + height - push + radius
        updated[index] = flake.model_copy(update={"chip_x_um": chip_x, "chip_y_um": chip_y})
    return updated


def _build_population(
    rng: random.Random, geometry: GeometryConfig, parameters: Mapping[str, float]
) -> tuple[tuple[FlakeSpec, ...], tuple[DebrisSpec, ...]]:
    region_x0, region_y0 = geometry.declared_region_origin_um
    region_w, region_h = geometry.declared_region_size_um

    count = rng.randint(*geometry.flake_count_range)
    flakes: list[FlakeSpec] = []
    for index in range(count):
        radius = rng.uniform(*geometry.flake_radius_um_range)
        contrast = rng.uniform(*geometry.flake_contrast_range)
        circularity = rng.uniform(*FLAKE_CIRCULARITY_RANGE)
        chip_x = rng.uniform(region_x0, region_x0 + region_w)
        chip_y = rng.uniform(region_y0, region_y0 + region_h)
        flakes.append(
            FlakeSpec(
                flake_id=f"flake-{index}",
                chip_x_um=chip_x,
                chip_y_um=chip_y,
                radius_um=radius,
                contrast=contrast,
                circularity=circularity,
                clipped=False,
            )
        )

    overlap_target = parameters.get("overlap_band_flake_count")
    if overlap_target is not None:
        flakes = _force_overlap_band(flakes, rng, geometry, int(overlap_target))

    clip_target = parameters.get("min_clipped_flake_count")
    if clip_target is not None:
        flakes = _force_edge_clipped(flakes, rng, geometry, int(clip_target))

    flakes = [
        flake.model_copy(
            update={
                "clipped": _is_clipped(flake.chip_x_um, flake.chip_y_um, flake.radius_um, geometry)
            }
        )
        for flake in flakes
    ]

    debris_count = rng.randint(*geometry.debris_count_range)
    multiplier = parameters.get("debris_count_multiplier")
    if multiplier is not None:
        debris_count = max(debris_count, round(debris_count * float(multiplier)))
    debris: list[DebrisSpec] = []
    for index in range(debris_count):
        radius = rng.uniform(*DEBRIS_RADIUS_UM_RANGE)
        contrast = rng.uniform(*DEBRIS_CONTRAST_RANGE)
        circularity = rng.uniform(*DEBRIS_CIRCULARITY_RANGE)
        chip_x = rng.uniform(region_x0, region_x0 + region_w)
        chip_y = rng.uniform(region_y0, region_y0 + region_h)
        debris.append(
            DebrisSpec(
                debris_id=f"debris-{index}",
                chip_x_um=chip_x,
                chip_y_um=chip_y,
                radius_um=radius,
                contrast=contrast,
                circularity=circularity,
            )
        )
    return tuple(flakes), tuple(debris)


@dataclass(frozen=True)
class _Detection:
    """Private, simulator-internal detection record (never exported directly)."""

    observation: BlobObservation
    provenance: BlobProvenance
    chip_x_um: float
    chip_y_um: float
    radius_um: float
    contrast: float
    clipped: bool
    matched_debris_rule: bool


class FlakeSearchController:
    """Bounded controller over the reduced-order flake-search simulator.

    Constructed from a condition's `parameters` mapping (must include `seed`; may
    include any of the named fault-magnitude keys in KNOWN_CONDITION_PARAMETERS).
    `reset()` deterministically (re)builds ground truth from `random.Random(seed)` and
    must be the first call; every other atom raises RuntimeError if called first.
    """

    def __init__(self, parameters: Mapping[str, float]) -> None:
        unknown = set(parameters) - KNOWN_CONDITION_PARAMETERS
        if unknown:
            raise ValueError(f"unsupported flake-search condition fields: {sorted(unknown)}")
        if "seed" not in parameters:
            raise ValueError("flake-search condition parameters must include 'seed'")
        self._parameters: dict[str, float] = dict(parameters)
        self._seed = int(parameters["seed"])
        prereg = load_flake_search_preregistration()
        self._geometry = prereg.geometry
        self._observation_model = prereg.observation_model

        self.trace: list[dict[str, Any]] = []
        self._initialized = False
        self._closed = False

        self._rng = random.Random(self._seed)
        self._chip_id = ""
        self._initial_state_nonce = 0
        self._corner_found = False
        self._calibrated = False
        self._move_count = 0
        self._current_tile: tuple[int, int] | None = None
        self._focus_score = 0.0
        self._illumination_shift = 0.0
        self._illumination_in_range = True
        self._homography_residual = (0.0, 0.0)
        self._flakes: tuple[FlakeSpec, ...] = ()
        self._debris: tuple[DebrisSpec, ...] = ()
        self._queue: list[CandidateRecord] = []
        self._queue_truth: list[BlobProvenance] = []
        self._marked_queue_indices: set[int] = set()
        self._manifest: list[CandidateRecord] = []
        self._current_blobs: list[BlobObservation] = []
        self._acquisitions: list[AcquisitionRecord] = []
        self._completed = False
        self._status_code: int | None = None
        self._released = False

    def _append(self, operation: str, **details: Any) -> None:
        self.trace.append({"sequence": len(self.trace), "operation": operation, **details})

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("reset() must be called before any other controller method")

    # -- required atoms -------------------------------------------------------------

    def reset(self) -> None:
        """Deterministic re-init to the condition. Must be the first call."""

        self._rng = random.Random(self._seed)
        self._chip_id = f"flake-search-chip-{self._seed}"
        self._initial_state_nonce = 1
        self._corner_found = True
        self._calibrated = False
        self._move_count = 0
        self._current_tile = None
        self._focus_score = float(self._parameters.get("initial_focus_score", NOMINAL_FOCUS_SCORE))
        self._illumination_shift = float(self._parameters.get("illumination_shift", 0.0))
        self._illumination_in_range = abs(self._illumination_shift) < ILLUMINATION_VALID_BAND
        self._homography_residual = (
            self._rng.uniform(-HOMOGRAPHY_RESIDUAL_UM, HOMOGRAPHY_RESIDUAL_UM),
            self._rng.uniform(-HOMOGRAPHY_RESIDUAL_UM, HOMOGRAPHY_RESIDUAL_UM),
        )
        self._flakes, self._debris = _build_population(self._rng, self._geometry, self._parameters)
        self._queue = []
        self._queue_truth = []
        self._marked_queue_indices = set()
        self._manifest = []
        self._current_blobs = []
        self._acquisitions = []
        self._completed = False
        self._status_code = None
        self._released = False
        self._initialized = True
        self._append("reset")

    def read_chip_state(self) -> dict[str, Any]:
        """chip_id/state_nonce/corner_found. See module docstring for the dict-return note."""

        self._require_initialized()
        state = {
            "chip_id": self._chip_id,
            "state_nonce": self._live_state_nonce(),
            "corner_found": self._corner_found,
        }
        self._append("read_chip_state", **state)
        return state

    def calibrate_region(self) -> bool:
        self._require_initialized()
        self._calibrated = True
        self._append("calibrate_region", calibration_ok=True)
        return True

    def move_to_tile(self, ix: int, iy: int) -> bool:
        self._require_initialized()
        low, high = self._geometry.tile_index_range
        in_range = low <= ix <= high and low <= iy <= high
        if not in_range:
            self._append(
                "move_to_tile", ix=ix, iy=iy, arrival=False, fault="tile_index_out_of_range"
            )
            return False
        self._move_count += 1
        decay = self._parameters.get("decay_per_move")
        if decay is not None:
            self._focus_score = max(0.0, self._focus_score - float(decay))
        self._current_tile = (int(ix), int(iy))
        self._append("move_to_tile", ix=ix, iy=iy, arrival=True)
        return True

    def autofocus(self) -> float:
        self._require_initialized()
        self._focus_score = NOMINAL_FOCUS_SCORE
        self._append("autofocus", focus_score=self._focus_score)
        return self._focus_score

    def capture_tile(self) -> int:
        self._require_initialized()
        if self._current_tile is None:
            raise RuntimeError("capture_tile requires a prior move_to_tile")
        ix, iy = self._current_tile
        valid = (
            self._calibrated
            and self._focus_score >= FOCUS_SCORE_MIN
            and self._illumination_in_range
        )
        detections = self._detect_tile(ix, iy)
        self._current_blobs = [detection.observation for detection in detections]
        if valid:
            for detection in detections:
                self._enqueue(detection, ix, iy)
        self._acquisitions.append(
            AcquisitionRecord(
                tile_ix=ix,
                tile_iy=iy,
                valid=valid,
                focus_score=self._focus_score,
                illumination_in_range=self._illumination_in_range,
                calibrated=self._calibrated,
            )
        )
        blob_count = len(detections)
        self._append("capture_tile", blob_count=blob_count, tile_ix=ix, tile_iy=iy, valid=valid)
        return blob_count

    def get_blob(self, index: int, field: str) -> float:
        self._require_initialized()
        if field not in self._observation_model.per_blob_fields:
            raise ValueError(f"unsupported blob field: {field}")
        if index < 0 or index >= len(self._current_blobs):
            raise IndexError("blob index out of range for the most recent capture_tile call")
        value = float(getattr(self._current_blobs[index], field))
        self._append("get_blob", index=index, field=field, value=value)
        return value

    def mark_candidate(
        self, chip_x_um: float, chip_y_um: float, radius_um: float, contrast: float, clipped: bool
    ) -> None:
        self._require_initialized()
        if self._current_tile is None:
            raise RuntimeError("mark_candidate requires a prior move_to_tile")
        ix, iy = self._current_tile
        record = CandidateRecord(
            chip_x_um=float(chip_x_um),
            chip_y_um=float(chip_y_um),
            radius_um=float(radius_um),
            contrast=float(contrast),
            clipped=bool(clipped),
            tile_index=self._tile_index(ix, iy),
            focus_score=self._focus_score,
            source="manual",
        )
        self._manifest.append(record)
        self._append(
            "mark_candidate",
            chip_x_um=record.chip_x_um,
            chip_y_um=record.chip_y_um,
            radius_um=record.radius_um,
            contrast=record.contrast,
            clipped=record.clipped,
        )

    def strong_blob_count(self) -> int:
        self._require_initialized()
        count = len(self._queue)
        self._append("strong_blob_count", count=count)
        return count

    def mark_candidate_from_blob(self, blob_index: int) -> bool:
        self._require_initialized()
        marked = 0 <= blob_index < len(self._queue) and blob_index not in self._marked_queue_indices
        if marked:
            self._manifest.append(self._queue[blob_index])
            self._marked_queue_indices.add(blob_index)
        self._append("mark_candidate_from_blob", blob_index=blob_index, marked=marked)
        return marked

    def complete_scan(self, status_code: int) -> None:
        self._require_initialized()
        if self._completed:
            raise RuntimeError("complete_scan already called")
        code = int(status_code)
        if code not in {status.value for status in ScanStatus}:
            raise ValueError(f"unsupported status_code: {status_code}")
        self._completed = True
        self._status_code = code
        self._append("complete_scan", status_code=code)

    def release(self) -> None:
        self._require_initialized()
        if not self._completed:
            raise RuntimeError("release called before complete_scan")
        if self._released:
            raise RuntimeError("release already called")
        self._released = True
        self._append("release")

    def close(self) -> None:
        """No external transport to release; idempotent no-op, matches MicroscopyController."""

        self._closed = True

    def telemetry(self) -> dict[str, Any]:
        return {
            "chip_id": self._chip_id,
            "initial_state_nonce": self._initial_state_nonce,
            "current_state_nonce": self._live_state_nonce(),
            "calibrated": self._calibrated,
            "focus_score": self._focus_score,
            "illumination_in_range": self._illumination_in_range,
            "queue_size": len(self._queue),
            "manifest_size": len(self._manifest),
            "completed": self._completed,
            "status_code": self._status_code,
            "released": self._released,
            "closed": self._closed,
            "trace_length": len(self.trace),
            "_raw_evidence": {
                "seed": self._seed,
                "flakes": tuple(flake.model_dump() for flake in self._flakes),
                "debris": tuple(item.model_dump() for item in self._debris),
                "chip_pose_timeline": (
                    {
                        "event": "initial",
                        "chip_id": self._chip_id,
                        "state_nonce": self._initial_state_nonce,
                    },
                    {
                        "event": "final",
                        "chip_id": self._chip_id,
                        "state_nonce": self._live_state_nonce(),
                    },
                ),
                "acquisition_timeline": tuple(item.model_dump() for item in self._acquisitions),
                "manifest": tuple(item.model_dump() for item in self._manifest),
                "queue": tuple(item.model_dump() for item in self._queue),
                "queue_truth": tuple(item.model_dump() for item in self._queue_truth),
                "released": self._released,
            },
        }

    # -- internals --------------------------------------------------------------

    def _live_state_nonce(self) -> int:
        swap_after = self._parameters.get("swap_after_tile_index")
        swapped = swap_after is not None and self._move_count > swap_after
        return self._initial_state_nonce + (1 if swapped else 0)

    def _tile_index(self, ix: int, iy: int) -> int:
        grid_x, _grid_y = self._geometry.tiling_grid
        return iy * grid_x + ix

    def _apply_calibration_fault(self, chip_x_um: float, chip_y_um: float) -> tuple[float, float]:
        if self._calibrated:
            return chip_x_um, chip_y_um
        offset_x = self._parameters.get("offset_x_um")
        offset_y = self._parameters.get("offset_y_um")
        if offset_x is not None or offset_y is not None:
            return chip_x_um + float(offset_x or 0.0), chip_y_um + float(offset_y or 0.0)
        mirror_axis = self._parameters.get("mirror_axis")
        if mirror_axis == 2.0:
            return chip_x_um, self._geometry.chip_size_um[1] - chip_y_um
        if mirror_axis == 1.0:
            return self._geometry.chip_size_um[0] - chip_x_um, chip_y_um
        return chip_x_um, chip_y_um

    def _make_detection(
        self,
        *,
        object_id: str,
        true_x: float,
        true_y: float,
        radius: float,
        contrast: float,
        circularity: float,
        clipped: bool,
        is_debris_truth: bool,
        ix: int,
        iy: int,
        physical_origin: tuple[float, float],
        nominal_origin: tuple[float, float],
    ) -> _Detection:
        tile_frame_x_true = true_x - physical_origin[0]
        tile_frame_y_true = true_y - physical_origin[1]
        stage_noise_x = self._rng.uniform(-STAGE_NOISE_UM, STAGE_NOISE_UM)
        stage_noise_y = self._rng.uniform(-STAGE_NOISE_UM, STAGE_NOISE_UM)
        tile_frame_x = _quantize(tile_frame_x_true + stage_noise_x, QUANTIZATION_STEP_UM)
        tile_frame_y = _quantize(tile_frame_y_true + stage_noise_y, QUANTIZATION_STEP_UM)

        chip_x = nominal_origin[0] + tile_frame_x + self._homography_residual[0]
        chip_y = nominal_origin[1] + tile_frame_y + self._homography_residual[1]
        chip_x, chip_y = self._apply_calibration_fault(chip_x, chip_y)

        # Derive the get_blob-exposed tile-frame reading FROM the (possibly faulted)
        # chip-frame value, not the other way around. observation_model.valid_
        # acquisition_rule gates queue accumulation on calibration, so an uncalibrated
        # capture's queue-side chip-frame value is never read. Without this derivation,
        # the origin-offset/mirror fault would be unobservable through ANY call
        # sequence: the recommended path only ever queues calibrated (fault-free)
        # captures, and get_blob's tile-frame reading would otherwise stay accurate
        # regardless of calibration. Deriving it this way keeps get_blob and the
        # queue/manifest mutually consistent and makes the fault observable through the
        # manual get_blob()+mark_candidate() escape hatch, which has no validity gate.
        exposed_tile_frame_x = chip_x - nominal_origin[0]
        exposed_tile_frame_y = chip_y - nominal_origin[1]

        matched_debris_rule = contrast >= DEBRIS_CONTRAST_MIN and (
            circularity < DEBRIS_CIRCULARITY_MAX or radius < DEBRIS_RADIUS_UM_MAX
        )
        observation = BlobObservation(
            x_um=exposed_tile_frame_x,
            y_um=exposed_tile_frame_y,
            radius_um=radius,
            contrast=contrast,
            circularity=circularity,
        )
        provenance = BlobProvenance(
            tile_ix=ix,
            tile_iy=iy,
            true_object_id=object_id,
            is_debris_truth=is_debris_truth,
            matched_debris_rule=matched_debris_rule,
        )
        return _Detection(
            observation=observation,
            provenance=provenance,
            chip_x_um=chip_x,
            chip_y_um=chip_y,
            radius_um=radius,
            contrast=contrast,
            clipped=clipped,
            matched_debris_rule=matched_debris_rule,
        )

    def _detect_tile(self, ix: int, iy: int) -> list[_Detection]:
        tile_w, tile_h = self._geometry.tile_size_um
        origin_x, origin_y = self._geometry.declared_region_origin_um
        nominal_origin = (origin_x + ix * tile_w, origin_y + iy * tile_h)
        backlash_x = float(self._parameters.get("backlash_x_um", 0.0))
        physical_origin = (nominal_origin[0] + backlash_x, nominal_origin[1])

        half_overlap = self._geometry.tile_overlap_um / 2.0
        x_min = physical_origin[0] - half_overlap
        x_max = physical_origin[0] + tile_w + half_overlap
        y_min = physical_origin[1] - half_overlap
        y_max = physical_origin[1] + tile_h + half_overlap

        detections: list[_Detection] = []
        for flake in self._flakes:
            if x_min <= flake.chip_x_um <= x_max and y_min <= flake.chip_y_um <= y_max:
                detections.append(
                    self._make_detection(
                        object_id=flake.flake_id,
                        true_x=flake.chip_x_um,
                        true_y=flake.chip_y_um,
                        radius=flake.radius_um,
                        contrast=flake.contrast,
                        circularity=flake.circularity,
                        clipped=flake.clipped,
                        is_debris_truth=False,
                        ix=ix,
                        iy=iy,
                        physical_origin=physical_origin,
                        nominal_origin=nominal_origin,
                    )
                )
        for item in self._debris:
            if x_min <= item.chip_x_um <= x_max and y_min <= item.chip_y_um <= y_max:
                detections.append(
                    self._make_detection(
                        object_id=item.debris_id,
                        true_x=item.chip_x_um,
                        true_y=item.chip_y_um,
                        radius=item.radius_um,
                        contrast=item.contrast,
                        circularity=item.circularity,
                        clipped=False,
                        is_debris_truth=True,
                        ix=ix,
                        iy=iy,
                        physical_origin=physical_origin,
                        nominal_origin=nominal_origin,
                    )
                )
        return detections

    def _enqueue(self, detection: _Detection, ix: int, iy: int) -> None:
        if detection.matched_debris_rule:
            return
        merge_radius = self._geometry.dedup_merge_radius_um
        for existing in self._queue:
            dx = existing.chip_x_um - detection.chip_x_um
            dy = existing.chip_y_um - detection.chip_y_um
            if (dx * dx + dy * dy) ** 0.5 <= merge_radius:
                return
        record = CandidateRecord(
            chip_x_um=detection.chip_x_um,
            chip_y_um=detection.chip_y_um,
            radius_um=detection.radius_um,
            contrast=detection.contrast,
            clipped=detection.clipped,
            tile_index=self._tile_index(ix, iy),
            focus_score=self._focus_score,
            source="recommended",
        )
        self._queue.append(record)
        self._queue_truth.append(detection.provenance)


def build_flake_search_controller(
    scenario: SimulationScenario, parameters: Mapping[str, float]
) -> FlakeSearchController:
    """Construct a bounded controller for one condition, or fail closed on UNAVAILABLE.

    Mirrors every existing built-in provider's `controller_factory` convention
    (xrd_provider/keithley_provider/openflexure_provider in builtin_providers.py, none
    of which this task may modify): SimulationScenario.UNAVAILABLE must raise
    InstrumentRuntimeUnavailable so instrument_plugins.py converts the outcome to HOLD,
    never REJECT/ADMIT. Other scenario values (NOMINAL/REPAIR/DRIFT) are not given any
    additional special-cased behavior here, matching keithley_provider's
    controller_factory precedent (builtin_providers.py:160-168) most closely: every
    flake-search fault is already fully driven by named `parameters` keys (see
    KNOWN_CONDITION_PARAMETERS), so `scenario` carries no extra fault-selection duty of
    its own for this instrument. This function is the future flake_search_provider()'s
    controller_factory body; it lives here (not in builtin_providers.py) only because
    this task's scope excludes touching that file -- a later task will import and wire
    it in.
    """

    if scenario is SimulationScenario.UNAVAILABLE:
        raise InstrumentRuntimeUnavailable("flake-search simulator is unavailable")
    return FlakeSearchController(parameters)
