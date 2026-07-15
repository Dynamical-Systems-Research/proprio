"""Unit tests for the reduced-order flake-search simulator and bounded controller.

Every threshold/parameter used below is read from the loaded preregistration (or from
flake_search_types' documented mirrors of its frozen prose, cross-checked against the raw
YAML text by test_frozen_prose_thresholds_match_yaml_text) rather than hardcoded, so these
tests fail if the frozen YAML and this test file drift apart.
"""

from __future__ import annotations

import hashlib
import inspect
import re
from importlib.resources import files
from typing import Any

import pytest

from proprio.flake_search_simulator import (
    ALLOWED_METHODS,
    HOMOGRAPHY_RESIDUAL_UM,
    NOMINAL_FOCUS_SCORE,
    QUANTIZATION_STEP_UM,
    STAGE_NOISE_UM,
    FlakeSearchController,
    build_flake_search_controller,
)
from proprio.flake_search_types import (
    COORDINATE_TOLERANCE_UM,
    DEBRIS_CIRCULARITY_MAX,
    DEBRIS_CONTRAST_MIN,
    DEBRIS_RADIUS_UM_MAX,
    FOCUS_SCORE_MIN,
    ConditionSpec,
    FlakeSearchPreregistration,
    ScanStatus,
    contract_geometry,
    contract_observation_model,
    load_flake_search_preregistration,
)
from proprio.instrument_types import InstrumentRuntimeUnavailable, SimulationScenario

PREREG: FlakeSearchPreregistration = load_flake_search_preregistration()


def _condition(condition_id: str) -> ConditionSpec:
    for group in PREREG.conditions.values():
        for item in group:
            if item.condition_id == condition_id:
                return item
    raise KeyError(condition_id)


def _full_scan(controller: FlakeSearchController, *, calibrate: bool = True) -> None:
    """Drive one complete nominal-shape scan (16 tiles, autofocus once per row)."""

    if calibrate:
        controller.calibrate_region()
    grid_x, grid_y = PREREG.geometry.tiling_grid
    for iy in range(grid_y):
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()


def _nearest_truth_distance(
    chip_x: float, chip_y: float, truth_points: list[tuple[float, float]]
) -> float:
    return min(((chip_x - tx) ** 2 + (chip_y - ty) ** 2) ** 0.5 for tx, ty in truth_points)


# ------------------------------------------------------------------------------------
# Deterministic reset
# ------------------------------------------------------------------------------------


def test_reset_is_deterministic_across_fresh_controllers() -> None:
    condition = _condition("visible-nominal")
    first = FlakeSearchController(condition.parameters)
    first.reset()
    second = FlakeSearchController(condition.parameters)
    second.reset()

    first_telemetry = first.telemetry()
    second_telemetry = second.telemetry()
    assert first_telemetry["_raw_evidence"]["flakes"] == second_telemetry["_raw_evidence"]["flakes"]
    assert first_telemetry["_raw_evidence"]["debris"] == second_telemetry["_raw_evidence"]["debris"]
    assert first_telemetry["chip_id"] == second_telemetry["chip_id"]
    assert first.trace == second.trace


def test_reset_is_deterministic_across_repeated_reset_on_one_controller() -> None:
    condition = _condition("visible-nominal")
    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    first_flakes = controller.telemetry()["_raw_evidence"]["flakes"]
    controller.reset()
    second_flakes = controller.telemetry()["_raw_evidence"]["flakes"]
    assert first_flakes == second_flakes


def test_full_scan_trace_and_manifest_are_deterministic_across_fresh_controllers() -> None:
    condition = _condition("visible-nominal")
    first = FlakeSearchController(condition.parameters)
    first.reset()
    _full_scan(first)
    count = first.strong_blob_count()
    for index in range(count):
        first.mark_candidate_from_blob(index)
    first.complete_scan(0)
    first.release()

    second = FlakeSearchController(condition.parameters)
    second.reset()
    _full_scan(second)
    second.strong_blob_count()
    for index in range(count):
        second.mark_candidate_from_blob(index)
    second.complete_scan(0)
    second.release()

    assert first.trace == second.trace
    assert (
        first.telemetry()["_raw_evidence"]["manifest"]
        == second.telemetry()["_raw_evidence"]["manifest"]
    )


def test_different_seeds_produce_different_layouts() -> None:
    acquisition = FlakeSearchController(_condition("acquisition-nominal").parameters)
    acquisition.reset()
    visible = FlakeSearchController(_condition("visible-nominal").parameters)
    visible.reset()
    assert (
        acquisition.telemetry()["_raw_evidence"]["flakes"]
        != visible.telemetry()["_raw_evidence"]["flakes"]
    )
    assert acquisition.telemetry()["chip_id"] != visible.telemetry()["chip_id"]


# ------------------------------------------------------------------------------------
# Bounded surface
# ------------------------------------------------------------------------------------


def test_public_surface_is_exactly_twelve_atoms_plus_close_and_telemetry() -> None:
    public_methods = {
        name
        for name, _ in inspect.getmembers(FlakeSearchController, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == ALLOWED_METHODS | {"close", "telemetry"}
    assert len(ALLOWED_METHODS) == 12


def test_atom_returns_are_scalar_except_the_documented_dict_atom() -> None:
    """read_chip_state is the sole documented exception; see the module docstring."""

    condition = _condition("visible-nominal")
    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    assert isinstance(controller.read_chip_state(), dict)
    assert isinstance(controller.calibrate_region(), bool)
    assert isinstance(controller.move_to_tile(0, 0), bool)
    assert isinstance(controller.autofocus(), float)
    blob_count = controller.capture_tile()
    assert isinstance(blob_count, int)
    if blob_count:
        assert isinstance(controller.get_blob(0, "x_um"), float)
    assert controller.mark_candidate(0.0, 0.0, 20.0, 0.5, False) is None
    assert isinstance(controller.strong_blob_count(), int)
    assert isinstance(controller.mark_candidate_from_blob(0), bool)
    assert controller.complete_scan(0) is None
    assert controller.release() is None
    assert controller.close() is None


def test_out_of_range_move_returns_false_and_records_fault_event() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    low, high = PREREG.geometry.tile_index_range
    assert controller.move_to_tile(high + 1, 0) is False
    last = controller.trace[-1]
    assert last["operation"] == "move_to_tile"
    assert last["arrival"] is False
    assert last["fault"] == "tile_index_out_of_range"
    assert controller.move_to_tile(low, high + 1) is False


def test_unknown_condition_parameter_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported flake-search condition fields"):
        FlakeSearchController({"seed": 1.0, "not_a_real_parameter": 2.0})


def test_missing_seed_rejected() -> None:
    with pytest.raises(ValueError, match="must include 'seed'"):
        FlakeSearchController({"fault_code": 1.0})


def test_reset_must_be_called_first() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    with pytest.raises(RuntimeError, match="reset"):
        controller.move_to_tile(0, 0)


# ------------------------------------------------------------------------------------
# Per-fault-class simulator behavior
# ------------------------------------------------------------------------------------


def test_stale_chip_swap_flips_nonce_after_frozen_tile_index() -> None:
    condition = _condition("locked-stale-chip-swap")
    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    pre = controller.read_chip_state()
    controller.calibrate_region()
    swap_after = condition.parameters["swap_after_tile_index"]
    grid_x, grid_y = PREREG.geometry.tiling_grid
    move_count = 0
    for iy in range(grid_y):
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            move_count += 1
            if move_count == int(swap_after):
                mid = controller.read_chip_state()
                assert mid["state_nonce"] == pre["state_nonce"]
            if move_count == int(swap_after) + 1:
                after = controller.read_chip_state()
                assert after["state_nonce"] == pre["state_nonce"] + 1
    post = controller.read_chip_state()
    assert post["chip_id"] == pre["chip_id"]
    assert post["state_nonce"] == pre["state_nonce"] + 1


def test_origin_offset_applies_only_when_uncalibrated() -> None:
    condition = _condition("locked-wrong-origin-offset")
    offset_x = condition.parameters["offset_x_um"]
    offset_y = condition.parameters["offset_y_um"]
    noise_bound = STAGE_NOISE_UM + QUANTIZATION_STEP_UM / 2 + HOMOGRAPHY_RESIDUAL_UM

    uncalibrated = FlakeSearchController(condition.parameters)
    uncalibrated.reset()
    truth = uncalibrated.telemetry()["_raw_evidence"]
    truth_points = [(item["chip_x_um"], item["chip_y_um"]) for item in truth["flakes"]] + [
        (item["chip_x_um"], item["chip_y_um"]) for item in truth["debris"]
    ]
    grid_x, grid_y = PREREG.geometry.tiling_grid
    tile_w, tile_h = PREREG.geometry.tile_size_um
    origin_x, origin_y = PREREG.geometry.declared_region_origin_um
    saw_offset_error = False
    for iy in range(grid_y):
        for ix in range(grid_x):
            uncalibrated.move_to_tile(ix, iy)
            uncalibrated.autofocus()
            count = uncalibrated.capture_tile()
            for index in range(count):
                x = uncalibrated.get_blob(index, "x_um")
                y = uncalibrated.get_blob(index, "y_um")
                chip_x = origin_x + ix * tile_w + x
                chip_y = origin_y + iy * tile_h + y
                nearest = _nearest_truth_distance(chip_x, chip_y, truth_points)
                # The nearest true object's own untransformed position is `noise_bound`
                # away at most; if the reconstructed position is far closer to
                # (truth + offset) than to truth itself, the fault was applied.
                shifted_error = min(
                    ((chip_x - (tx + offset_x)) ** 2 + (chip_y - (ty + offset_y)) ** 2) ** 0.5
                    for tx, ty in truth_points
                )
                if shifted_error <= noise_bound and nearest > noise_bound:
                    saw_offset_error = True
    assert saw_offset_error, "expected at least one detection shifted by the frozen offset"

    calibrated = FlakeSearchController(condition.parameters)
    calibrated.reset()
    calibrated.calibrate_region()
    for iy in range(grid_y):
        for ix in range(grid_x):
            calibrated.move_to_tile(ix, iy)
            calibrated.autofocus()
            count = calibrated.capture_tile()
            for index in range(count):
                x = calibrated.get_blob(index, "x_um")
                y = calibrated.get_blob(index, "y_um")
                chip_x = origin_x + ix * tile_w + x
                chip_y = origin_y + iy * tile_h + y
                assert _nearest_truth_distance(chip_x, chip_y, truth_points) <= noise_bound * 2**0.5


def test_mirrored_frame_applies_only_when_uncalibrated() -> None:
    condition = _condition("locked-mirrored-frame")
    chip_size_y = PREREG.geometry.chip_size_um[1]
    noise_bound = STAGE_NOISE_UM + QUANTIZATION_STEP_UM / 2 + HOMOGRAPHY_RESIDUAL_UM

    uncalibrated = FlakeSearchController(condition.parameters)
    uncalibrated.reset()
    truth = uncalibrated.telemetry()["_raw_evidence"]
    truth_points = [(item["chip_x_um"], item["chip_y_um"]) for item in truth["flakes"]] + [
        (item["chip_x_um"], item["chip_y_um"]) for item in truth["debris"]
    ]
    grid_x, grid_y = PREREG.geometry.tiling_grid
    tile_w, tile_h = PREREG.geometry.tile_size_um
    origin_x, origin_y = PREREG.geometry.declared_region_origin_um
    saw_mirror_error = False
    for iy in range(grid_y):
        for ix in range(grid_x):
            uncalibrated.move_to_tile(ix, iy)
            uncalibrated.autofocus()
            count = uncalibrated.capture_tile()
            for index in range(count):
                x = uncalibrated.get_blob(index, "x_um")
                y = uncalibrated.get_blob(index, "y_um")
                chip_x = origin_x + ix * tile_w + x
                chip_y = origin_y + iy * tile_h + y
                mirrored_error = min(
                    ((chip_x - tx) ** 2 + (chip_y - (chip_size_y - ty)) ** 2) ** 0.5
                    for tx, ty in truth_points
                )
                nearest = _nearest_truth_distance(chip_x, chip_y, truth_points)
                if mirrored_error <= noise_bound and nearest > noise_bound:
                    saw_mirror_error = True
    assert saw_mirror_error, "expected at least one detection reflected across the y-mirror"

    calibrated = FlakeSearchController(condition.parameters)
    calibrated.reset()
    calibrated.calibrate_region()
    for iy in range(grid_y):
        for ix in range(grid_x):
            calibrated.move_to_tile(ix, iy)
            calibrated.autofocus()
            count = calibrated.capture_tile()
            for index in range(count):
                x = calibrated.get_blob(index, "x_um")
                y = calibrated.get_blob(index, "y_um")
                chip_x = origin_x + ix * tile_w + x
                chip_y = origin_y + iy * tile_h + y
                assert _nearest_truth_distance(chip_x, chip_y, truth_points) <= noise_bound * 2**0.5


@pytest.mark.parametrize("condition_id", ["locked-wrong-origin-offset", "locked-mirrored-frame"])
def test_calibration_gated_faults_on_the_recommended_path(condition_id: str) -> None:
    """Regression for the fault-gating fix: recommended path is empty while
    uncalibrated (valid_acquisition_rule), and coordinate-correct once calibrated."""

    condition = _condition(condition_id)

    uncalibrated = FlakeSearchController(condition.parameters)
    uncalibrated.reset()
    _full_scan(uncalibrated, calibrate=False)
    assert uncalibrated.strong_blob_count() == 0
    assert uncalibrated.mark_candidate_from_blob(0) is False
    assert uncalibrated.telemetry()["manifest_size"] == 0
    timeline = uncalibrated.telemetry()["_raw_evidence"]["acquisition_timeline"]
    assert timeline and all(not entry["valid"] for entry in timeline)

    calibrated = FlakeSearchController(condition.parameters)
    calibrated.reset()
    _full_scan(calibrated, calibrate=True)
    count = calibrated.strong_blob_count()
    assert count > 0
    for index in range(count):
        calibrated.mark_candidate_from_blob(index)
    telemetry = calibrated.telemetry()
    truth_by_id = {item["flake_id"]: item for item in telemetry["_raw_evidence"]["flakes"]}
    per_axis_bound = STAGE_NOISE_UM + QUANTIZATION_STEP_UM / 2 + HOMOGRAPHY_RESIDUAL_UM
    manifest = telemetry["_raw_evidence"]["manifest"]
    queue_truth = telemetry["_raw_evidence"]["queue_truth"]
    assert manifest
    for record, provenance in zip(manifest, queue_truth, strict=True):
        truth = truth_by_id[provenance["true_object_id"]]
        assert abs(record["chip_x_um"] - truth["chip_x_um"]) <= per_axis_bound
        assert abs(record["chip_y_um"] - truth["chip_y_um"]) <= per_axis_bound
        assert per_axis_bound < COORDINATE_TOLERANCE_UM


def test_focus_decays_by_frozen_rate_per_move_and_autofocus_restores() -> None:
    condition = _condition("locked-focus-drift")
    decay = condition.parameters["decay_per_move"]
    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    controller.calibrate_region()
    start = controller.telemetry()["focus_score"]
    controller.move_to_tile(0, 0)
    assert controller.telemetry()["focus_score"] == pytest.approx(start - decay)
    controller.move_to_tile(1, 0)
    assert controller.telemetry()["focus_score"] == pytest.approx(start - 2 * decay)
    restored = controller.autofocus()
    assert restored == pytest.approx(NOMINAL_FOCUS_SCORE)


def test_visible_mild_defocus_recovers_via_autofocus() -> None:
    condition = _condition("visible-mild-defocus")
    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    initial_focus = controller.telemetry()["focus_score"]
    assert initial_focus == pytest.approx(condition.parameters["initial_focus_score"])
    assert condition.parameters["initial_focus_score"] < FOCUS_SCORE_MIN
    assert controller.autofocus() >= FOCUS_SCORE_MIN


def test_debris_multiplier_scales_population() -> None:
    condition = _condition("locked-heavy-debris")
    baseline = FlakeSearchController({"seed": condition.parameters["seed"]})
    baseline.reset()
    baseline_count = len(baseline.telemetry()["_raw_evidence"]["debris"])

    faulted = FlakeSearchController(condition.parameters)
    faulted.reset()
    faulted_count = len(faulted.telemetry()["_raw_evidence"]["debris"])

    multiplier = condition.parameters["debris_count_multiplier"]
    assert faulted_count == max(baseline_count, round(baseline_count * multiplier))
    assert faulted_count > baseline_count


def test_illumination_out_of_range_flag_set() -> None:
    out_of_range = _condition("locked-illumination-out-of-range")
    controller = FlakeSearchController(out_of_range.parameters)
    controller.reset()
    assert controller.telemetry()["illumination_in_range"] is False

    mild = _condition("visible-mild-illumination")
    controller = FlakeSearchController(mild.parameters)
    controller.reset()
    assert controller.telemetry()["illumination_in_range"] is True


def test_illumination_out_of_range_invalidates_every_capture() -> None:
    condition = _condition("locked-illumination-out-of-range")
    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    _full_scan(controller)
    assert controller.strong_blob_count() == 0
    timeline = controller.telemetry()["_raw_evidence"]["acquisition_timeline"]
    assert timeline and all(not entry["valid"] for entry in timeline)


def test_backlash_shifts_reported_x_by_the_frozen_amount() -> None:
    condition = _condition("evolution-stage-backlash-shift")
    backlash_x = condition.parameters["backlash_x_um"]
    noise_bound = STAGE_NOISE_UM + QUANTIZATION_STEP_UM / 2 + HOMOGRAPHY_RESIDUAL_UM

    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    _full_scan(controller)
    count = controller.strong_blob_count()
    for index in range(count):
        controller.mark_candidate_from_blob(index)
    telemetry = controller.telemetry()
    truth_by_id = {item["flake_id"]: item for item in telemetry["_raw_evidence"]["flakes"]}
    truth_by_id.update({item["debris_id"]: item for item in telemetry["_raw_evidence"]["debris"]})

    manifest = telemetry["_raw_evidence"]["manifest"]
    queue_truth = telemetry["_raw_evidence"]["queue_truth"]
    assert manifest, "expected at least one queued candidate"
    for record, provenance in zip(manifest, queue_truth, strict=True):
        truth = truth_by_id[provenance["true_object_id"]]
        dx = record["chip_x_um"] - truth["chip_x_um"]
        dy = record["chip_y_um"] - truth["chip_y_um"]
        assert dx == pytest.approx(-backlash_x, abs=noise_bound)
        assert abs(dy) <= noise_bound


def test_edge_clipped_flakes_flagged_and_meet_frozen_minimum() -> None:
    condition = _condition("locked-edge-clipped-field")
    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    flakes = controller.telemetry()["_raw_evidence"]["flakes"]
    clipped = [flake for flake in flakes if flake["clipped"]]
    assert len(clipped) >= condition.parameters["min_clipped_flake_count"]

    x0, y0 = PREREG.geometry.declared_region_origin_um
    width, height = PREREG.geometry.declared_region_size_um
    x1, y1 = x0 + width, y0 + height
    for flake in clipped:
        crosses = (
            flake["chip_x_um"] - flake["radius_um"] < x0
            or flake["chip_x_um"] + flake["radius_um"] > x1
            or flake["chip_y_um"] - flake["radius_um"] < y0
            or flake["chip_y_um"] + flake["radius_um"] > y1
        )
        assert crosses
    for flake in flakes:
        if flake not in clipped:
            assert (
                flake["chip_x_um"] - flake["radius_um"] >= x0
                and flake["chip_x_um"] + flake["radius_um"] <= x1
                and flake["chip_y_um"] - flake["radius_um"] >= y0
                and flake["chip_y_um"] + flake["radius_um"] <= y1
            )


# ------------------------------------------------------------------------------------
# Candidate queue mechanics
# ------------------------------------------------------------------------------------


def test_strong_blob_screen_uses_the_frozen_debris_signature_thresholds() -> None:
    contract = contract_observation_model(PREREG)
    assert contract.debris_contrast_min == DEBRIS_CONTRAST_MIN
    assert contract.debris_circularity_max == DEBRIS_CIRCULARITY_MAX
    assert contract.debris_radius_um_max == DEBRIS_RADIUS_UM_MAX
    # every constructed debris object matches the mechanical signature by construction
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    for item in controller.telemetry()["_raw_evidence"]["debris"]:
        matched = item["contrast"] >= DEBRIS_CONTRAST_MIN and (
            item["circularity"] < DEBRIS_CIRCULARITY_MAX or item["radius_um"] < DEBRIS_RADIUS_UM_MAX
        )
        assert matched
    # no constructed flake ever matches it
    for item in controller.telemetry()["_raw_evidence"]["flakes"]:
        matched = item["contrast"] >= DEBRIS_CONTRAST_MIN and (
            item["circularity"] < DEBRIS_CIRCULARITY_MAX or item["radius_um"] < DEBRIS_RADIUS_UM_MAX
        )
        assert not matched


def test_debris_never_enters_the_strong_blob_queue() -> None:
    controller = FlakeSearchController(_condition("locked-heavy-debris").parameters)
    controller.reset()
    _full_scan(controller)
    queue_truth = controller.telemetry()["_raw_evidence"]["queue_truth"]
    assert queue_truth
    assert all(not entry["is_debris_truth"] for entry in queue_truth)


def test_mark_candidate_from_blob_computes_coordinates_within_the_derived_noise_bound() -> None:
    noise_bound = (STAGE_NOISE_UM + QUANTIZATION_STEP_UM / 2 + HOMOGRAPHY_RESIDUAL_UM) * 2**0.5
    assert noise_bound < COORDINATE_TOLERANCE_UM

    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    _full_scan(controller)
    count = controller.strong_blob_count()
    for index in range(count):
        controller.mark_candidate_from_blob(index)
    telemetry = controller.telemetry()
    truth_by_id = {item["flake_id"]: item for item in telemetry["_raw_evidence"]["flakes"]}
    manifest = telemetry["_raw_evidence"]["manifest"]
    queue_truth = telemetry["_raw_evidence"]["queue_truth"]
    assert manifest
    for record, provenance in zip(manifest, queue_truth, strict=True):
        truth = truth_by_id[provenance["true_object_id"]]
        distance = (
            (record["chip_x_um"] - truth["chip_x_um"]) ** 2
            + (record["chip_y_um"] - truth["chip_y_um"]) ** 2
        ) ** 0.5
        assert distance <= noise_bound


def test_strong_blob_count_bounded_by_true_flake_population() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    _full_scan(controller)
    truth = controller.telemetry()["_raw_evidence"]
    assert controller.strong_blob_count() <= len(truth["flakes"])


def test_overlap_band_flakes_are_deduplicated_not_double_counted() -> None:
    condition = _condition("locked-duplicate-overlap-stress")
    controller = FlakeSearchController(condition.parameters)
    controller.reset()
    _full_scan(controller)
    truth = controller.telemetry()["_raw_evidence"]
    assert controller.strong_blob_count() == len(truth["flakes"])
    queue_truth = truth["queue_truth"]
    seen_ids = [entry["true_object_id"] for entry in queue_truth]
    assert len(seen_ids) == len(set(seen_ids))


def test_mark_candidate_from_blob_idempotent_and_out_of_range_returns_false() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    _full_scan(controller)
    count = controller.strong_blob_count()
    assert count > 0
    assert controller.mark_candidate_from_blob(0) is True
    assert controller.mark_candidate_from_blob(0) is False
    assert controller.mark_candidate_from_blob(count + 1000) is False
    assert controller.mark_candidate_from_blob(-1) is False
    manifest_size = controller.telemetry()["manifest_size"]
    assert manifest_size == 1


def test_get_blob_scoped_to_most_recent_capture_only() -> None:
    """index resets on every capture_tile() call, even re-capturing the same tile.

    Re-capturing the identical (unmoved) tile keeps blob_count identical (same true
    population, same bounds) while advancing the RNG stream, so a changed get_blob(0,
    "x_um") reading after the second capture_tile() call proves the accessor is scoped
    to the latest capture's fresh data, not cached/cumulative across calls.
    """

    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    controller.calibrate_region()
    controller.move_to_tile(0, 0)
    controller.autofocus()
    first_count = controller.capture_tile()
    if not first_count:
        pytest.skip("seeded tile (0, 0) has no detections under this condition")
    first_reading = controller.get_blob(0, "x_um")

    second_count = controller.capture_tile()
    assert second_count == first_count
    second_reading = controller.get_blob(0, "x_um")
    assert second_reading != first_reading


def test_get_blob_rejects_unknown_field_and_out_of_range_index() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    controller.calibrate_region()
    controller.move_to_tile(0, 0)
    controller.autofocus()
    controller.capture_tile()
    with pytest.raises(ValueError, match="unsupported blob field"):
        controller.get_blob(0, "material")
    with pytest.raises(IndexError):
        controller.get_blob(10_000, "x_um")


# ------------------------------------------------------------------------------------
# Raw evidence channel, ordering guards, and UNAVAILABLE
# ------------------------------------------------------------------------------------


def test_raw_evidence_present_in_telemetry_and_absent_from_trace() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    _full_scan(controller)
    telemetry = controller.telemetry()
    assert "_raw_evidence" in telemetry
    assert telemetry["_raw_evidence"]["flakes"]

    serialized_trace = repr(controller.trace)
    assert "_raw_evidence" not in serialized_trace
    for entry in controller.trace:
        assert "flake_id" not in str(entry)
        assert "debris_id" not in str(entry)


def test_complete_scan_and_release_ordering_enforced() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    with pytest.raises(RuntimeError, match="before complete_scan"):
        controller.release()
    controller.complete_scan(0)
    with pytest.raises(RuntimeError, match="already called"):
        controller.complete_scan(0)
    controller.release()
    with pytest.raises(RuntimeError, match="already called"):
        controller.release()


def test_complete_scan_rejects_unknown_status_code() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    with pytest.raises(ValueError, match="unsupported status_code"):
        controller.complete_scan(99)


def test_capture_tile_requires_prior_move() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    with pytest.raises(RuntimeError, match="move_to_tile"):
        controller.capture_tile()


def test_mark_candidate_requires_prior_move() -> None:
    controller = FlakeSearchController(_condition("visible-nominal").parameters)
    controller.reset()
    with pytest.raises(RuntimeError, match="move_to_tile"):
        controller.mark_candidate(0.0, 0.0, 20.0, 0.5, False)


def test_unavailable_scenario_raises_instrument_runtime_unavailable() -> None:
    with pytest.raises(InstrumentRuntimeUnavailable):
        build_flake_search_controller(SimulationScenario.UNAVAILABLE, {"seed": 1.0})


def test_non_unavailable_scenarios_construct_normally() -> None:
    for scenario in (
        SimulationScenario.NOMINAL,
        SimulationScenario.REPAIR,
        SimulationScenario.DRIFT,
    ):
        controller = build_flake_search_controller(scenario, {"seed": 1.0})
        assert isinstance(controller, FlakeSearchController)


# ------------------------------------------------------------------------------------
# Coordinate noise budget (M2) and frozen-prose threshold drift guard
# ------------------------------------------------------------------------------------


def test_coordinate_noise_budget_conforms_to_frozen_tolerance_with_margin() -> None:
    worst_case_per_axis = STAGE_NOISE_UM + QUANTIZATION_STEP_UM / 2 + HOMOGRAPHY_RESIDUAL_UM
    assert worst_case_per_axis < COORDINATE_TOLERANCE_UM
    margin_fraction = (COORDINATE_TOLERANCE_UM - worst_case_per_axis) / COORDINATE_TOLERANCE_UM
    assert margin_fraction > 0.5


def test_frozen_prose_thresholds_match_yaml_text() -> None:
    """Drift guard: mirrors of prose-only frozen numbers must match the raw YAML text."""

    resource = files("proprio").joinpath("data/flake-search-preregistration.yaml")
    raw_text = resource.read_text(encoding="utf-8")

    debris_rule_match = re.search(
        r"contrast >= (0\.\d+) AND \(circularity < (0\.\d+) OR radius_um < (\d+\.\d+)\)",
        raw_text,
    )
    assert debris_rule_match is not None
    assert float(debris_rule_match.group(1)) == DEBRIS_CONTRAST_MIN
    assert float(debris_rule_match.group(2)) == DEBRIS_CIRCULARITY_MAX
    assert float(debris_rule_match.group(3)) == DEBRIS_RADIUS_UM_MAX

    focus_matches = re.findall(r"focus_score >= (0\.\d+)", raw_text)
    assert focus_matches
    assert all(float(value) == FOCUS_SCORE_MIN for value in focus_matches)

    coordinate_match = re.search(r"<= (\d+\.\d+) um, evaluated independently per axis", raw_text)
    assert coordinate_match is not None
    assert float(coordinate_match.group(1)) == COORDINATE_TOLERANCE_UM


def test_known_condition_parameters_cover_every_frozen_condition_field() -> None:
    from proprio.flake_search_types import KNOWN_CONDITION_PARAMETERS

    for group in PREREG.conditions.values():
        for condition in group:
            assert set(condition.parameters).issubset(KNOWN_CONDITION_PARAMETERS)


def test_contract_accessors_never_expose_condition_data() -> None:
    """Ledger finding M4: contract-facing accessors must never carry conditions."""

    geometry_fields = set(contract_geometry(PREREG).model_dump())
    observation_fields = set(contract_observation_model(PREREG).model_dump())
    assert "conditions" not in geometry_fields
    assert "conditions" not in observation_fields
    assert "seed" not in geometry_fields
    assert "seed" not in observation_fields


def _string_values(payload: Any) -> list[str]:
    """Every str-typed value reachable in a nested trace/telemetry structure."""

    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, dict):
        found: list[str] = []
        for key, value in payload.items():
            found.extend(_string_values(key))
            found.extend(_string_values(value))
        return found
    if isinstance(payload, (list, tuple)):
        found = []
        for item in payload:
            found.extend(_string_values(item))
        return found
    return []


def test_chip_id_is_opaque_and_seed_is_unrecoverable_from_trace_and_compact_telemetry() -> None:
    """M4 leak guard: locked seeds must be structurally unrecoverable from what a
    drafting agent can see (trace + compact telemetry). chip_id must be the one-way
    sha256 derivation, and no string value in either surface may embed the seed digits.
    (_raw_evidence is exempt: it is the verifier-only channel and carries the seed
    deliberately.)"""

    for group in PREREG.conditions.values():
        for condition in group:
            seed = int(condition.parameters["seed"])
            controller = FlakeSearchController(condition.parameters)
            controller.reset()
            state = controller.read_chip_state()

            digest = hashlib.sha256(f"proprio.flake_search|{seed}".encode()).hexdigest()
            assert state["chip_id"] == f"chip-{digest[:12]}"

            compact = dict(controller.telemetry())
            assert "_raw_evidence" in compact
            compact.pop("_raw_evidence")
            assert "seed" not in compact
            seed_text = str(seed)
            for value in _string_values(list(controller.trace)) + _string_values(compact):
                assert seed_text not in value


def test_scan_status_enum_matches_frozen_status_codes() -> None:
    """Drift guard: ScanStatus must mirror observation_model.status_codes exactly."""

    codes = PREREG.observation_model.status_codes
    assert {status.value for status in ScanStatus} == set(codes)
    for status in ScanStatus:
        assert status.name.lower() == codes[status.value]


def test_nominal_full_scan_matches_the_frozen_call_budget_total() -> None:
    """Cross-check against task-2-report.md's recomputed nominal_path total (55 calls)."""

    controller = FlakeSearchController(_condition("acquisition-nominal").parameters)
    controller.reset()
    controller.read_chip_state()
    _full_scan(controller)
    controller.read_chip_state()
    count = controller.strong_blob_count()
    flake_ceiling = PREREG.geometry.flake_count_range[1]
    for index in range(flake_ceiling):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(0)
    controller.release()
    assert count <= flake_ceiling
    assert len(controller.trace) == 55
