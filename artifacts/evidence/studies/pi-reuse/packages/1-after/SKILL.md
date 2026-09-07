# 2D flake-search skill

## Scope and claim boundary

`skill.py` contains the required `run(controller)` procedure for the simulator contract in
`source.md`. It searches the declared region for workflow-level flake candidates. It does
not identify a material, measure layer count or thickness, or qualify a microscope, chip,
or other hardware. Simulator checks are not hardware qualification. Admission, if sought,
depends on execution by the simulator and its independent preregistered checks, not on
self-judgment by the model.

## Operating instructions

The procedure is intended to be run as supplied; the only entry point is:

```python
def run(controller):
    ...
```

It performs the following sequence:

1. `reset()`, then read and retain `chip_id`, `state_nonce`, and `corner_found`.
2. Calibrate before any movement. Calibration failure produces status 4 and no move.
3. Visit all 16 tiles, row-major, using indices 0..3 in each axis. A failed arrival
   stops further useful motion and produces status 4.
4. Run autofocus before every capture. If the score is below 0.70, autofocus once more.
   A second score below 0.70 produces status 2 and that tile is not captured. A recovered
   score permits the capture.
5. Read chip state after each of the first three completed rows. A difference in any of
   the three retained fields stops further scanning and produces status 1.
6. Count every returned `capture_tile()` blob count. After the scan (or an early stop),
   query `strong_blob_count()`. If all 16 tiles were captured, at least one mechanical
   count was nonzero, and the strong queue is empty, infer the documented illumination
   failure and produce status 3 without marking candidates. Otherwise mark queued
   candidates, then complete and release.

Status meanings are: 0 complete, 1 stale chip, 2 unrecovered focus failure, 3 inferred
illumination failure, and 4 other incomplete condition. `complete_scan(status)` is called
exactly once and is immediately followed by exactly one `release()`.

## Candidate path and limits

Candidates use the controller-managed queue: `mark_candidate_from_blob()` supplies
controller-computed chip coordinates, radius, contrast, boundary clipping, tile
provenance, focus evidence, debris exclusion, and duplicate merging. No manual blob
coordinates are reconstructed by the skill. Partial valid captures are marked before an
abort, while status 3 deliberately marks none.

The bounded runtime checker counts possible calls conservatively, including a possible
focus recovery on every tile. To stay within the 96-call contract, this implementation
submits queue slots 0 through 22 at most (and only when those slots exist); the tested
scenarios have queues of 5, 8, and 10. A queue larger than 23 is a remaining limitation:
its later slots cannot be submitted within this implementation's static call budget.
The controller's queue still performs its documented detectability filtering, debris rule,
30 um duplicate merge, chip-frame conversion, and boundary clipping for every slot.

The geometry is the source-defined 2000 x 2000 um region at (500, 500) um on a 3000 x
3000 um chip, covered by the 4 x 4 grid of 500 um tiles with 50 um overlap. Reported
candidates remain workflow candidates, not scientific identifications or measurements.

## Development execution record

The supplied draft was tested and repaired with `execute_candidate` five times:

- Attempt 1: rejected before execution because its conservative call bound was 113,
  above 96.
- Attempt 2: rejected because a marking loop used bound 24, above the 16-iteration
  limit.
- Attempt 3: rejected with call bound 98 after splitting that loop.
- Attempt 4: static safety and nominal, focus, and stale cases passed, but the
  illumination case incorrectly returned status 0 because it required every mechanical
  count to be nonzero.
- Attempt 5: changed that diagnostic to require at least one nonzero mechanical count.
  Nominal, focus, stale, and illumination cases all completed without runtime errors;
  all reported simulator checks passed, including coverage, candidate recall, focus
  validity, stale-chip handling, illumination abstention, bounded runtime, and release.

The focus development case returned ordinary status 0 with scores of 0.95; it did not
exercise a below-floor recovery trace. No private evaluation or real hardware test was
performed, and no hardware or scientific claim follows from these development checks.
