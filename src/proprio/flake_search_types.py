"""Shared data-only types for flake-search generation, verification, and providers.

Mirrors ``proprio.xrd_types``: dependency-light data models shared by the simulator,
verifier, and provider adapter. This module imports nothing from any of those.

``FlakeSearchPreregistration.conditions`` carries locked-only content (seed, fault_code,
fault magnitudes) that must never reach a drafting agent. ``ContractGeometry`` and
``ContractObservationModel`` omit that field entirely, so no accessor built on them can
leak it.
"""

from __future__ import annotations

from enum import IntEnum
from functools import cache
from importlib.resources import files
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# These five numbers exist only as prose in flake-search-preregistration.yaml (no
# structured thresholds block to read), so they are mirrored here verbatim. Do not tune:
# test_flake_search_simulator.py regex-extracts the same numbers from the raw YAML text
# and asserts equality, so drift between the two fails loudly.

# geometry.debris_population.signature / observation_model.debris_rule:
# "contrast >= 0.30 AND (circularity < 0.35 OR radius_um < 12.0)"
DEBRIS_CONTRAST_MIN = 0.30
DEBRIS_CIRCULARITY_MAX = 0.35
DEBRIS_RADIUS_UM_MAX = 12.0

# controller_atoms.autofocus.notes / observation_model.valid_acquisition_rule /
# checks.focus-validity.rule: "focus_score >= 0.70"
FOCUS_SCORE_MIN = 0.70

# checks.coordinate-integrity.rule: "abs(reported_chip_position - true_chip_position)
# <= 25.0 um"
COORDINATE_TOLERANCE_UM = 25.0

# Every parameter key any condition in the frozen preregistration supplies. Fault
# injection is driven only by the presence of these named keys, never a categorical
# switch -- see flake_search_simulator.py.
KNOWN_CONDITION_PARAMETERS: frozenset[str] = frozenset(
    {
        "seed",
        "fault_code",
        "swap_after_tile_index",
        "offset_x_um",
        "offset_y_um",
        "mirror_axis",
        "illumination_shift",
        "debris_count_multiplier",
        "min_clipped_flake_count",
        "decay_per_move",
        "overlap_band_flake_count",
        "backlash_x_um",
        "initial_focus_score",
    }
)


class ScanStatus(IntEnum):
    """Mirrors observation_model.status_codes exactly (frozen, contract-visible)."""

    COMPLETE = 0
    ABORTED_STALE_CHIP = 1
    ABORTED_FOCUS_INVALID = 2
    ABORTED_ILLUMINATION = 3
    INCOMPLETE = 4


class ChipState(BaseModel):
    """Return shape of the `read_chip_state()` atom.

    The one atom whose frozen signature specifies a compound return rather than a
    scalar -- see flake_search_simulator.py's module docstring.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chip_id: str
    state_nonce: int
    corner_found: bool


class FlakeSpec(BaseModel):
    """Constructed ground-truth flake (simulator/verifier-only; never in .trace)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    flake_id: str
    chip_x_um: float
    chip_y_um: float
    radius_um: float = Field(gt=0)
    contrast: float = Field(ge=0, le=1)
    circularity: float = Field(ge=0, le=1)
    clipped: bool


class DebrisSpec(BaseModel):
    """Constructed ground-truth debris object (simulator/verifier-only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    debris_id: str
    chip_x_um: float
    chip_y_um: float
    radius_um: float = Field(gt=0)
    contrast: float = Field(ge=0, le=1)
    circularity: float = Field(ge=0, le=1)


class BlobObservation(BaseModel):
    """Tile-frame per-blob reading exposed by `get_blob(index, field)`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    x_um: float
    y_um: float
    radius_um: float = Field(gt=0)
    contrast: float = Field(ge=0, le=1)
    circularity: float = Field(ge=0, le=1)


class BlobProvenance(BaseModel):
    """Simulator-internal, verifier-only truth about one detected blob.

    Never surfaced through `get_blob`/`mark_candidate_from_blob`; carried only inside
    `telemetry()["_raw_evidence"]` for the verifier.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tile_ix: int
    tile_iy: int
    true_object_id: str
    is_debris_truth: bool
    matched_debris_rule: bool


class AcquisitionRecord(BaseModel):
    """One capture_tile() entry in the acquisition-validity timeline (raw evidence)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tile_ix: int
    tile_iy: int
    valid: bool
    focus_score: float
    illumination_in_range: bool
    calibrated: bool


class CandidateRecord(BaseModel):
    """One chip-wide queue slot or manifest entry: controller-computed candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chip_x_um: float
    chip_y_um: float
    radius_um: float = Field(gt=0)
    contrast: float = Field(ge=0, le=1)
    clipped: bool
    tile_index: int = Field(ge=0)
    focus_score: float
    source: Literal["recommended", "manual"]


class GeometryConfig(BaseModel):
    """Typed geometry, sourced from clean structured YAML fields (not prose)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chip_size_um: tuple[float, float]
    coordinate_origin: str
    declared_region_origin_um: tuple[float, float]
    declared_region_size_um: tuple[float, float]
    tiling_grid: tuple[int, int]
    tile_size_um: tuple[float, float]
    tile_index_range: tuple[int, int]
    tile_overlap_um: float = Field(ge=0)
    flake_count_range: tuple[int, int]
    flake_radius_um_range: tuple[float, float]
    flake_contrast_range: tuple[float, float]
    debris_count_range: tuple[int, int]
    detectability_contrast_min: float = Field(ge=0, le=1)
    detectability_radius_um_min: float = Field(gt=0)
    dedup_merge_radius_um: float = Field(gt=0)


class ObservationModelConfig(BaseModel):
    """Typed observation-model thresholds (mix of clean fields and frozen-prose mirrors)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    per_blob_fields: tuple[str, ...]
    debris_contrast_min: float
    debris_circularity_max: float
    debris_radius_um_max: float
    focus_score_min: float
    coordinate_tolerance_um: float
    status_codes: dict[int, str]


class ConditionSpec(BaseModel):
    """One condition_id/scenario/parameters/repetitions tuple, mirroring DebugCondition.

    Locked-only content (seed, fault_code, fault magnitudes) lives in `parameters` here.
    This type is deliberately NOT reachable from `contract_geometry`/
    `contract_observation_model` -- see the module docstring.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: str
    scenario: str
    parameters: dict[str, float]
    repetitions: int = Field(ge=1, le=7)


class FlakeSearchPreregistration(BaseModel):
    """Full, simulator/verifier-side view of the frozen preregistration.

    `conditions` carries locked-only content. Never pass this whole object, or its
    `conditions` field, to anything that builds drafting-visible content -- use
    `contract_geometry`/`contract_observation_model` for that instead.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    geometry: GeometryConfig
    observation_model: ObservationModelConfig
    conditions: dict[str, tuple[ConditionSpec, ...]]


class ContractGeometry(BaseModel):
    """Drafting-visible geometry subset only -- exactly the contract_visible: true fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chip_size_um: tuple[float, float]
    coordinate_origin: str
    declared_region_origin_um: tuple[float, float]
    declared_region_size_um: tuple[float, float]
    tiling_grid: tuple[int, int]
    tile_size_um: tuple[float, float]
    tile_overlap_um: float
    detectability_contrast_min: float
    detectability_radius_um_min: float
    dedup_merge_radius_um: float


class ContractObservationModel(BaseModel):
    """Drafting-visible observation-model subset only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    per_blob_fields: tuple[str, ...]
    debris_contrast_min: float
    debris_circularity_max: float
    debris_radius_um_max: float
    focus_score_min: float
    coordinate_tolerance_um: float
    status_codes: dict[int, str]


def _geometry_from_raw(raw: dict[str, Any]) -> GeometryConfig:
    geometry = raw["geometry"]
    declared = geometry["declared_region"]
    tiling = geometry["tiling"]
    flake_population = geometry["flake_population"]
    debris_population = geometry["debris_population"]
    detectability = geometry["detectability_floor"]
    dedup = geometry["dedup"]
    return GeometryConfig(
        chip_size_um=tuple(geometry["chip_size_um"]),
        coordinate_origin=geometry["coordinate_origin"],
        declared_region_origin_um=tuple(declared["origin_um"]),
        declared_region_size_um=tuple(declared["size_um"]),
        tiling_grid=tuple(tiling["grid"]),
        tile_size_um=tuple(tiling["tile_size_um"]),
        tile_index_range=tuple(tiling["tile_index_range"]),
        tile_overlap_um=float(tiling["overlap_um"]),
        flake_count_range=tuple(flake_population["count_range"]),
        flake_radius_um_range=tuple(flake_population["radius_um_range"]),
        flake_contrast_range=tuple(flake_population["contrast_range"]),
        debris_count_range=tuple(debris_population["count_range"]),
        detectability_contrast_min=float(detectability["contrast_min"]),
        detectability_radius_um_min=float(detectability["equivalent_radius_um_min"]),
        dedup_merge_radius_um=float(dedup["merge_radius_um"]),
    )


def _observation_model_from_raw(raw: dict[str, Any]) -> ObservationModelConfig:
    observation_model = raw["observation_model"]
    status_codes = {int(key): value for key, value in observation_model["status_codes"].items()}
    return ObservationModelConfig(
        per_blob_fields=tuple(observation_model["per_blob_fields"]),
        debris_contrast_min=DEBRIS_CONTRAST_MIN,
        debris_circularity_max=DEBRIS_CIRCULARITY_MAX,
        debris_radius_um_max=DEBRIS_RADIUS_UM_MAX,
        focus_score_min=FOCUS_SCORE_MIN,
        coordinate_tolerance_um=COORDINATE_TOLERANCE_UM,
        status_codes=status_codes,
    )


def _conditions_from_raw(raw: dict[str, Any]) -> dict[str, tuple[ConditionSpec, ...]]:
    conditions: dict[str, tuple[ConditionSpec, ...]] = {}
    for group, items in raw["conditions"].items():
        conditions[group] = tuple(
            ConditionSpec(
                condition_id=item["condition_id"],
                scenario=item["scenario"],
                parameters={key: float(value) for key, value in item.get("parameters", {}).items()},
                repetitions=int(item.get("repetitions", 3)),
            )
            for item in items
        )
    return conditions


@cache
def load_flake_search_preregistration() -> FlakeSearchPreregistration:
    """Read the frozen flake-search preregistration YAML once, cached thereafter."""

    resource = files("proprio").joinpath("data/flake-search-preregistration.yaml")
    raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
    return FlakeSearchPreregistration(
        schema_version=raw["schema_version"],
        geometry=_geometry_from_raw(raw),
        observation_model=_observation_model_from_raw(raw),
        conditions=_conditions_from_raw(raw),
    )


def contract_geometry(prereg: FlakeSearchPreregistration) -> ContractGeometry:
    """Drafting-visible geometry only. Never reads `prereg.conditions`."""

    geometry = prereg.geometry
    return ContractGeometry(
        chip_size_um=geometry.chip_size_um,
        coordinate_origin=geometry.coordinate_origin,
        declared_region_origin_um=geometry.declared_region_origin_um,
        declared_region_size_um=geometry.declared_region_size_um,
        tiling_grid=geometry.tiling_grid,
        tile_size_um=geometry.tile_size_um,
        tile_overlap_um=geometry.tile_overlap_um,
        detectability_contrast_min=geometry.detectability_contrast_min,
        detectability_radius_um_min=geometry.detectability_radius_um_min,
        dedup_merge_radius_um=geometry.dedup_merge_radius_um,
    )


def contract_observation_model(prereg: FlakeSearchPreregistration) -> ContractObservationModel:
    """Drafting-visible observation-model subset only. Never reads `prereg.conditions`."""

    observation_model = prereg.observation_model
    return ContractObservationModel(
        per_blob_fields=observation_model.per_blob_fields,
        debris_contrast_min=observation_model.debris_contrast_min,
        debris_circularity_max=observation_model.debris_circularity_max,
        debris_radius_um_max=observation_model.debris_radius_um_max,
        focus_score_min=observation_model.focus_score_min,
        coordinate_tolerance_um=observation_model.coordinate_tolerance_um,
        status_codes=dict(observation_model.status_codes),
    )
