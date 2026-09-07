# 2D flake-search controller skill

## Scope and claim boundary

This skill is an unverified implementation of the simulator-only 2D flake-search
procedure in `source.md`. It searches the declared 2000 um by 2000 um region using
its 4 by 4, 500 um tile grid. A successful status is only a workflow report: the
region was covered with valid captures and the controller's candidate queue was
reported at chip-relative positions. A candidate is not asserted to be a particular
material, layer count, thickness, or other scientific interpretation. This document
must not be read as qualification of a real microscope, stage, chip, or hardware.

Admission depends on execution against the supplied simulator and the independent,
preregistered checks described by the contract, not on model self-judgment or a code
inspection. Even successful simulation verification does not qualify hardware and
does not establish material identity, layer count, thickness, or any other physical
sample interpretation.

## Operating procedure

The implementation in `skill.py` defines only `run(controller)`. It uses the
controller's recommended chip-wide detection path rather than manually extracting
and transforming blob coordinates.

1. It calls `reset()` first, then reads the initial `chip_id` and `state_nonce`.
   It calls `calibrate_region()` before any tile movement. A failed calibration is
   reported as status 4 (incomplete), with no tile movement.
2. It traverses tile indices `(ix, iy)` for `ix = 0..3` and `iy = 0..3`. Each tile
   must arrive successfully. An arrival failure stops the traversal and is reported
   as status 4.
3. Before every capture it calls `autofocus()`. A score below 0.70 causes one
   autofocus recovery attempt. If that second score is also below 0.70, the current
   tile is not captured, traversal stops, and status 2 is used. A successful score
   is followed immediately by `capture_tile()`.
4. It records the mechanical `blob_count` from every valid capture for the
   illumination decision. It does not treat that count as a flake count. After each
   completed row it reads chip state and compares both the chip ID and nonce with
   the initial values. If either changes, it stops before moving to another tile
   and uses status 1. If an early stop occurs before two row checks have happened,
   it performs enough additional non-moving checks to make the identity check
   non-singleton.
5. After the traversal it calls `strong_blob_count()`. The controller's recommended
   queue supplies debris exclusion, duplicate merging at its configured merge
   radius, chip-frame coordinates, focus evidence, and boundary clipping. The
   skill registers queued slots with `mark_candidate_from_blob()` before declaring
   the result. Registration uses bounded queue-index passes permitted by the
   controller language and supplies no manual coordinates.
6. Status 0 is used only after all 16 tiles arrived, were freshly focused, and
   captured without a stop. If the complete sweep saw at least one mechanical blob
   but the final strong queue is still zero, the recommended-path inference treats
   illumination as the remaining failure mode and uses status 3 without marking
   any candidate. A status 1 or 2 retains candidates accumulated before the stop;
   other early stops use status 4. The procedure never reports status 3 with a
   nonempty manifest.
7. It calls `complete_scan(status)` exactly once and then calls `release()` exactly
   once. No controller state is read directly; all observations come from atom
   return values.

## Controller and geometry assumptions

The procedure relies on the contract's declared frame and constants: the chip is
3000 um by 3000 um with origin at its bottom-left corner; the search region starts
at `(500, 500)` um and is 2000 um square; tile overlap is 50 um; focus validity is
at least 0.70; detectability uses contrast at least 0.30 and equivalent radius at
least 20 um; and candidate position tolerance is 25 um per axis. The recommended
queue excludes a debris blob when `contrast >= 0.30` and either `circularity <
0.35` or `radius_um < 12.0`, merges duplicate positions within 30 um, and stamps
boundary-crossing candidates as clipped. These are controller operations; the
skill does not manually claim material identity or layer information.

## Status meanings

- `0`: complete 16-tile workflow.
- `1`: aborted because chip identity became stale during the workflow.
- `2`: aborted after autofocus recovery also returned a score below 0.70.
- `3`: aborted because illumination is inferred out of range, with an empty manifest.
- `4`: another honest incomplete stop, including failed calibration or tile arrival.

These statuses describe this unverified controller procedure only. They are not
hardware qualification results.
