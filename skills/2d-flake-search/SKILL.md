---
name: 2d-flake-search
description: Bounded optical scan of a declared 2000x2000um chip region for exfoliated 2D-material flake candidates, driven entirely through the proprio.flake_search controller inside a call- and loop-limited executor.
---

## Purpose and claim boundary

This is a simulator-only development skill for `proprio.flake_search.2d-flake-search`. It
runs an automated search over a declared 2000 x 2000 um chip region, tiled as a 4x4 grid
of 500 x 500 um tiles, looking for candidate flakes among background debris. It cannot
qualify a real microscope or a real chip. The only claim it can make is workflow-level:
it covered the declared region, it reported candidate positions within the documented
accuracy, it kept its own chip-identity bookkeeping current, and it stopped and reported
honestly when conditions made a reliable search impossible. Nothing it reports is a
material-identity, layer-count, or thickness claim, and no controller field encodes one.
Hardware validation is a separate, later qualification gate.

Admission is decided by an independent simulator and verifier, external to this skill,
that judge the executed session against preregistered checks (procedural compliance,
coverage, positional accuracy, deduplication, completeness). The skill cannot set or
override those checks, and the model's own judgment of a run is not the admission
authority. Passing simulation verification does not itself qualify hardware, and it does
not make any material-identity, layer-count, or other scientific interpretation of a
real sample.

## Entry point

`skill.py` defines exactly one function, `run(controller)`, executed inside a restricted
interpreter: no imports, no comprehensions/lambdas/while/try/classes, no reads of
controller attributes (only calls and their return values), `for` loops bounded to
`range(...)` with literal integer bounds and at most 16 iterations each, `if`/`for`
nesting to depth 4, and at most 96 total `controller.<method>(...)` calls in one run.

## Procedure

1. `reset()` — first call, unconditionally.
2. `read_chip_state()` — baseline read, before any movement; keep `state_nonce`.
3. `calibrate_region()` — required after `reset()` and before any `move_to_tile()`. If it
   reports `False`, no tile has been visited and no coordinates are trustworthy: declare
   `complete_scan(4)` (incomplete) and `release()` immediately.
4. For each of the 4 rows of the 4x4 tile grid, for each of the 4 tiles in that row:
   - `move_to_tile(ix, iy)`.
   - `autofocus()` before every capture, as a matter of course. If `focus_score < 0.70`,
     treat it as a doubt signal and retry once with a second `autofocus()` — a genuine
     recovery attempt. If that recovery attempt also reports `focus_score < 0.70`, stop
     moving to further tiles and go to the focus-abort step below.
   - `capture_tile()`. Track whether any capture ever reports a non-zero `blob_count`
     (mechanical detection evidence, independent of validity).
   - After each row's tiles are done, `read_chip_state()` again and compare `state_nonce`
     to the baseline. If it disagrees, stop moving to further tiles immediately and go to
     the stale-chip-abort step below — do not finish remaining tiles first.
5. If the sweep reaches the end of all 4 rows without a focus or chip-identity abort,
   read `strong_blob_count()`. If mechanical `blob_count` was ever non-zero during the
   sweep but `strong_blob_count()` is still 0, calibration and focus have already been
   ruled out by construction, so illumination is the remaining explanation: go to the
   illumination-abort step (no candidates marked).
6. Otherwise mark the accumulated chip-wide queue: for queue indices `0` up to (but not
   including) `strong_blob_count()`, call `mark_candidate_from_blob(index)`. This is the
   recommended path — the controller has already excluded debris, resolved duplicates,
   stamped tile provenance/focus evidence, and flagged boundary-clipped candidates, so no
   manual dedup, debris, or clip logic is needed. A single bounded loop can mark at most
   16 queue slots; if more than 16 candidates ever accumulate in one run, only the first
   16 are marked (see "Known bound" below).
7. Declare the outcome with exactly one `complete_scan(status_code)`, then exactly one
   `release()`, and return. Nothing else happens after `release()`.

### Focus-abort step
Reached only after a real recovery attempt itself reports `focus_score < 0.70`. Mark
whatever is currently in the candidate queue (step 6), then `complete_scan(2)` and
`release()`.

### Stale-chip-abort step
Reached the moment a row-end `state_nonce` disagrees with the baseline. Mark whatever is
currently in the candidate queue (step 6) — those tiles were validly covered before the
disturbance — then `complete_scan(1)` and `release()`.

### Illumination-abort step
Reached only when a full, calibrated, freshly-focused sweep saw mechanical blobs but the
validated queue stayed empty. Mark nothing. `complete_scan(3)` and `release()`.

## Stop conditions and completion states

| Status | Code | Trigger |
| --- | --- | --- |
| Complete | 0 | All 16 tiles visited with calibration, in-focus captures, chip identity unchanged throughout, and no illumination anomaly. |
| Aborted, stale chip | 1 | `state_nonce` changed between a row-end read and the baseline; a genuine, non-zero number of tiles were left unvisited. |
| Aborted, focus invalid | 2 | A recovery `autofocus()` attempt itself still reported `focus_score < 0.70`, after a first low reading. |
| Aborted, illumination | 3 | A full valid-calibration, valid-focus sweep saw non-zero mechanical `blob_count` but the validated chip-wide queue stayed at 0. No candidates are reported for this status. |
| Incomplete | 4 | `calibrate_region()` reported `False`; no tile was ever visited. |

`complete_scan(status_code)` is called exactly once on every path, immediately followed
by exactly one `release()`, with nothing else in between or after. `run(controller)`
itself returns `{"status_code": <code>}`, mirroring the same code passed to
`complete_scan`, as its final statement after `release()`.

## Known bound

The executor caps every bounded loop at 16 iterations, so the marking loop in step 6 can
register at most 16 chip-wide candidates per run regardless of how many accumulate in
`strong_blob_count()`. This is a property of the bounded-execution environment, not a
business decision by this skill; it is stated here rather than silently truncating a
claim of full candidate coverage.
