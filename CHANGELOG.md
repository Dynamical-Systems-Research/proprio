# Changelog

## Unreleased

- Added the built-in `proprio.flake_search` provider: a reduced-order 2D optical
  flake-search simulator, an independent verifier, and a preregistered rubric
  (procedural compliance, coverage, positional accuracy, deduplication, completeness).
- Published `2d-flake-search`, a blind-drafted, simulator-verified skill admitted on
  visible and locked conditions with zero access to the verifier, thresholds, or prior
  evidence during drafting.

## 0.5.0 - 2026-07-14

- Added the versioned `proprio.instrument_providers` entry-point seam for independently installed
  simulator integrations without core registry edits.
- Routed all 12 skills through the common inspect, execute, visible-evidence, locked-verification,
  and optional evolution path, including the existing verified XRD generator and metrology gate.
- Published the complete flat skill library with compact hash-bound records, instrument sources,
  and the core code required to reproduce and extend the method.
- Moved the pinned native OpenFlexure replay to an explicit release-validation workflow while
  keeping standard CI focused on the provider and admission contracts.

## 0.4.0 - 2026-07-11

- Added a persistent, checkpointed agent context for skill drafting, execution, repair, and drift
  evolution.
- Froze and ran one acquisition-and-verification method across liquid-delivery,
  electrochemical-measurement, and spectral-measurement simulators.
- Verified all three instrument skills on visible and locked conditions with zero invalid
  promotions; staged regression-safe drift evolution for all three.
- Published the complete raw model, tool, simulator, verifier, selection, and provenance records.
- Retained XRD as the reference workflow and the Keithley wrong-range rejection as the compact
  deterministic admission example.
- Removed superseded study code, internal notes, duplicate assets, and obsolete artifacts from the
  public release surface.
