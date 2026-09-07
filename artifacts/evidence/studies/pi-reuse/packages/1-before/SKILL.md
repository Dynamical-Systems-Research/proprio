# 2D flake-search controller skill

## Scope and claim boundary

This document describes an unverified simulator procedure derived from `source.md`.
It is a workflow for searching the declared region; it is not a material-identification,
layer-count, thickness, or other scientific interpretation procedure. It does not
qualify a microscope, a chip, or any other hardware. Admission, if sought, depends on
executing the supplied `run(controller)` against the simulator and passing the
independent preregistered checks. It does not depend on model self-judgment. Simulator
verification itself does not qualify hardware or establish a claim about a real sample.

## Interface and bounded implementation

`skill.py` defines exactly one function:

```python
def run(controller):
    ...
```

The implementation uses only the documented controller atoms and the bounded
language. It has no imports, state reads other than values returned by direct
controller calls, dynamic loops, exception handling, or auxiliary functions. The
first controller call is `reset()`. The final two controller calls are exactly one
`complete_scan(status_code)` followed immediately by exactly one `release()`.

The procedure uses the recommended controller-managed candidate queue. This means the
controller, rather than the skill, applies debris exclusion, chip-frame position
calculation, boundary clipping, focus evidence, tile provenance, and duplicate
merging when a queued slot is marked.

## Operating procedure

1. Reset the session.
2. Read and retain the initial chip state. The retained `chip_id`, `state_nonce`, and
   `corner_found` values are the reference for identity checks.
3. Calibrate the declared region before making any move. If calibration fails, stop
   without moving and use status 4 (`incomplete`).
4. Sweep the 4 by 4 tile grid with indices `ix = 0..3` and `iy = 0..3`. Each tile is
   visited at most once in row-major order. A failed arrival stops further motion and
   uses status 4.
5. Before every capture, run autofocus. If its score is below 0.70, run autofocus
   once more as a recovery attempt. A second score below 0.70 stops the sweep with
   status 2 (`aborted_focus_invalid`), without capturing that tile. A recovered score
   at or above 0.70 permits the capture.
6. Capture each successfully arrived, in-focus tile. The capture is valid for the
   sweep because calibration preceded all moves and a fresh autofocus score meeting
   the floor preceded it. Count the mechanical `blob_count` for the illumination
   diagnostic, including zero counts.
7. After each of the first three completed rows, read chip state again and compare all
   three stored fields with the initial state. On any disagreement, stop before
   moving to another tile and use status 1 (`aborted_stale_chip`). The already
   accumulated queue is retained as partial simulator output. The final row is not
   followed by a new motion; the required mid-scan checks have already occurred.
8. Query `strong_blob_count()` after the sweep stops or completes. If all 16 tiles
   were captured, every capture had a valid focus recovery path, every mechanical
   count was nonzero, and the queue count is zero, infer the documented illumination
   failure condition. Use status 3 (`aborted_illumination`) and mark no candidates.
   Otherwise, mark the accumulated controller queue slots in stable discovery order.
9. Declare the selected status exactly once and release exactly once.

A normal status 0 (`complete`) is used only when all 16 tiles were visited and
captured under the valid calibration and focus conditions and the illumination
inference did not trigger. Status 1 is used only for an identity disagreement during
the sweep. Status 2 is used only after the explicit failed autofocus recovery. Status
3 is used only for the prescribed full-sweep illumination inference. Status 4 is used
for calibration failure or another movement/incomplete condition.

## Candidate handling

The implementation marks queue indices from 0 through 38 when those indices exist.
Three bounded loops are guarded by the observed count, so an out-of-range index is
never submitted. The mark limit is reduced by one for each autofocus recovery call so
the procedure remains within the 96-call bound even if every tile needs recovery.
`mark_candidate_from_blob()` is safe for an already-marked slot, but this procedure
submits each possible slot once. Candidates accumulated before focus or chip-state
aborts are still submitted before completion. An illumination abort submits none,
leaving the manifest empty as required.

The controller-managed queue is relied on for the following source-defined rules:

- detections must meet the documented detectability floor (`contrast >= 0.30` and
  equivalent radius `>= 20.0 um`);
- debris is excluded using `contrast >= 0.30` together with
  `circularity < 0.35` or `radius_um < 12.0`;
- positions are converted into the chip frame and checked against the declared
  region, with boundary-crossing candidates marked as clipped;
- duplicate detections within the documented 30 um merge radius are merged; and
- tile index and focus evidence are stamped by the controller.

The skill does not use the manual `get_blob()` or `mark_candidate()` path and therefore
does not independently reconstruct coordinates or apply manual deduplication.

## Geometry and interpretation limits

The search is for the declared 2000 um by 2000 um region whose origin is
(500 um, 500 um) on a 3000 um by 3000 um chip, using the documented 4 by 4 grid,
500 um tiles, and 50 um overlap. The controller's recommended queue is responsible
for the candidate fields. A reported candidate is only a workflow-level candidate;
this procedure does not assert that it is a particular material, layer number, or
thickness, and it does not turn a simulator result into a real measurement.

This procedure has not been executed here and has no execution feedback. Its behavior,
coverage, candidate accuracy, and admission status therefore remain unverified.
