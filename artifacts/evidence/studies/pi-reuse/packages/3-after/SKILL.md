# 2-D flake-search controller skill

## Scope and claim boundary

This is a simulator-only workflow for the source contract's declared 2000 um by
2000 um region.  A status-0 run means that the calibrated 4 by 4 region was
visited with valid captures and that controller-computed candidate records were
registered.  It does **not** identify a material, layer count, thickness, or any
other scientific property, and it does not qualify a real microscope, chip,
stage, or illumination system.

Admission is determined by execution against the supplied simulator and its
independent preregistered checks, not by this document or model self-judgment.
Development verification does not establish private admission or hardware
qualification.

## Operating procedure

`skill.py` defines only `run(controller)`.  It uses the recommended
controller-computed candidate path and no imports, helper functions, manual
blob coordinates, or controller-state reads.

1. `reset()` is first.  Read and retain the initial `chip_id` and `state_nonce`,
   then call `calibrate_region()` before any move.  Calibration failure stops
   with status 4 and still completes/releases the session.
2. Traverse four fixed row loops, each over `ix` 0 through 3, using `iy` 0,
   1, 2, and 3.  A failed arrival stops further moves with status 4.
3. After every successful move, call `autofocus()` immediately before the
   capture.  A score below 0.70 gets exactly one autofocus recovery attempt;
   if that attempt is still below 0.70, stop without capturing that tile and
   use status 2.  A recovered valid score permits the capture.
4. Read chip state after rows 0, 1, and 2.  Compare both saved fields.  On a
   mismatch, stop before moving to another tile and use status 1.  Captures
   before the stop remain eligible partial results.
5. After the sweep (or an early stop), call `strong_blob_count()`.  If the
   sweep reached status 0, at least one mechanical `blob_count` was nonzero,
   and the strong count is zero, use status 3 and mark no candidates.  This is
   the documented illumination inference.  Status 3 is not used for partial
   scans.
6. Otherwise offer queue indices 0 through 22 once each with
   `mark_candidate_from_blob()`, stopping at the current `strong_blob_count()`.
   This preserves controller-side debris exclusion, 30 um deduplication,
   chip-frame positions, focus/tile provenance, and boundary clipping.  Partial
   status-1, status-2, and status-4 results are registered before completion.
7. Call `complete_scan(status)` exactly once, followed immediately by exactly
   one `release()`.

The fixed candidate window is 23 slots.  It is deliberately bounded because
sixteen possible autofocus recovery calls plus the required scan, three
in-scan identity reads, queue read, completion, and release consume the
96-call budget in the static bounded-language checker.  The documented source
does not state a larger queue bound; a scene producing more than 23 queue slots
would require a future budget/procedure change to preserve complete candidate
recall.  The procedure also has no identity checkpoint after the final row, so
an identity change occurring only after the last checkpoint may not be
observed; late observations must not be relabeled as a complete scan after all
16 tiles are already validly covered.

## Status codes

| Code | Meaning in this procedure |
|---:|---|
| 0 | All 16 tiles were validly captured and the illumination inference did not trigger. |
| 1 | A later chip ID or state nonce disagreed with the initial state. |
| 2 | Autofocus and its one recovery attempt both failed on a tile. |
| 3 | A complete valid sweep had nonzero mechanical detections but zero valid strong queue entries; no candidates are marked. |
| 4 | Calibration, arrival, or another non-identity/non-focus early stop occurred. |

## Contract constants used

The calibrated chip frame is bottom-left-origin.  The declared region starts at
(500, 500) um and is 2000 um square on a 3000 um chip.  The grid is 4 by 4,
with 500 um tiles and 50 um shared-edge overlap.  The focus floor is 0.70;
detectability is contrast at least 0.30 and radius at least 20 um; debris is
`contrast >= 0.30 and (circularity < 0.35 or radius_um < 12.0)`; duplicate
merging is within 30 um; and the independent position tolerance is 25 um per
axis.  These are workflow/detection constants, not material-identification
claims.  The recommended path supplies candidate coordinates, radius,
contrast, clipping, tile index, and focus evidence from the controller.

## Development execution record

The first draft was rejected statically for branch depth greater than 4.  A
nesting repair was then rejected statically because its conservative controller
call bound was 116, above 96.  The current fixed-row/fixed-registration draft
was executed once through all four available development conditions:

- nominal: status 0;
- focus: status 0;
- stale-chip: status 1 with partial candidates;
- illumination: status 3 with an empty manifest.

That execution reported passing development checks for static safety, runtime
completion, identity freshness, coverage, focus validity, candidate recall,
deduplication, clipping, coordinate/evidence integrity, bounded stopping, and
resource release.  The supplied focus condition returned 0.95 on each
autofocus call, so that run did not exercise a below-floor recovery.  These are
development results only; they are not private admission, hardware
qualification, or scientific validation.
