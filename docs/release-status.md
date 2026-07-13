# Proprio v0.1 release status

Status date: 2026-07-10

## Release engineering: PASS

- Locked install and hardware-free test suite: 196 tests pass.
- Ruff format and lint: pass.
- Procedural fault battery: five failure classes detected; honest degraded/unavailable states
  preserved.
- XRD validity metrology: 300 valid controls and 300 cases for each of nine invalid classes;
  zero false-valids and zero false rejections at the release decision level.
- Declared-support battery and composed operate → observe → judge trajectory: pass.
- Keithley admission proof: one correct DSV4-authored skill admitted; one plausible DSV4-self-
  accepted skill rejected.
- Original cross-family verifier metrology: 9,000 labeled simulations, zero false admissions
  and zero false rejections.
- Original confirmatory replay: 12/12 episodes byte-identical and reset-idempotent, including
  600 locked conditions.
- Public skill catalog: six confirmatory packages plus the Keithley development package remain
  hash-bound and require hardware qualification. No OpenFlexure candidate or evolution
  proposal entered the catalog.
- Evidence manifest: 158 release artifacts, no hash errors. Ignored calibration-array caches
  are excluded explicitly; the corresponding PNGs and all locked arrays remain bound.
- Public naming regression: internal numbered sequencing vocabulary is absent from public
  paths and content.

CI treats a failed research claim as evidence that must remain failed, not as a broken build.
Tests assert the exact external-family rejection, independent-review mismatch, and rejected
evolution proposal so they cannot silently become passes.

## Post-v0.1 OpenFlexure full-loop evidence — 2026-07-13

A separately versioned GPT-5.6 Luna release lineage completed the source-to-skill, rejection,
repair, admission, drift, rejected-evolution, correction, replay, and staging loop against the
pinned native OpenFlexure simulator. The final proposal passed changed `1/1`, historical `3/3`,
and locked `5/5`; the stage record is `STAGED`, with the admitted parent retained byte-immutably.
See the [committed release cassette](../cassettes/openflexure-full-loop/session-001/manifest.json)
and [continuous video](../public/proprio-openflexure-flagship.mp4).

This is one release lineage under a later persistent-context protocol. It does not replace or
recalculate the frozen DSV4 population gates below. Verified in simulation. Hardware validation
remains separate.

## Expanded research gates

| Gate | Result | Status |
| --- | --- | --- |
| Replication capture and route | 70/70 complete; DSV4 revision and GMICloud route frozen | PASS |
| Executable initial draft | 68/70 overall; every instrument exceeded the 75% floor | PASS |
| Systematic original-panel qualification | 60/60 across six instruments in three reduced-order families | PASS |
| External-family qualification | OpenFlexure microscope 4/10 versus the frozen 8/10 minimum | **FAIL** |
| Unsafe promotion prevention | All six unqualified microscope candidates rejected | PASS |
| OpenFlexure verifier metrology | 2,700 cases; zero false-valids; 1/300 valid false rejection | PASS |
| Alternate verifier cross-check | FFT and Laplacian valid-case concordance 299/300 | PASS |
| Independent reviewer calibration | Qwen 3.7 Plus 56/56 diagnostic cases | PASS |
| Independent reviewer confirmatory panel | 47/49 label matches; two unsupported OpenFlexure labels exposed by fresh replay | **FAIL** |
| Reviewer hard-gate dominance | 100% critical recall; zero hard-gate overrides | PASS |
| Reviewer correlation | Qwen and DSV4 agreed on 24/24 original shared cases; Cohen's κ=1.0 | REPORTED |
| Reduced-order simulated evolution | 8/8 staged with immutable parents and rollback lineage | PASS |
| External OpenFlexure evolution | `MAX_TURNS`; target failed; history incomplete; locked 6/10; Qwen reject | **FAIL** |

The failed gates narrow the release claim. They do not invalidate the admission method: every
failure remained outside the public library, and every raw record is retained.

## Release approvals

- COMPLETE: Jarrod Barnes countersigned the XRD
  [manual inspection](../artifacts/evidence/metrology/manual-inspection.md).
- COMPLETE: Jarrod Barnes countersigned the original 30-record
  [confirmatory inspection](../artifacts/evidence/confirmatory-metrology/manual-inspection.md).
- COMPLETE: Jarrod Barnes countersigned the
  [OpenFlexure frame inspection](../artifacts/evidence/microscopy/locked/manual-inspection.md),
  [replication inspection](../cassettes/replication-dsv4/manual-inspection.md), and
  [independent-review inspection](../cassettes/independent-review/manual-inspection.md).
- COMPLETE: Jarrod Barnes confirmed `Dynamical-Systems-Research` as the GitHub organization.

## Claim boundary

The strongest supported claim is simulation-only: DSV4 repeatedly acquired and repaired
skills across the original three held-out method families, and Proprio prevented invalid
candidates from promoting themselves. The external OpenFlexure test demonstrates that
executable generation does not imply physically robust qualification: 10/10 drafts ran but
only 4/10 qualified. It therefore falsifies the stronger four-family systematic-
generalization claim under the frozen threshold.

The method uses no XRD-RL or VOE-Bench data, trained judgment checkpoint, or external policy-
training distribution, and makes no claim about model pretraining. Real-hardware qualification
remains a separate required gate.

## Outside v0.1

- Real-hardware operation, facility interlock validation, and independent instrument-expert
  sign-off.
- MatteriX GPU/GB10 ARM64 runtime qualification; the adapter remains honestly `unavailable`.
- Binding support detection to a trained judgment policy's actual distribution.
- A compiled PDF of the technical note.
