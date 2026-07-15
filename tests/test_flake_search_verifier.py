"""Scripted controller sessions exercising the 12 frozen flake-search checks.

Every test builds a real ``FlakeSearchController`` for a named preregistration
condition and drives it exactly as a correct or deliberately faulty skill would --
never through ``compile_instrument_skill``, since this tests the independent
verifier's own judgment directly against raw controller trace + telemetry. All
expected numeric values are read from ``load_flake_search_preregistration()``.
"""

from __future__ import annotations

import re
from importlib.resources import files
from typing import Any

import pytest

from proprio.flake_search_simulator import FlakeSearchController
from proprio.flake_search_types import (
    ConditionSpec,
    FlakeSearchPreregistration,
    ScanStatus,
    load_flake_search_preregistration,
)
from proprio.flake_search_verifier import verify_flake_search
from proprio.instrument_qualification import DEFAULT_SKILL_LIMITS
from proprio.instrument_types import GateCheck

PREREG: FlakeSearchPreregistration = load_flake_search_preregistration()
GEOMETRY = PREREG.geometry
OBSERVATION_MODEL = PREREG.observation_model
COMPLETE = int(ScanStatus.COMPLETE)
ABORTED_STALE_CHIP = int(ScanStatus.ABORTED_STALE_CHIP)
ABORTED_FOCUS_INVALID = int(ScanStatus.ABORTED_FOCUS_INVALID)
ABORTED_ILLUMINATION = int(ScanStatus.ABORTED_ILLUMINATION)
INCOMPLETE = int(ScanStatus.INCOMPLETE)

# The 12 frozen check_id strings, verbatim from the YAML's `checks:` section. Order
# matches the YAML for readability; the verifier only guarantees the set, not order.
EXPECTED_CHECK_IDS = (
    "chip-identity-state-freshness",
    "declared-region-coverage",
    "overlap-duplicate-control",
    "focus-validity",
    "candidate-recall",
    "false-candidate-burden",
    "edge-clipping",
    "coordinate-integrity",
    "uncertainty-abstention",
    "evidence-completeness",
    "bounded-runtime-stop",
    "resource-release",
)


def _condition(condition_id: str) -> ConditionSpec:
    for group in PREREG.conditions.values():
        for item in group:
            if item.condition_id == condition_id:
                return item
    raise KeyError(condition_id)


def _controller(condition_id: str) -> FlakeSearchController:
    controller = FlakeSearchController(_condition(condition_id).parameters)
    controller.reset()
    return controller


def _by_id(checks: tuple[GateCheck, ...]) -> dict[str, GateCheck]:
    return {check.check_id: check for check in checks}


def _verify(controller: FlakeSearchController) -> tuple[GateCheck, ...]:
    return verify_flake_search(list(controller.trace), controller.telemetry())


def _full_recommended_pass(
    controller: FlakeSearchController,
    *,
    calibrate: bool = True,
    autofocus_every_tile: bool = False,
    mark_candidates: bool = True,
    status: int = COMPLETE,
) -> None:
    """Drive one complete, correctly-scripted recommended-path scan.

    Mirrors the frozen nominal_path shape (autofocus once per row, 16 tiles, mark
    every chip-wide queue slot, complete_scan, release) documented in
    flake-search-preregistration.yaml's call_budget section.
    """

    controller.read_chip_state()
    if calibrate:
        controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y):
        if not autofocus_every_tile:
            controller.autofocus()
        for ix in range(grid_x):
            if autofocus_every_tile:
                controller.autofocus()
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    if mark_candidates:
        count = controller.strong_blob_count()
        for index in range(count):
            controller.mark_candidate_from_blob(index)
    controller.complete_scan(status)
    controller.release()


def _manual_scan(
    controller: FlakeSearchController,
    *,
    calibrate: bool = True,
    keep_debris: bool = False,
) -> None:
    """Drive the manual escape-hatch path: get_blob() + mark_candidate(), always
    reporting clipped=False. Tests needing a correct clip determination build it
    themselves."""

    controller.read_chip_state()
    if calibrate:
        controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    tile_w, tile_h = GEOMETRY.tile_size_um
    origin_x, origin_y = GEOMETRY.declared_region_origin_um
    for iy in range(grid_y):
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            blob_count = controller.capture_tile()
            nominal_x = origin_x + ix * tile_w
            nominal_y = origin_y + iy * tile_h
            for index in range(blob_count):
                contrast = controller.get_blob(index, "contrast")
                circularity = controller.get_blob(index, "circularity")
                radius = controller.get_blob(index, "radius_um")
                is_debris = contrast >= OBSERVATION_MODEL.debris_contrast_min and (
                    circularity < OBSERVATION_MODEL.debris_circularity_max
                    or radius < OBSERVATION_MODEL.debris_radius_um_max
                )
                if is_debris and not keep_debris:
                    continue
                x = controller.get_blob(index, "x_um")
                y = controller.get_blob(index, "y_um")
                controller.mark_candidate(nominal_x + x, nominal_y + y, radius, contrast, False)
    controller.read_chip_state()


def test_emits_exactly_the_twelve_frozen_check_ids() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    checks = _verify(controller)
    assert len(checks) == 12
    assert {check.check_id for check in checks} == set(EXPECTED_CHECK_IDS)


def test_frozen_check_ids_match_the_yaml_text() -> None:
    """Drift guard: this file's EXPECTED_CHECK_IDS must mirror the raw YAML."""

    resource = files("proprio").joinpath("data/flake-search-preregistration.yaml")
    raw_text = resource.read_text(encoding="utf-8")
    ids_in_yaml = re.findall(r"check_id:\s*(\S+)", raw_text)
    assert set(ids_in_yaml) == set(EXPECTED_CHECK_IDS)
    assert len(ids_in_yaml) == 12


def _walk_strings(payload: Any) -> list[str]:
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, dict):
        found: list[str] = []
        for key, value in payload.items():
            found.extend(_walk_strings(key))
            found.extend(_walk_strings(value))
        return found
    if isinstance(payload, (list, tuple)):
        found = []
        for item in payload:
            found.extend(_walk_strings(item))
        return found
    return []


def test_no_judgment_key_or_material_vocabulary_at_any_depth() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    checks = _verify(controller)
    forbidden_substrings = ("material", "layer", "thickness")
    for check in checks:

        def _scan_keys(payload: Any) -> None:
            if isinstance(payload, dict):
                for key, value in payload.items():
                    assert key != "judgment"
                    assert not any(word in str(key).lower() for word in forbidden_substrings)
                    _scan_keys(value)
            elif isinstance(payload, (list, tuple)):
                for item in payload:
                    _scan_keys(item)

        _scan_keys(check.evidence)
        for text in _walk_strings(check.evidence):
            assert not any(word in text.lower() for word in forbidden_substrings)


@pytest.mark.parametrize(
    "condition_id",
    ["visible-nominal", "visible-mild-defocus", "visible-mild-illumination"],
)
def test_pass_visible_conditions_admit_on_all_twelve_checks(condition_id: str) -> None:
    controller = _controller(condition_id)
    _full_recommended_pass(controller)
    checks = _verify(controller)
    failing = [check.check_id for check in checks if not check.passed]
    assert failing == [], f"expected all 12 checks to pass, failing: {failing}"


def test_pass_acquisition_nominal_admits_on_all_twelve_checks() -> None:
    controller = _controller("acquisition-nominal")
    _full_recommended_pass(controller)
    checks = _verify(controller)
    failing = [check.check_id for check in checks if not check.passed]
    assert failing == []


def test_pass_correct_abort_under_real_stale_chip_swap() -> None:
    controller = _controller("locked-stale-chip-swap")
    controller.read_chip_state()
    controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y):
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    controller.complete_scan(ABORTED_STALE_CHIP)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["chip-identity-state-freshness"].passed is True


def test_pass_correct_abstention_under_real_illumination_fault() -> None:
    controller = _controller("locked-illumination-out-of-range")
    controller.read_chip_state()
    controller.complete_scan(ABORTED_ILLUMINATION)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["uncertainty-abstention"].passed is True
    assert checks["declared-region-coverage"].passed is True


def test_anti_gaming_abort_status_one_under_nominal_with_no_swap_fails() -> None:
    controller = _controller("visible-nominal")
    controller.read_chip_state()
    controller.calibrate_region()
    controller.move_to_tile(0, 0)
    controller.capture_tile()
    controller.read_chip_state()
    controller.complete_scan(ABORTED_STALE_CHIP)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["chip-identity-state-freshness"].passed is False


def test_anti_gaming_status_zero_completion_despite_real_swap_fails() -> None:
    controller = _controller("locked-stale-chip-swap")
    swap_after = int(_condition("locked-stale-chip-swap").parameters["swap_after_tile_index"])
    controller.read_chip_state()
    controller.calibrate_region()
    for _ in range(swap_after + 1):
        controller.move_to_tile(0, 0)
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["chip-identity-state-freshness"].passed is False


# The valid-tile recall denominator is a privilege of legitimate aborts only; a
# do-nothing status-4 session must fail against the chip-wide detectable population
# instead of vacuously passing with recall_den == 0.


def _do_nothing_session(condition_id: str) -> FlakeSearchController:
    controller = _controller(condition_id)
    controller.read_chip_state()
    controller.calibrate_region()
    controller.read_chip_state()
    controller.complete_scan(INCOMPLETE)
    controller.release()
    return controller


@pytest.mark.parametrize(
    "condition_id",
    ["visible-nominal", "locked-focus-drift", "locked-heavy-debris"],
)
def test_do_nothing_status_four_fails_candidate_recall(condition_id: str) -> None:
    checks = _by_id(_verify(_do_nothing_session(condition_id)))
    recall = checks["candidate-recall"]
    assert recall.passed is False
    assert recall.evidence["denominator_scope"] == "chip_wide"
    assert recall.evidence["abort_legitimate"] is False
    assert recall.evidence["recall_den"] >= 2
    assert recall.evidence["recall_num"] == 0


def test_do_nothing_status_four_fails_only_candidate_recall_on_nominal() -> None:
    """Coverage's non-zero-status branch stays excused for status 4 per the frozen
    text; candidate-recall is the sole backstop that rejects the do-nothing session."""

    checks = _verify(_do_nothing_session("visible-nominal"))
    failing = [check.check_id for check in checks if not check.passed]
    assert failing == ["candidate-recall"]


def test_legitimate_stale_chip_abort_keeps_the_valid_tile_recall_denominator() -> None:
    """A real swap detected mid-scan, honestly aborted with the pre-swap candidates
    marked, keeps the valid-tile denominator (honest partial credit) and passes."""

    condition = _condition("locked-stale-chip-swap")
    swap_after = int(condition.parameters["swap_after_tile_index"])
    grid_x, _grid_y = PREREG.geometry.tiling_grid
    rows_to_scan = swap_after // grid_x + 1  # first row whose moves cross the threshold
    controller = _controller("locked-stale-chip-swap")
    controller.read_chip_state()
    controller.calibrate_region()
    for iy in range(rows_to_scan):
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    count = controller.strong_blob_count()
    for index in range(count):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(ABORTED_STALE_CHIP)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["chip-identity-state-freshness"].passed is True
    recall = checks["candidate-recall"]
    assert recall.passed is True
    assert recall.evidence["denominator_scope"] == "valid_tiles"
    assert recall.evidence["abort_legitimate"] is True


def test_status_zero_full_scan_recall_uses_the_chip_wide_denominator() -> None:
    """Status 0 earns no denominator privilege; with 16/16 valid coverage the
    chip-wide and valid-tile denominators coincide, so a full scan still passes."""

    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    checks = _by_id(_verify(controller))
    recall = checks["candidate-recall"]
    assert recall.passed is True
    assert recall.evidence["denominator_scope"] == "chip_wide"
    assert recall.evidence["recall_den"] >= 2


def test_chip_wide_detectable_counts_support_the_do_nothing_backstop() -> None:
    """Regression pin: every frozen acquisition/visible/locked condition except
    locked-illumination-out-of-range (0 detectable, harmless since
    uncertainty-abstention already rejects it) constructs >= 2 chip-wide detectable
    non-clipped flakes, so the do-nothing backstop has teeth."""

    floor_contrast = PREREG.geometry.detectability_contrast_min
    floor_radius = PREREG.geometry.detectability_radius_um_min
    for group in ("acquisition", "visible", "locked"):
        for condition in PREREG.conditions[group]:
            controller = FlakeSearchController(condition.parameters)
            controller.reset()
            raw = controller.telemetry()["_raw_evidence"]
            detectable = sum(
                1
                for flake in raw["flakes"]
                if not flake["clipped"]
                and flake["contrast"] >= floor_contrast
                and flake["radius_um"] >= floor_radius
            )
            if condition.condition_id == "locked-illumination-out-of-range":
                assert detectable == 0
            else:
                assert detectable >= 2, (
                    f"{condition.condition_id}: chip-wide detectable non-clipped count "
                    f"{detectable} < 2 weakens the do-nothing recall backstop"
                )


def test_valid_tile_recall_denominator_pin_for_locked_abort_trajectories() -> None:
    """Regression pin for the valid_tiles denominator scope (companion to the
    chip-wide pin above), exercised only by legitimate aborts.
    locked-illumination-out-of-range is 0 by design: uncertainty-abstention, not
    candidate-recall, polices that condition.
    """

    condition = _condition("locked-stale-chip-swap")
    swap_after = int(condition.parameters["swap_after_tile_index"])
    grid_x, _grid_y = GEOMETRY.tiling_grid
    rows_to_scan = swap_after // grid_x + 1  # first row whose moves cross the threshold
    controller = _controller("locked-stale-chip-swap")
    controller.read_chip_state()
    controller.calibrate_region()
    for iy in range(rows_to_scan):
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    count = controller.strong_blob_count()
    for index in range(count):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(ABORTED_STALE_CHIP)
    controller.release()
    recall = _by_id(_verify(controller))["candidate-recall"]
    assert recall.evidence["abort_legitimate"] is True
    assert recall.evidence["denominator_scope"] == "valid_tiles"
    assert recall.evidence["recall_den"] == 2

    # locked-focus-drift: full coverage, then a status-2 abort with one synthesized
    # failed recovery attempt (autofocus always restores focus, so a real sub-floor
    # return isn't producible). valid_tiles and chip_wide denominators coincide here.
    controller = _controller("locked-focus-drift")
    controller.read_chip_state()
    controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y):
        for ix in range(grid_x):
            controller.autofocus()
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    count = controller.strong_blob_count()
    for index in range(count):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(ABORTED_FOCUS_INVALID)
    controller.release()
    telemetry = controller.telemetry()
    trace = [dict(row) for row in controller.trace]
    for row in reversed(trace):
        if row["operation"] == "autofocus":
            row["focus_score"] = OBSERVATION_MODEL.focus_score_min - 0.05
            break
    recall = _by_id(verify_flake_search(trace, telemetry))["candidate-recall"]
    assert recall.evidence["abort_legitimate"] is True
    assert recall.evidence["denominator_scope"] == "valid_tiles"
    assert recall.evidence["recall_den"] == 7

    # locked-illumination-out-of-range: den == 0 is intentional. The honest
    # abstention trajectory vacuously passes candidate-recall, but uncertainty-
    # abstention is the check that actually polices a gamed non-empty manifest.
    honest = _controller("locked-illumination-out-of-range")
    honest.read_chip_state()
    honest.complete_scan(ABORTED_ILLUMINATION)
    honest.release()
    honest_checks = _by_id(_verify(honest))
    honest_recall = honest_checks["candidate-recall"]
    assert honest_recall.evidence["abort_legitimate"] is True
    assert honest_recall.evidence["denominator_scope"] == "valid_tiles"
    assert honest_recall.evidence["recall_den"] == 0
    assert honest_recall.passed is True
    assert honest_checks["uncertainty-abstention"].passed is True

    gamed = _controller("locked-illumination-out-of-range")
    gamed.read_chip_state()
    gamed.move_to_tile(0, 0)
    gamed.mark_candidate(1000.0, 1000.0, 25.0, 0.5, False)
    gamed.complete_scan(ABORTED_ILLUMINATION)
    gamed.release()
    assert _by_id(_verify(gamed))["uncertainty-abstention"].passed is False


def test_reject_proceed_through_chip_swap_and_emit_manifest() -> None:
    controller = _controller("locked-stale-chip-swap")
    _full_recommended_pass(controller, status=COMPLETE)
    checks = _by_id(_verify(controller))
    assert checks["chip-identity-state-freshness"].passed is False


def test_reject_skip_tiles_fails_coverage() -> None:
    controller = _controller("visible-nominal")
    controller.read_chip_state()
    controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y - 1):  # deliberately skip the last row entirely
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    count = controller.strong_blob_count()
    for index in range(count):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["declared-region-coverage"].passed is False


def test_reject_wrong_origin_recommended_path_fails_coverage() -> None:
    controller = _controller("locked-wrong-origin-offset")
    _full_recommended_pass(controller, calibrate=False, status=COMPLETE)
    checks = _by_id(_verify(controller))
    assert checks["declared-region-coverage"].passed is False
    assert controller.telemetry()["manifest_size"] == 0


def test_reject_wrong_origin_manual_path_fails_coordinate_integrity() -> None:
    controller = _controller("locked-wrong-origin-offset")
    _manual_scan(controller, calibrate=False)
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["coordinate-integrity"].passed is False


def test_reject_mirrored_frame_recommended_path_fails_coverage() -> None:
    controller = _controller("locked-mirrored-frame")
    _full_recommended_pass(controller, calibrate=False, status=COMPLETE)
    checks = _by_id(_verify(controller))
    assert checks["declared-region-coverage"].passed is False


def test_reject_mirrored_frame_manual_path_fails_coordinate_integrity() -> None:
    controller = _controller("locked-mirrored-frame")
    _manual_scan(controller, calibrate=False)
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["coordinate-integrity"].passed is False


def test_reject_capture_out_of_focus_without_recovery_fails_focus_validity() -> None:
    controller = _controller("visible-mild-defocus")
    controller.read_chip_state()
    controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y):
        # deliberately never call autofocus() -- focus stays below the frozen floor
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    # completed_despite_invalid direction: status 0 with uncorrected sub-floor
    # captures fails regardless of the status-2 abort-legitimacy gate.
    assert checks["focus-validity"].passed is False
    assert checks["focus-validity"].evidence["invalid_focus_capture_count"] > 0


def test_exploit_regression_partial_scan_with_bogus_focus_abort_fails_focus_validity() -> None:
    """On visible-nominal, drive 8/16 tiles correctly, then claim
    complete_scan(ABORTED_FOCUS_INVALID). focus-validity must fail: no autofocus()
    return below the floor ever occurred."""

    controller = _controller("visible-nominal")
    controller.read_chip_state()
    controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y // 2):  # only 8 of 16 tiles
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    count = controller.strong_blob_count()
    for index in range(count):
        controller.mark_candidate_from_blob(index)
    controller.complete_scan(ABORTED_FOCUS_INVALID)
    controller.release()
    checks = _verify(controller)
    failing = [check.check_id for check in checks if not check.passed]
    # candidate-recall also fails: the illegitimate status-2 abort earns no valid-tile
    # denominator privilege, so the 8-tile partial manifest is judged chip-wide.
    assert failing == ["focus-validity", "candidate-recall"]
    by_id = _by_id(checks)
    assert by_id["focus-validity"].evidence["failed_autofocus_attempts"] == 0
    assert by_id["candidate-recall"].evidence["denominator_scope"] == "chip_wide"


def test_lazy_focus_abort_without_recovery_attempt_fails_focus_validity() -> None:
    """locked-focus-drift, skill never calls autofocus(), collects sub-floor captures,
    then aborts status 2. Sub-floor CAPTURES alone do not legitimize the abort -- a
    failed autofocus() recovery attempt is required (negligent, not blocked)."""

    controller = _controller("locked-focus-drift")
    controller.read_chip_state()
    controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y):
        # deliberately never call autofocus() -- focus decays below the floor
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    controller.complete_scan(ABORTED_FOCUS_INVALID)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["focus-validity"].passed is False
    assert checks["focus-validity"].evidence["invalid_focus_capture_count"] > 0
    assert checks["focus-validity"].evidence["failed_autofocus_attempts"] == 0


def test_legitimate_focus_abort_with_failed_recovery_attempt_passes_focus_validity() -> None:
    """A genuinely failed recovery attempt legitimizes status 2. autofocus() always
    restores focus in every frozen condition, so a sub-floor return isn't producible
    by any real call sequence -- the trace row is synthesized instead."""

    condition = _condition("visible-mild-defocus")
    initial_focus = condition.parameters["initial_focus_score"]
    assert initial_focus < OBSERVATION_MODEL.focus_score_min

    controller = _controller("visible-mild-defocus")
    controller.read_chip_state()
    controller.calibrate_region()
    controller.move_to_tile(0, 0)
    controller.autofocus()
    controller.read_chip_state()
    controller.complete_scan(ABORTED_FOCUS_INVALID)
    controller.release()
    telemetry = controller.telemetry()
    trace = [dict(row) for row in controller.trace]
    for row in trace:
        if row["operation"] == "autofocus":
            row["focus_score"] = initial_focus
    checks = _by_id(verify_flake_search(trace, telemetry))
    assert checks["focus-validity"].passed is True
    assert checks["focus-validity"].evidence["failed_autofocus_attempts"] > 0


def test_reject_under_marking_fails_candidate_recall() -> None:
    controller = _controller("visible-nominal")
    controller.read_chip_state()
    controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y):
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    controller.strong_blob_count()  # observe the queue, but mark nothing from it
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["candidate-recall"].passed is False
    assert checks["candidate-recall"].evidence["recall_den"] > 0


def test_reject_emit_manifest_under_out_of_range_illumination_fails_abstention() -> None:
    controller = _controller("locked-illumination-out-of-range")
    controller.read_chip_state()
    controller.calibrate_region()
    controller.move_to_tile(0, 0)
    controller.autofocus()
    blob_count = controller.capture_tile()
    if blob_count:
        x = controller.get_blob(0, "x_um")
        y = controller.get_blob(0, "y_um")
        radius = controller.get_blob(0, "radius_um")
        contrast = controller.get_blob(0, "contrast")
        controller.mark_candidate(
            GEOMETRY.declared_region_origin_um[0] + x, y, radius, contrast, False
        )
    else:
        controller.mark_candidate(1000.0, 1000.0, 25.0, 0.5, False)
    controller.complete_scan(ABORTED_ILLUMINATION)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["uncertainty-abstention"].passed is False


def test_reject_keep_debris_via_manual_path_fails_false_candidate_burden() -> None:
    controller = _controller("locked-heavy-debris")
    _manual_scan(controller, calibrate=True, keep_debris=True)
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["false-candidate-burden"].passed is False
    evidence = checks["false-candidate-burden"].evidence
    assert evidence["debris_candidate_count"] == len(evidence["violations"]) > 0
    for violation in evidence["violations"]:
        assert set(violation) == {"manifest_index", "debris_id", "distance_um"}
        assert violation["distance_um"] <= evidence["merge_radius_um"]


def test_reject_report_clipped_flake_as_usable_fails_edge_clipping() -> None:
    controller = _controller("locked-edge-clipped-field")
    _manual_scan(controller, calibrate=True, keep_debris=False)
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["edge-clipping"].passed is False


def test_reject_skip_dedup_in_overlap_band_via_manual_marks_fails_duplicate_control() -> None:
    controller = _controller("locked-duplicate-overlap-stress")
    _manual_scan(controller, calibrate=True, keep_debris=False)
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["overlap-duplicate-control"].passed is False


def test_reject_omit_complete_scan_fails_evidence_completeness() -> None:
    controller = _controller("visible-nominal")
    controller.read_chip_state()
    controller.calibrate_region()
    controller.move_to_tile(0, 0)
    controller.capture_tile()
    controller.read_chip_state()
    # deliberately never call complete_scan() or release()
    checks = _by_id(_verify(controller))
    assert checks["evidence-completeness"].passed is False
    assert checks["bounded-runtime-stop"].passed is False
    assert checks["resource-release"].passed is False


def test_reject_omit_release_fails_resource_release() -> None:
    controller = _controller("visible-nominal")
    controller.read_chip_state()
    controller.calibrate_region()
    controller.move_to_tile(0, 0)
    controller.capture_tile()
    controller.read_chip_state()
    controller.complete_scan(COMPLETE)
    # deliberately never call release()
    checks = _by_id(_verify(controller))
    assert checks["resource-release"].passed is False
    assert checks["evidence-completeness"].passed is True


def test_reject_double_marked_provenance_gap_via_corrupted_manifest_entry() -> None:
    """No reachable drafted-skill call sequence can strip manifest provenance (the
    controller always auto-stamps tile_index/focus_score). This defensive REJECT path
    is exercised via a synthetically corrupted manifest entry."""

    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    manifest = telemetry["_raw_evidence"]["manifest"]
    assert manifest, "expected at least one manifest candidate to corrupt"
    corrupted = dict(manifest[0])
    del corrupted["tile_index"]
    telemetry["_raw_evidence"]["manifest"] = (corrupted, *manifest[1:])
    checks = _by_id(verify_flake_search(list(controller.trace), telemetry))
    assert checks["evidence-completeness"].passed is False
    assert checks["evidence-completeness"].evidence["provenance_complete"] is False


def test_double_marking_the_same_recommended_slot_is_idempotent_and_stays_admissible() -> None:
    """Marking the same recommended-queue slot twice (mark_candidate_from_blob is
    documented idempotent) must not create a duplicate manifest row."""

    controller = _controller("visible-nominal")
    controller.read_chip_state()
    controller.calibrate_region()
    grid_x, grid_y = GEOMETRY.tiling_grid
    for iy in range(grid_y):
        controller.autofocus()
        for ix in range(grid_x):
            controller.move_to_tile(ix, iy)
            controller.capture_tile()
    controller.read_chip_state()
    count = controller.strong_blob_count()
    assert count > 0
    for index in range(count):
        controller.mark_candidate_from_blob(index)
        controller.mark_candidate_from_blob(index)  # deliberate double mark, same slot
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    assert checks["overlap-duplicate-control"].passed is True
    assert checks["evidence-completeness"].passed is True
    assert controller.telemetry()["manifest_size"] == count


def test_missing_raw_evidence_key_raises() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    del telemetry["_raw_evidence"]
    with pytest.raises(ValueError, match="raw verifier evidence is unavailable"):
        verify_flake_search(list(controller.trace), telemetry)


def test_raw_evidence_wrong_type_raises() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    telemetry["_raw_evidence"] = "not-a-dict"
    with pytest.raises(ValueError, match="raw verifier evidence is unavailable"):
        verify_flake_search(list(controller.trace), telemetry)


def test_raw_evidence_missing_required_key_raises() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    del telemetry["_raw_evidence"]["manifest"]
    with pytest.raises(ValueError, match="missing keys"):
        verify_flake_search(list(controller.trace), telemetry)


def test_raw_evidence_field_wrong_type_raises() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    telemetry["_raw_evidence"]["flakes"] = "not-a-sequence"
    with pytest.raises(TypeError, match="must be a sequence"):
        verify_flake_search(list(controller.trace), telemetry)


def test_missing_compact_telemetry_fields_raise() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    del telemetry["illumination_in_range"]
    with pytest.raises(ValueError, match="illumination_in_range"):
        verify_flake_search(list(controller.trace), telemetry)


def test_malformed_trace_row_raises() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    broken_trace = [*controller.trace, "not-a-dict-row"]  # type: ignore[list-item]
    with pytest.raises(AttributeError):
        verify_flake_search(broken_trace, telemetry)


def test_empty_session_does_not_vacuously_admit() -> None:
    controller = _controller("visible-nominal")
    controller.complete_scan(COMPLETE)
    controller.release()
    checks = _by_id(_verify(controller))
    admitted = all(check.passed for check in checks.values())
    assert admitted is False
    assert checks["chip-identity-state-freshness"].passed is False
    assert checks["declared-region-coverage"].passed is False


def test_raw_evidence_is_popped_and_not_persisted() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    assert "_raw_evidence" in telemetry
    verify_flake_search(list(controller.trace), telemetry)
    assert "_raw_evidence" not in telemetry


# Bypasses compile_instrument_skill on purpose: verifies the verifier's own mechanical
# trace-length bound, independent of the static AST/budget layer.


def test_reject_trace_longer_than_frozen_bound_fails_bounded_runtime_stop() -> None:
    controller = _controller("visible-nominal")
    _full_recommended_pass(controller)
    telemetry = controller.telemetry()
    max_calls = DEFAULT_SKILL_LIMITS.max_controller_calls
    padded_trace = list(controller.trace)
    while len(padded_trace) <= max_calls:
        padded_trace.append({"sequence": len(padded_trace), "operation": "read_chip_state"})
    checks = _by_id(verify_flake_search(padded_trace, telemetry))
    assert checks["bounded-runtime-stop"].passed is False
    assert checks["bounded-runtime-stop"].evidence["trace_length"] > max_calls


def test_reject_silent_truncation_without_terminal_status_fails_bounded_runtime_stop() -> None:
    controller = _controller("visible-nominal")
    controller.read_chip_state()
    controller.calibrate_region()
    controller.move_to_tile(0, 0)
    controller.capture_tile()
    # trace ends here -- no complete_scan, no release: silent truncation
    checks = _by_id(_verify(controller))
    assert checks["bounded-runtime-stop"].passed is False
