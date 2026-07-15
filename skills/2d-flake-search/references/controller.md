# SOURCE: 2D flake-search controller contract

## Purpose and claim boundary

This is a simulator-only development contract for an automated optical search over a
declared 2000 x 2000 um region of a chip, looking for exfoliated 2D-material flakes among
background debris. It cannot qualify a real microscope or a real chip. The claim a
qualified skill can make is workflow-level only: it covered the declared region, it
reported flake candidates at chip-relative positions within a stated accuracy, it kept
its own chip-identity bookkeeping current, and it stopped and reported honestly when
conditions made a reliable search impossible. Nothing here is a material-identity, a
layer-count, or a thickness claim, and no field returned by the controller encodes one.
Hardware validation is a separate, later qualification gate.

## Procedure and controller

Define exactly:

```python
def run(controller):
    ...
```

`run` is the only function you may define, and `controller` is its only argument. The
executor that runs your code accepts assignments, dictionary/list/tuple literals and
subscripts, arithmetic (`+ - * /`, unary `- + not`), comparisons, `and`/`or`, `if`,
bounded `for controller.reset()` loops over `range(...)` with literal integer bounds,
`break`/`continue`, and calls to `controller.<method>(...)`. It does not permit imports,
comprehensions, lambdas, `while`, `try`, classes, or reading controller state except as
the direct target of a call (`controller.reset()` is fine; reading `controller.trace` is
not). Source is limited to 16,384 bytes, loops to 16 iterations each, `if`/`for` nesting
to depth 4, and the whole run to 96 controller calls total. Every atom below costs
exactly one controller call per invocation; there is no batched or free call.

## The twelve controller atoms

Ordering constraint that applies before any of the individual notes below:
`reset()` must be the first call, `calibrate_region()` must be called after `reset()` and
before any `move_to_tile()`, and `complete_scan()` must be followed by exactly one
`release()` before the run ends.

| Atom | Signature | Role | Cost | Notes |
| --- | --- | --- | --- | --- |
| `reset` | `reset() -> None` | required | 1 | Deterministic re-init to the session. Must be the first call. |
| `read_chip_state` | `read_chip_state() -> {chip_id: str, state_nonce: int, corner_found: bool}` | required | 1 | `state_nonce` changes if the chip is swapped or disturbed. Read it before scanning and again more than once during the scan (see "Chip identity" below), not only once at the very end. |
| `calibrate_region` | `calibrate_region() -> calibration_ok: bool` | required | 1 | Establishes the chip-relative coordinate frame from the detected corner. Must follow `reset()` and precede any `move_to_tile()`; moving before calibration is recorded and reported coordinates are not trustworthy afterward. |
| `move_to_tile` | `move_to_tile(ix: int, iy: int) -> arrival: bool` | required | 1 | `ix`, `iy` are tile indices in `[0, 3]`, covering the 4x4 tile grid. An out-of-range index returns `False` and is recorded as a fault. |
| `autofocus` | `autofocus() -> focus_score: float` | required | 1 | Documented validity floor is `focus_score >= 0.70`. Focus can decay as the stage moves; re-invoke `autofocus()` before capturing whenever there is any reason to doubt current focus, including simply as a matter of course before every capture. |
| `capture_tile` | `capture_tile() -> blob_count: int` | required | 1 | Captures at the current position. `blob_count` is a mechanical count of every detected object at this tile, reported regardless of validity. The capture only contributes to declared-region coverage and to the chip-wide candidate queue if, in this scan, it was preceded by `calibrate_region()` and its concurrent `autofocus()` reported `focus_score >= 0.70` and illumination was in the documented range. |
| `get_blob` | `get_blob(index: int, field: str) -> float` | manual | 1 | `field` in `{"x_um", "y_um", "radius_um", "contrast", "circularity"}`, in the tile frame (relative to the current tile's own nominal origin), scoped to the blobs recorded by the most recent `capture_tile()` call only; `index` resets to 0 on every new capture. A manual, diagnostic accessor, not required by the recommended path below. |
| `mark_candidate` | `mark_candidate(chip_x_um: float, chip_y_um: float, radius_um: float, contrast: float, clipped: bool) -> None` | manual | 1 | Manual candidate registration from skill-supplied floats. The controller still auto-stamps tile provenance and focus evidence, but chip-frame coordinates, debris exclusion, boundary-clip determination, and duplicate control are entirely the skill's own responsibility on this path. |
| `strong_blob_count` | `strong_blob_count() -> count: int` | recommended | 1 | Chip-wide count of candidate-queue slots accumulated so far: debris-excluded and duplicate-resolved by the controller, built only from valid captures (see `capture_tile` above). Monotonically non-decreasing as more captures complete. |
| `mark_candidate_from_blob` | `mark_candidate_from_blob(blob_index: int) -> marked: bool` | recommended | 1 | Marks chip-wide queue slot `blob_index` (0-based, stable discovery order) into the manifest using controller-computed chip-frame coordinates and auto-stamped tile provenance and focus evidence. Returns `False` (a no-op, not an error) if `blob_index` is out of range for the current `strong_blob_count()` or was already marked, so calling it twice on the same index is always safe. |
| `complete_scan` | `complete_scan(status_code: int) -> None` | required | 1 | `status_code` in `{0, 1, 2, 3, 4}` (see "Status codes" below). Required exactly once; a run with no `complete_scan` call is incomplete. |
| `release` | `release() -> None` | required | 1 | Returns the stage to park and releases held resources. Required exactly once, strictly after `complete_scan()`, before the run ends. |

### Status codes

| Code | Meaning |
| --- | --- |
| 0 | complete |
| 1 | aborted, stale chip (identity changed mid-scan) |
| 2 | aborted, focus invalid (recovery attempt failed) |
| 3 | aborted, illumination out of range |
| 4 | incomplete (any other honest early stop) |

## Required workflow obligations

**Chip identity.** Read chip state before moving anywhere. A single check before the
scan and a single check after it is not, by itself, enough to justify an abort: any
non-zero status code needs a genuine, consistent number of tiles that were actually left
unvisited or invalid, not merely a status claim tacked onto an otherwise complete scan.
Read chip state again at least once during the scan -- for example once per row, after
that row's tiles are captured -- and compare it against the very first read. If it
disagrees, stop moving to further tiles immediately and abort status 1
(`aborted_stale_chip`); do not finish the remaining tiles first and only report the
change afterward, since by then every tile is already validly covered and the abort no
longer matches what was actually visited.

**Focus.** Abort status 2 (`aborted_focus_invalid`) only after a failed autofocus
recovery attempt -- that is, an `autofocus()` call that itself reports a `focus_score`
below the documented floor. A capture that happens to fall below the floor is not, by
itself, grounds for this abort; call `autofocus()` again and try to recover before giving
up. Treat status 2 as a last resort you should rarely if ever need, not a substitute for
finishing the scan or a way to explain away an incomplete one.

**Illumination.** Abort status 3 (`aborted_illumination`) when illumination is out of the
documented range, and report no candidates in that case. There is no direct
illumination-reading atom, so illumination has to be inferred from what the recommended
path already gives you: `capture_tile()` keeps returning a mechanical `blob_count`
regardless of validity, while the chip-wide queue (`strong_blob_count()`) only grows from
valid captures. If a full, correctly-calibrated, freshly-focused sweep of the declared
region keeps seeing non-zero `blob_count` from individual captures, yet
`strong_blob_count()` still reports zero once the sweep is done, calibration and focus
have both been ruled out by construction and illumination is the remaining explanation:
abort status 3 with no candidates marked.

**Coverage.** Report status 0 (complete) only when all 16 tiles have been visited with a
valid capture (calibrated, in focus, in-range illumination). Any other status code needs
to leave a real, non-zero number of tiles unvisited or invalid, consistent with why the
scan stopped.

**Deduplication.** The recommended chip-wide queue (`strong_blob_count()` /
`mark_candidate_from_blob()`) already merges repeat observations of the same physical
object within the merge radius below; this happens mechanically before a slot is
queued. Recording candidates through the manual path (`get_blob()` / `mark_candidate()`)
does not get this for free -- a skill using the manual path is responsible for not
reporting the same physical object twice.

**Boundary crossing.** Any candidate whose disk crosses the declared-region boundary must
be reported with `clipped=true` if reported at all. The recommended path stamps this
correctly from controller-side detection; the manual path must set it explicitly. A
clipped candidate is reported honestly, not treated as an ordinary find.

**Debris.** A blob is debris, not a flake, if `contrast >= 0.30 AND (circularity < 0.35
OR radius_um < 12.0)`. The recommended chip-wide queue applies this rule mechanically
before a slot is queued, so a skill using only the recommended path never needs to
evaluate it directly. A skill using the manual `get_blob()` path to build its own
candidates is responsible for applying this rule itself.

**Completion.** Call `complete_scan(status_code)` exactly once to declare the outcome,
and call `release()` exactly once, strictly after `complete_scan()`, before the run
returns.

## Geometry and detection constants

| Constant | Value |
| --- | --- |
| Chip size | 3000 x 3000 um |
| Coordinate origin | bottom-left chip corner |
| Declared region | origin (500, 500) um, size 2000 x 2000 um |
| Tile grid | 4 x 4 tiles |
| Tile size | 500 x 500 um |
| Tile overlap | 50 um on shared edges |
| Detectability floor | contrast >= 0.30 and equivalent radius >= 20.0 um, evaluated on an in-focus, in-range-illumination capture |
| Debris rule | contrast >= 0.30 AND (circularity < 0.35 OR radius_um < 12.0) |
| Focus floor | focus_score >= 0.70 |
| Dedup merge radius | 30.0 um -- two reported positions within this distance are the same physical object |
| Position tolerance | 25.0 um -- how close a reported chip-relative position must be to the object it claims to identify, evaluated independently per axis |

## Manifest fields

Every reported candidate carries `chip_x_um`, `chip_y_um`, `radius_um`, `contrast`,
`clipped`, `tile_index`, and `focus_score`.

- **Recommended path** (`mark_candidate_from_blob`): `chip_x_um`, `chip_y_um`,
  `radius_um`, `contrast`, and `clipped` are all controller-computed from the queued
  detection; the skill only supplies the queue index. `tile_index` and `focus_score` are
  auto-stamped by the controller from its own current state.
- **Manual path** (`mark_candidate`): the skill supplies `chip_x_um`, `chip_y_um`,
  `radius_um`, `contrast`, and `clipped` directly as floats/bool. `tile_index` and
  `focus_score` are still auto-stamped by the controller from its own current state, not
  from anything the skill claims.

## Verification

An independent simulator and verifier, neither of which is part of this source bundle,
judge the executed session: procedural compliance, coverage, positional accuracy,
deduplication, and completeness against preregistered constants (some of which are
listed above because a correct skill needs them; others are held back). The skill cannot
set or override those checks, and model self-judgment is not the admission authority.

The drafted `SKILL.md` must state that admission depends on execution against this
simulator and the independent preregistered checks, not on model self-judgment, and that
simulation verification does not itself qualify hardware or make a material-identity,
layer-count, or other scientific interpretation of a real sample.
