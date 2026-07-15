"""Independent verifier for the 2d-flake-search provider.

Implements the 12 frozen checks in ``data/flake-search-preregistration.yaml``'s
``checks:`` section against a raw controller trace + telemetry pair, mirroring the
openflexure/xrd verifier pattern: pop and consume ``telemetry["_raw_evidence"]`` so it
never survives into persisted evidence, and fail closed on missing/malformed evidence.

Manifest candidates are matched to constructed ground truth by nearest-neighbor
distance, using ``coordinate_tolerance_um`` (25.0) for recall/coordinate-integrity/
edge-clipping and ``dedup_merge_radius_um`` (30.0) for overlap-duplicate-control and
false-candidate-burden.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from proprio.flake_search_types import (
    GeometryConfig,
    ScanStatus,
    load_flake_search_preregistration,
)
from proprio.instrument_qualification import DEFAULT_SKILL_LIMITS
from proprio.instrument_types import GateCheck

_VALID_STATUS_CODES = frozenset(status.value for status in ScanStatus)

_RAW_EVIDENCE_REQUIRED_KEYS = (
    "flakes",
    "debris",
    "chip_pose_timeline",
    "acquisition_timeline",
    "manifest",
    "queue",
    "queue_truth",
    "released",
)
_RAW_EVIDENCE_SEQUENCE_KEYS = (
    "flakes",
    "debris",
    "acquisition_timeline",
    "manifest",
    "queue",
    "queue_truth",
)


def _gate(check_id: str, passed: bool, **evidence: Any) -> GateCheck:
    return GateCheck(check_id=check_id, passed=bool(passed), evidence=evidence)


def _validate_raw_evidence(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("flake-search raw verifier evidence is unavailable")
    missing = [key for key in _RAW_EVIDENCE_REQUIRED_KEYS if key not in raw]
    if missing:
        raise ValueError(f"flake-search raw verifier evidence is missing keys: {missing}")
    for key in _RAW_EVIDENCE_SEQUENCE_KEYS:
        if not isinstance(raw[key], (list, tuple)):
            raise TypeError(f"flake-search raw verifier evidence field {key!r} must be a sequence")
    return raw


def _validate_compact_telemetry(telemetry: dict[str, Any]) -> None:
    """Fail closed on the public telemetry fields the abort-legitimacy checks depend
    on, so a corrupted/stripped dict raises (-> HOLD) rather than producing a wrong
    GateCheck."""

    if not isinstance(telemetry.get("initial_state_nonce"), int) or not isinstance(
        telemetry.get("current_state_nonce"), int
    ):
        raise ValueError("flake-search telemetry is missing a valid chip state-nonce pair")
    if not isinstance(telemetry.get("illumination_in_range"), bool):
        raise ValueError("flake-search telemetry is missing a valid illumination_in_range flag")


def _status_code(trace: Sequence[dict[str, Any]]) -> int | None:
    for row in trace:
        if row.get("operation") == "complete_scan":
            value = row.get("status_code")
            return (
                int(value)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else None
            )
    return None


def _real_swap_occurred(telemetry: dict[str, Any]) -> bool:
    return bool(telemetry["initial_state_nonce"] != telemetry["current_state_nonce"])


def _failed_autofocus_attempts(trace: Sequence[dict[str, Any]], focus_min: float) -> int:
    return sum(
        1
        for row in trace
        if row.get("operation") == "autofocus" and row.get("focus_score", math.inf) < focus_min
    )


def _illumination_bad(telemetry: dict[str, Any]) -> bool:
    return telemetry["illumination_in_range"] is False


def _abort_legitimate(
    status_code: int | None,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
    focus_min: float,
) -> bool:
    """Did the declared abort's corresponding fault actually occur? Status 1 requires
    a real chip swap, status 2 a failed autofocus recovery attempt, status 3 genuinely
    out-of-range illumination. Status 0/4/unknown are never legitimate, so none earns
    the valid-tile recall-denominator privilege (see ``_check_candidate_recall``).
    """

    if status_code == ScanStatus.ABORTED_STALE_CHIP.value:
        return _real_swap_occurred(telemetry)
    if status_code == ScanStatus.ABORTED_FOCUS_INVALID.value:
        return _failed_autofocus_attempts(trace, focus_min) > 0
    if status_code == ScanStatus.ABORTED_ILLUMINATION.value:
        return _illumination_bad(telemetry)
    return False


def _distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _tile_index_for(x: float, y: float, geometry: GeometryConfig) -> tuple[int, int]:
    origin_x, origin_y = geometry.declared_region_origin_um
    tile_w, tile_h = geometry.tile_size_um
    grid_x, grid_y = geometry.tiling_grid
    ix = int((x - origin_x) // tile_w)
    iy = int((y - origin_y) // tile_h)
    return min(max(ix, 0), grid_x - 1), min(max(iy, 0), grid_y - 1)


def _valid_tiles(acquisitions: Sequence[dict[str, Any]]) -> set[tuple[int, int]]:
    return {
        (int(row["tile_ix"]), int(row["tile_iy"]))
        for row in acquisitions
        if row.get("valid") is True
    }


def _all_tiles(geometry: GeometryConfig) -> set[tuple[int, int]]:
    grid_x, grid_y = geometry.tiling_grid
    return {(ix, iy) for ix in range(grid_x) for iy in range(grid_y)}


def _nearest(
    point: tuple[float, float], truth: Sequence[tuple[str, float, float]]
) -> tuple[str | None, float]:
    """Nearest (id, distance) among (id, x, y) truth tuples; (None, inf) if empty."""

    best_id: str | None = None
    best_distance = math.inf
    for object_id, tx, ty in truth:
        distance = _distance(point[0], point[1], tx, ty)
        if distance < best_distance:
            best_distance = distance
            best_id = object_id
    return best_id, best_distance


def _check_chip_identity(trace: Sequence[dict[str, Any]], telemetry: dict[str, Any]) -> GateCheck:
    read_events = [row for row in trace if row.get("operation") == "read_chip_state"]
    status_code = _status_code(trace)
    initial_nonce = telemetry["initial_state_nonce"]
    current_nonce = telemetry["current_state_nonce"]
    real_swap = _real_swap_occurred(telemetry)
    observed_match = (
        len(read_events) >= 2
        and read_events[0].get("chip_id") == read_events[-1].get("chip_id")
        and read_events[0].get("state_nonce") == read_events[-1].get("state_nonce")
    )
    # A claimed stale-chip abort is judged purely against ground truth (a bogus
    # status_code==1 claim can't be rescued by a matching, no-swap read pair). Any
    # other status requires both no real swap AND the skill's own reads observing it.
    if status_code == ScanStatus.ABORTED_STALE_CHIP.value:
        passed = real_swap
    else:
        passed = observed_match and not real_swap
    return _gate(
        "chip-identity-state-freshness",
        passed,
        read_chip_state_calls=len(read_events),
        observed_pre_post_match=observed_match,
        real_swap_occurred=real_swap,
        status_code=status_code,
        initial_state_nonce=initial_nonce,
        current_state_nonce=current_nonce,
    )


def _check_declared_region_coverage(
    trace: Sequence[dict[str, Any]],
    acquisitions: Sequence[dict[str, Any]],
    geometry: GeometryConfig,
) -> GateCheck:
    status_code = _status_code(trace)
    all_tiles = _all_tiles(geometry)
    valid_tiles = _valid_tiles(acquisitions)
    incomplete_count = len(all_tiles - valid_tiles)
    # The non-zero-status branch is kind-agnostic: any non-zero uncovered-tile count
    # passes, because each abort status is policed for legitimacy on its own axis
    # elsewhere (_abort_legitimate). A do-nothing status-4 session is excused here but
    # caught by candidate-recall's chip-wide denominator instead.
    if status_code == ScanStatus.COMPLETE.value:
        passed = incomplete_count == 0
    elif status_code in _VALID_STATUS_CODES:
        passed = incomplete_count > 0
    else:
        passed = False
    return _gate(
        "declared-region-coverage",
        passed,
        status_code=status_code,
        total_tiles=len(all_tiles),
        valid_tiles=len(valid_tiles),
        incomplete_or_invalid_tiles=incomplete_count,
    )


def _check_overlap_duplicate_control(
    manifest: Sequence[dict[str, Any]], merge_radius: float
) -> GateCheck:
    non_clipped = [c for c in manifest if c.get("clipped") is False]
    violations: list[dict[str, Any]] = []
    for i in range(len(non_clipped)):
        for j in range(i + 1, len(non_clipped)):
            a, b = non_clipped[i], non_clipped[j]
            distance = _distance(a["chip_x_um"], a["chip_y_um"], b["chip_x_um"], b["chip_y_um"])
            if distance <= merge_radius:
                violations.append({"pair": [i, j], "distance_um": distance})
    return _gate(
        "overlap-duplicate-control",
        len(violations) == 0,
        merge_radius_um=merge_radius,
        non_clipped_candidate_count=len(non_clipped),
        violation_count=len(violations),
        violations=violations,
    )


def _check_focus_validity(
    trace: Sequence[dict[str, Any]],
    acquisitions: Sequence[dict[str, Any]],
    manifest: Sequence[dict[str, Any]],
    focus_min: float,
) -> GateCheck:
    status_code = _status_code(trace)
    manifest_below_floor = sum(1 for c in manifest if c.get("focus_score", -1.0) < focus_min)
    invalid_focus_captures = sum(1 for a in acquisitions if a.get("focus_score", -1.0) < focus_min)
    completed_despite_invalid = (
        status_code == ScanStatus.COMPLETE.value and invalid_focus_captures > 0
    )
    failed_autofocus_attempts = _failed_autofocus_attempts(trace, focus_min)
    # A focus abort (status 2) is legitimate only with a failed recovery attempt (an
    # autofocus() return below the floor); sub-floor captures alone don't qualify,
    # since autofocus always restores focus in every frozen condition.
    if status_code == ScanStatus.ABORTED_FOCUS_INVALID.value:
        abort_legitimate = failed_autofocus_attempts > 0
    else:
        abort_legitimate = True
    passed = manifest_below_floor == 0 and not completed_despite_invalid and abort_legitimate
    return _gate(
        "focus-validity",
        passed,
        focus_score_min=focus_min,
        manifest_candidates_below_floor=manifest_below_floor,
        invalid_focus_capture_count=invalid_focus_captures,
        failed_autofocus_attempts=failed_autofocus_attempts,
        status_code=status_code,
    )


def _check_candidate_recall(
    manifest: Sequence[dict[str, Any]],
    flakes: Sequence[dict[str, Any]],
    acquisitions: Sequence[dict[str, Any]],
    debris: Sequence[dict[str, Any]],
    geometry: GeometryConfig,
    tolerance: float,
    contrast_min: float,
    radius_min: float,
    status_code: int | None,
    legitimate_abort: bool,
) -> GateCheck:
    # The valid-tile denominator is a privilege of LEGITIMATE aborts only (honest
    # partial credit). Everything else -- status-0 completion, status-4 incomplete, an
    # illegitimate abort -- is judged against all detectable non-clipped flakes
    # chip-wide, so a do-nothing or probe-then-abstain session fails recall instead of
    # vacuously passing with recall_den == 0.
    valid_tiles = _valid_tiles(acquisitions)
    eligible_flake_ids = {
        flake["flake_id"]
        for flake in flakes
        if flake.get("clipped") is False
        and flake["contrast"] >= contrast_min
        and flake["radius_um"] >= radius_min
        and (
            not legitimate_abort
            or _tile_index_for(flake["chip_x_um"], flake["chip_y_um"], geometry) in valid_tiles
        )
    }
    flake_ids = {flake["flake_id"] for flake in flakes}
    truth = [(flake["flake_id"], flake["chip_x_um"], flake["chip_y_um"]) for flake in flakes] + [
        (item["debris_id"], item["chip_x_um"], item["chip_y_um"]) for item in debris
    ]
    matched_flake_ids: set[str] = set()
    for candidate in manifest:
        if candidate.get("clipped", True):
            continue
        object_id, distance = _nearest((candidate["chip_x_um"], candidate["chip_y_um"]), truth)
        if object_id is not None and distance <= tolerance and object_id in flake_ids:
            matched_flake_ids.add(object_id)
    recall_num = len(eligible_flake_ids & matched_flake_ids)
    recall_den = len(eligible_flake_ids)
    required_num = 0 if recall_den == 0 else min(recall_den - 1, math.ceil(0.90 * recall_den))
    return _gate(
        "candidate-recall",
        recall_num >= required_num,
        recall_den=recall_den,
        recall_num=recall_num,
        required_num=required_num,
        coordinate_tolerance_um=tolerance,
        status_code=status_code,
        abort_legitimate=legitimate_abort,
        denominator_scope="valid_tiles" if legitimate_abort else "chip_wide",
    )


def _check_false_candidate_burden(
    manifest: Sequence[dict[str, Any]], debris: Sequence[dict[str, Any]], merge_radius: float
) -> GateCheck:
    debris_truth = [(item["debris_id"], item["chip_x_um"], item["chip_y_um"]) for item in debris]
    matches: list[dict[str, Any]] = []
    for index, candidate in enumerate(manifest):
        if candidate.get("clipped", True):
            continue
        object_id, distance = _nearest(
            (candidate["chip_x_um"], candidate["chip_y_um"]), debris_truth
        )
        if object_id is not None and distance <= merge_radius:
            matches.append(
                {"manifest_index": index, "debris_id": object_id, "distance_um": distance}
            )
    return _gate(
        "false-candidate-burden",
        len(matches) == 0,
        merge_radius_um=merge_radius,
        debris_candidate_count=len(matches),
        violations=matches,
    )


def _check_edge_clipping(
    manifest: Sequence[dict[str, Any]], flakes: Sequence[dict[str, Any]], tolerance: float
) -> GateCheck:
    flake_truth = [(flake["flake_id"], flake["chip_x_um"], flake["chip_y_um"]) for flake in flakes]
    flakes_by_id = {flake["flake_id"]: flake for flake in flakes}
    violations: list[dict[str, Any]] = []
    for index, candidate in enumerate(manifest):
        object_id, distance = _nearest(
            (candidate["chip_x_um"], candidate["chip_y_um"]), flake_truth
        )
        if object_id is None or distance > tolerance:
            continue
        truth_clipped = flakes_by_id[object_id]["clipped"]
        if truth_clipped and not candidate.get("clipped", False):
            violations.append({"manifest_index": index, "flake_id": object_id})
    return _gate(
        "edge-clipping",
        len(violations) == 0,
        coordinate_tolerance_um=tolerance,
        violation_count=len(violations),
    )


def _check_coordinate_integrity(
    manifest: Sequence[dict[str, Any]],
    flakes: Sequence[dict[str, Any]],
    debris: Sequence[dict[str, Any]],
    tolerance: float,
) -> GateCheck:
    truth = [(flake["flake_id"], flake["chip_x_um"], flake["chip_y_um"]) for flake in flakes] + [
        (item["debris_id"], item["chip_x_um"], item["chip_y_um"]) for item in debris
    ]
    truth_points = {object_id: (tx, ty) for object_id, tx, ty in truth}
    violations: list[dict[str, Any]] = []
    checked = 0
    for index, candidate in enumerate(manifest):
        if candidate.get("clipped", True):
            continue
        checked += 1
        object_id, _distance = _nearest((candidate["chip_x_um"], candidate["chip_y_um"]), truth)
        if object_id is None:
            violations.append({"manifest_index": index, "reason": "no_truth_available"})
            continue
        true_x, true_y = truth_points[object_id]
        dx = abs(candidate["chip_x_um"] - true_x)
        dy = abs(candidate["chip_y_um"] - true_y)
        if dx > tolerance or dy > tolerance:
            violations.append({"manifest_index": index, "dx_um": dx, "dy_um": dy})
    return _gate(
        "coordinate-integrity",
        len(violations) == 0,
        coordinate_tolerance_um=tolerance,
        candidates_checked=checked,
        violation_count=len(violations),
    )


def _check_uncertainty_abstention(
    trace: Sequence[dict[str, Any]], manifest: Sequence[dict[str, Any]], telemetry: dict[str, Any]
) -> GateCheck:
    status_code = _status_code(trace)
    illumination_in_range = telemetry["illumination_in_range"]
    illumination_bad = _illumination_bad(telemetry)
    if status_code == ScanStatus.ABORTED_ILLUMINATION.value:
        passed = illumination_bad and len(manifest) == 0
    elif illumination_bad:
        passed = False
    else:
        passed = True
    return _gate(
        "uncertainty-abstention",
        passed,
        status_code=status_code,
        illumination_in_range=illumination_in_range,
        manifest_size=len(manifest),
    )


def _check_evidence_completeness(
    trace: Sequence[dict[str, Any]], manifest: Sequence[dict[str, Any]]
) -> GateCheck:
    complete_events = [row for row in trace if row.get("operation") == "complete_scan"]
    called_once_valid = (
        len(complete_events) == 1 and complete_events[0].get("status_code") in _VALID_STATUS_CODES
    )
    provenance_ok = all(
        isinstance(c.get("tile_index"), int)
        and c.get("tile_index") >= 0
        and isinstance(c.get("focus_score"), (int, float))
        for c in manifest
    )
    return _gate(
        "evidence-completeness",
        called_once_valid and provenance_ok,
        complete_scan_calls=len(complete_events),
        manifest_size=len(manifest),
        provenance_complete=provenance_ok,
    )


def _check_bounded_runtime_stop(trace: Sequence[dict[str, Any]]) -> GateCheck:
    max_calls = DEFAULT_SKILL_LIMITS.max_controller_calls
    within_bound = len(trace) <= max_calls
    reached_terminal = any(row.get("operation") == "complete_scan" for row in trace)
    return _gate(
        "bounded-runtime-stop",
        within_bound and reached_terminal,
        trace_length=len(trace),
        max_controller_calls=max_calls,
        reached_terminal_status=reached_terminal,
    )


def _check_resource_release(trace: Sequence[dict[str, Any]]) -> GateCheck:
    complete_index = next(
        (i for i, row in enumerate(trace) if row.get("operation") == "complete_scan"), None
    )
    release_indices = [i for i, row in enumerate(trace) if row.get("operation") == "release"]
    passed = (
        len(release_indices) == 1
        and complete_index is not None
        and complete_index < release_indices[0]
    )
    return _gate(
        "resource-release",
        passed,
        release_calls=len(release_indices),
        complete_scan_index=complete_index,
        release_index=release_indices[0] if release_indices else None,
    )


def verify_flake_search(
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    """Adapt one raw flake-search controller session to the 12 frozen checks.

    Pops ``telemetry["_raw_evidence"]`` so it is never persisted downstream. Raises on
    missing/malformed evidence; the caller converts any verifier exception to HOLD,
    never a silent ADMIT/REJECT.
    """

    raw = _validate_raw_evidence(telemetry.pop("_raw_evidence", None))
    _validate_compact_telemetry(telemetry)

    prereg = load_flake_search_preregistration()
    geometry = prereg.geometry
    observation_model = prereg.observation_model

    trace = tuple(trace)
    manifest = list(raw["manifest"])
    flakes = list(raw["flakes"])
    debris = list(raw["debris"])
    acquisitions = list(raw["acquisition_timeline"])
    status_code = _status_code(trace)
    legitimate_abort = _abort_legitimate(
        status_code, trace, telemetry, observation_model.focus_score_min
    )

    return (
        _check_chip_identity(trace, telemetry),
        _check_declared_region_coverage(trace, acquisitions, geometry),
        _check_overlap_duplicate_control(manifest, geometry.dedup_merge_radius_um),
        _check_focus_validity(trace, acquisitions, manifest, observation_model.focus_score_min),
        _check_candidate_recall(
            manifest,
            flakes,
            acquisitions,
            debris,
            geometry,
            observation_model.coordinate_tolerance_um,
            geometry.detectability_contrast_min,
            geometry.detectability_radius_um_min,
            status_code,
            legitimate_abort,
        ),
        _check_false_candidate_burden(manifest, debris, geometry.dedup_merge_radius_um),
        _check_edge_clipping(manifest, flakes, observation_model.coordinate_tolerance_um),
        _check_coordinate_integrity(
            manifest, flakes, debris, observation_model.coordinate_tolerance_um
        ),
        _check_uncertainty_abstention(trace, manifest, telemetry),
        _check_evidence_completeness(trace, manifest),
        _check_bounded_runtime_stop(trace),
        _check_resource_release(trace),
    )
