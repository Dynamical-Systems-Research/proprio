# 2D flake-search controller skill

## Scope and claim boundary

`skill.py` implements the simulator-only procedure in `source.md`. It searches the
2,000 um by 2,000 um declared region as a 4 by 4 grid and reports a workflow
outcome and controller-generated candidate records. A candidate is not a material,
layer-count, thickness, or other scientific identification. This procedure does
not qualify a real microscope, stage, chip, or hardware.

Admission is determined by execution against the supplied simulator and the
independent preregistered checks, not by model judgment or code inspection.
Simulation checks likewise do not qualify hardware or establish a physical sample
interpretation.

## Operating instructions

Run the single entry point `run(controller)` in `skill.py`.

1. Reset, read the initial `chip_id` and `state_nonce`, and calibrate before any
   move. A failed calibration completes with status `4` and does not move.
2. Visit `(ix, iy)` in row-major order for `ix, iy = 0..3`. A failed arrival stops
   with status `4`. Autofocus precedes every capture. A score below `0.70` gets
   exactly one recovery autofocus; a second score below `0.70` stops with status
   `2`, without capturing that tile.
3. Count only successfully focused captures as valid coverage. The mechanical
   `blob_count` is used only as the illumination clue; it is not treated as a
   flake count.
4. After every completed row, compare both chip identity fields with the initial
   read. A mismatch stops before the next tile and produces status `1`. If an
   early stop occurs before any row check, one non-moving identity check is made
   before declaring the result.
5. Call `strong_blob_count()` after the scan and register queue slots with
   `mark_candidate_from_blob()`. This recommended path delegates chip-frame
   coordinates, debris exclusion, duplicate merging, focus provenance, and
   boundary clipping to the controller; no manual blob coordinates are supplied.
   Partial valid results are registered for status `1`, `2`, or `4`. Status `3`
   registers none.
6. A complete sweep is status `0` only when all 16 tiles were captured validly,
   identity stayed fresh, and no stop occurred. If all 16 valid captures saw at
   least one mechanical blob but the final strong queue is empty, report status
   `3` (illumination inferred out of range) with an empty manifest. Other early
   stops report status `4` unless they specifically meet the stale or focus rules.
7. The procedure calls `complete_scan(status)` exactly once and then
   `release()` exactly once.

The recommended queue registration is bounded by the 96-call controller budget:
the implementation marks queue indices `0..20` (21 slots). The tested simulator
cases had at most 10 queued slots. A case producing more than 21 strong queue
slots is a remaining limitation and would need a contract/runtime budget that
permits more registration calls; the skill does not silently invent or manually
approximate the omitted records.

## Contract constants relied upon

The controller contract defines a 3,000 um square chip, bottom-left chip origin,
a region beginning at `(500, 500)` um, 500 um tiles with 50 um overlap, focus
validity `>= 0.70`, detectability contrast `>= 0.30` and equivalent radius
`>= 20.0` um, 30 um queue deduplication, and 25 um per-axis position tolerance.
The recommended queue mechanically applies the stated debris rule and stamps
clipped boundary-crossing candidates.

Statuses are: `0` complete, `1` stale chip, `2` unrecovered focus failure, `3`
inferred illumination failure with an empty manifest, and `4` other incomplete
stop.

## Development testing and limitations

- The first execution of the earlier draft failed static validation because its
  nested branches exceeded depth 4.
- The first repair then exceeded the 96-call bound (static worst-case bound 108).
  The final repair flattens the traversal and limits queue registration to 21
  slots while retaining one focus recovery and row identity checks.
- Final executions (attempts 3, 4, and 5) passed every reported simulator check
  for the nominal, focus-labelled, stale-chip, and illumination conditions. In
  each execution those four conditions produced statuses `0`, `0`, `1`, and `3`;
  checks covered coverage, queue deduplication/recall, focus validity, identity
  freshness, clipping/coordinates, abstention, completion, and release.
- In the focus-labelled executions every returned focus score was `0.95`; the
  low-score recovery branch and status `2` were not exercised by the available
  development feedback. Calibration and arrival-failure branches were also not
  separately exercised. These are testing limitations, not claims that those
  cases cannot occur.
