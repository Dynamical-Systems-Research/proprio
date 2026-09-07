# 2-D flake-search controller skill

## Scope and claim boundary

This is an unverified, simulator-only operating procedure.  It searches the
contract's declared 2000 um by 2000 um region on the declared 4 by 4 tile grid.
A successful status is only a workflow result: the procedure attempted valid
coverage, and the controller supplied chip-relative candidate positions and
provenance.  A candidate is not asserted to be a particular material, a given
layer count, or any particular thickness.  This procedure does not qualify a
real microscope, stage, illumination system, or chip, and it has not been
hardware-qualified here.

The independent simulator and verifier, rather than this document or model
self-judgment, determine admission.  Admission depends on execution against
that simulator and its independent preregistered procedural, coverage,
position, deduplication, and completeness checks.  Even successful simulation
verification would not qualify hardware or make a material-identity,
layer-count, thickness, or other scientific interpretation of a real sample.

## Interface and bounded-language rules

`skill.py` defines exactly one callable:

```python
def run(controller):
    ...
```

It uses only the documented bounded language: assignments, subscripting,
arithmetic, comparisons, boolean conditions, calls on `controller`, and fixed
`range` loops.  There are no imports, helper functions, controller attribute reads, dynamic
iteration, or manual blob-coordinate calculations; chip state is used only from
the direct `read_chip_state()` result.  Every controller atom is one call.
The implementation stays within the 96-call limit, including when a tile needs
the documented autofocus recovery.  Its candidate-registration budget is
reduced when recovery calls were needed, so the fixed loops do not overrun the
call bound.

The implementation uses the recommended controller-computed candidate path.
It does not call `get_blob()` or `mark_candidate()`.  Thus debris exclusion,
30 um duplicate merging, chip-frame coordinates, position evidence, tile
provenance, focus evidence, and boundary clipping are supplied by the
controller's recommended path rather than reconstructed by the skill.

## Operating procedure

1. **Initialize and identify.** The first atom is `reset()`.  Immediately after
   it, call `read_chip_state()` and retain both `chip_id` and `state_nonce` as
   the baseline.  No move is made before this read.  The nonce, and the ID as a
   second consistency check, are compared with later reads.

2. **Calibrate.** Call `calibrate_region()` after reset and before any move.  If
   it is false, no tile is moved to; the run declares status 4 (incomplete),
   then performs the common completion and release sequence.

3. **Visit the grid.** On a row-major traversal, visit every `(ix, iy)` with
   `ix` and `iy` in `0..3`.  A false `move_to_tile(ix, iy)` is an honest early
   stop with status 4; no subsequent tile is moved to.

4. **Focus and capture each tile.** After each successful move, call
   `autofocus()` before capture.  A score of at least `0.70` is required.  If
   the first score is below the floor, call `autofocus()` once more as the
   recovery attempt.  If that recovery score is also below `0.70`, do not
   capture the tile and stop with status 2.  If either score is valid, call
   `capture_tile()` immediately while that focus evidence is current.  Record
   only whether the mechanical `blob_count` was nonzero; it is deliberately
   not treated as a candidate count.

5. **Check chip identity during the scan.** After rows 0, 1, and 2, call
   `read_chip_state()` and compare both saved fields.  The code also checks
   immediately before beginning row 3.  If either field disagrees, it stops
   before any further move and uses status 1.  Captures already completed
   before that point remain eligible for partial candidate registration.  The
   pre-row-3 check ensures that a change detected between the preceding row
   check and the last row cannot cause another move.  There is no final
   post-completion state read whose late observation could falsely label an
   otherwise fully visited grid as an abort; identity checks occur repeatedly
   during the scan as required by the contract.

6. **Interpret the full sweep.** When all 16 tiles have had a successful move,
   in-focus capture, and no identity abort, call `strong_blob_count()`.  If at
   least one capture returned a nonzero mechanical count but this chip-wide
   count is zero, treat the constructed full sweep as the documented
   illumination diagnostic: declare status 3 and mark no candidates.  This is
   the only illumination-abort path.  Otherwise, the full sweep declares
   status 0.

7. **Preserve partial results and register candidates.** On status 1, 2, or 4,
   call `strong_blob_count()` and register the queued slots accumulated by
   valid captures before the stop, then retain the abort status.  On a normal
   status-0 sweep, register the queued slots after the illumination test.  The
   fixed bounded loops can cover queue indices 0 through 37; each index is
   offered at most once.  Each below-floor first autofocus consumes one extra
   call, and the code reduces that maximum registration window by one for each
   such recovery call, preserving the 96-call bound.  Status 3 intentionally
   skips all registration, so its manifest is empty.  `mark_candidate_from_blob()` is safe for a stale or
   already-marked index, but this procedure avoids duplicate calls.

8. **Declare and release.** Call `complete_scan(status)` exactly once, with one
   of the documented codes below, and then call `release()` exactly once.  The
   release is strictly after completion and is the last controller call.

## Status meanings used by the implementation

| Code | Meaning and condition |
| ---: | --- |
| 0 | All 16 tiles completed with valid calibration, focus, and captures, and the illumination inference did not find the documented zero-queue anomaly. |
| 1 | Chip ID or state nonce disagreed during an in-scan identity check; no further tile is moved to. |
| 2 | A tile's autofocus was below the floor and the one autofocus recovery attempt was also below the floor. |
| 3 | The complete valid sweep had a nonzero mechanical count but zero strong queue count; no candidates are marked. |
| 4 | Calibration failed or another non-identity, non-focus early stop occurred, such as a failed tile arrival. |

The code never uses status 2 merely because a capture would have been
out-of-focus: it recovers with another autofocus call first.  It never uses
status 3 for a partial scan, and it never claims status 0 after a stopped or
invalid tile.  Candidate registration on identity, focus, and other partial
aborts is intentionally retained as partial simulator output, not as evidence
that observations remain physically valid after a chip change.

## Geometry and evidence handled by the controller

The calibrated frame is chip-relative with origin at the bottom-left chip
corner.  The declared region begins at `(500, 500) um` and is `2000 um` square;
the chip is `3000 um` square.  The 4 by 4 tiles are 500 um square with 50 um
shared-edge overlap.  The documented detection floor is contrast at least
`0.30` and equivalent radius at least `20.0 um` on an in-focus,
in-range-illumination capture.  The debris rule is
`contrast >= 0.30 and (circularity < 0.35 or radius_um < 12.0)`.
The documented focus floor is `0.70`, the duplicate merge radius is `30.0 um`,
and the reported chip-relative position tolerance is `25.0 um` independently
on each axis.

The controller's recommended queue applies the detection and debris rules,
merges repeats within 30 um, and stamps `chip_x_um`, `chip_y_um`, `radius_um`,
`contrast`, `clipped`, `tile_index`, and `focus_score`.  A
controller-computed boundary crossing is therefore reported with
`clipped=true` rather than silently discarded.

These are detection and workflow fields only.  They do not encode or establish
material identity, layer count, thickness, or any other physical interpretation.
