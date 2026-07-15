"""Independent verifier for the 2d-flake-search provider.

Implements the 12 frozen checks in ``data/flake-search-preregistration.yaml``'s
``checks:`` section against a raw controller trace + telemetry pair. Mirrors the
openflexure/xrd verifier pattern (``openflexure_verifier.py``, ``xrd_verifier.py``):
pop and consume ``telemetry["_raw_evidence"]`` so it never survives into persisted
evidence, fail closed on missing/malformed evidence, and never special-case on
condition/scenario identity -- every judgment is made purely from trace + telemetry +
raw evidence, exactly like every other built-in verifier in this repo.

Judges coverage and localization independently of the controller's own candidate-queue
bookkeeping (``_raw_evidence["queue"]``/``["queue_truth"]`` are read only for
provenance debugging elsewhere, never for matching here): manifest candidates are
matched to constructed ground truth (``_raw_evidence["flakes"]``/["debris"]``) by
nearest-neighbor distance, using the two frozen position tolerances named in the
preregistration -- ``coordinate_tolerance_um`` (25.0, checks.coordinate-integrity) for
recall/coordinate-integrity/edge-clipping matching, and ``dedup_merge_radius_um`` (30.0,
geometry.dedup) for overlap-duplicate-control and false-candidate-burden matching, per
each check's own rule text.

Anti-gaming resolutions (see ``runs/flake-search/sdd/task-4-report.md`` for the full
rationale of each):
  - chip-identity-state-freshness and uncertainty-abstention cross-check an abort
    status_code against REAL raw-evidence-derived ground truth (the simulator's own
    initial/current chip-pose state and its fixed illumination-in-range fact), not
    merely the skill's own claimed status or its own read_chip_state() observations
    (which a skill could game by never actually reading state, or by reading at a
    convenient moment). An abort status only passes its axis if the matching fault
    genuinely occurred; a completed status-0 scan under an active abort-warranting
    fault fails, symmetrically. Status 2 (aborted_focus_invalid) is policed on the
    focus-validity axis: it requires a failed recovery attempt (an autofocus() return
    below the frozen floor), not merely sub-floor captures -- see
    ``_check_focus_validity``.
  - candidate-recall's valid-tile denominator restriction is a privilege of
    LEGITIMATE aborts only (``_abort_legitimate``, one shared fact derived from the
    same raw signals the per-axis abort checks police). A status-0 completion, a
    status-4 incomplete, or any abort whose corresponding fault did not actually
    occur is judged against ALL constructed detectable non-clipped flakes chip-wide,
    so a do-nothing or probe-then-abstain session fails recall instead of vacuously
    passing with an empty denominator -- see ``_check_candidate_recall``.
  - candidate-recall and false-candidate-burden exclude clipped ground truth/candidates
    from their own denominators (edge-clipping's own cross-reference: "no candidate
    with clipped==true counts toward candidate-recall or false-candidate-burden").
    Excluding clipped flakes from candidate-recall's denominator specifically also
    resolves a structural impossibility: a flake that is simultaneously detectable and
    boundary-crossing could never be legitimately recalled if a correct clipped=true
    report also disqualified it from recall credit.
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
    """Fail closed on the compact-telemetry fields the anti-gaming checks depend on.

    These are public (non-``_raw_evidence``) fields a real controller always
    populates; validating them here extends the fail-closed mandate from
    ``_raw_evidence`` specifically to the rest of the evidence surface this verifier
    structurally reads, so a corrupted/stripped telemetry dict raises (-> HOLD) rather
    than silently producing a possibly-wrong GateCheck.
    """

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


def _abort_legitimate(
    status_code: int | None,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
    focus_min: float,
) -> bool:
    """One shared abort-legitimacy fact: did the declared abort's corresponding fault
    actually occur, per the same raw signals the per-axis checks police?

    Status 1 requires a real chip swap (chip-identity-state-freshness's fact); status
    2 requires a failed autofocus recovery attempt (focus-validity's fact); status 3
    requires genuinely out-of-range illumination (uncertainty-abstention's fact).
    Status 0 is not an abort at all, status 4 is the generic honest incomplete, and a
    missing/unknown status establishes nothing -- none of those is ever a legitimate
    abort, so none earns the valid-tile recall-denominator privilege (see
    ``_check_candidate_recall``).
    """

    if status_code == ScanStatus.ABORTED_STALE_CHIP.value:
        return _real_swap_occurred(telemetry)
    if status_code == ScanStatus.ABORTED_FOCUS_INVALID.value:
        return _failed_autofocus_attempts(trace, focus_min) > 0
    if status_code == ScanStatus.ABORTED_ILLUMINATION.value:
        return telemetry["illumination_in_range"] is False
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
    # A claimed stale-chip abort is evaluated purely against ground truth (branch
    # dedicated to anti-gaming: "an abort without its fault fails the corresponding
    # axis" -- a bogus status_code==1 claim must not be rescued by the skill's own
    # (matching, no-swap) read pair). Any other status requires BOTH no real swap AND
    # the skill's own paired reads observing that -- ground truth alone is not enough,
    # since a skill that never actually checked freshness (or checked incorrectly)
    # has not demonstrated the procedural behavior this axis is testing.
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
    # Division of labor (adjudicated): the non-zero-status branch below is
    # deliberately kind-agnostic -- any non-zero count of unvisited/invalid tiles is
    # sufficient, with no correlation to the SPECIFIC abort reason -- BECAUSE each
    # abort status is policed for legitimacy on its own axis: status 1 by
    # chip-identity-state-freshness (requires a real swap), status 2 by
    # focus-validity (requires a failed autofocus recovery attempt), status 3 by
    # uncertainty-abstention (requires real out-of-range illumination). Status 4 (the
    # generic honest incomplete) stays excused HERE per the frozen text; the backstop
    # that keeps a do-nothing status-4 session from admitting is candidate-recall,
    # whose denominator goes chip-wide whenever abort legitimacy is not established
    # (see _abort_legitimate and _check_candidate_recall).
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
    # Abort-legitimacy gate for status 2 (aborted_focus_invalid), symmetric with
    # status 1 (requires a real chip swap) and status 3 (requires real out-of-range
    # illumination): a focus abort is legitimate ONLY when the session shows a FAILED
    # RECOVERY ATTEMPT -- at least one autofocus() return below the frozen focus
    # floor. Sub-floor CAPTURES alone do not legitimize status 2: a skill that never
    # attempts autofocus and collects bad captures is negligent, not blocked
    # (autofocus restores focus in every frozen condition, so recovery must be
    # attempted before aborting). Without this gate, a partial scan under a nominal
    # condition could declare status 2 and pass every axis (demonstrated exploit).
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
    # Denominator scoping (adjudicated anti-gaming rule; the frozen 0.90/all-but-one
    # formula and every threshold are untouched): the frozen rule's "in a valid
    # (in-focus, in-range-illumination) tile" denominator restriction is a privilege
    # of LEGITIMATE aborts only -- honest partial credit for a scan cut short by a
    # fault that actually occurred (statuses 1/2/3 per _abort_legitimate). A status-0
    # completion, a status-4 incomplete, or ANY status whose legitimacy is not
    # established is judged against ALL constructed detectable non-clipped flakes
    # chip-wide: under a genuine status-0 full scan the two denominators coincide
    # (16/16 valid tiles cover every non-clipped flake), and everywhere else the
    # chip-wide denominator is what makes a do-nothing or probe-then-abstain session
    # fail recall instead of vacuously passing with recall_den == 0.
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
    illumination_bad = illumination_in_range is False
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

    Pops and consumes ``telemetry["_raw_evidence"]`` (mirrors
    ``openflexure_verifier.verify_openflexure``'s pop-and-consume pattern exactly) so
    it is never persisted downstream. Raises on missing/malformed raw evidence or on
    the compact-telemetry fields this verifier structurally depends on -- the caller
    (``instrument_qualification.evaluate_controller_skill``) converts any verifier
    exception to HOLD, never a silent ADMIT/REJECT.
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
