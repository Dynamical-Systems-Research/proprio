# Proprio v0.1 release status

Status date: 2026-07-09

## Machine gates: PASS

- Locked clean-copy install: pass.
- Isolated wheel install: pass; the installed wheel ran the 9,000-case confirmatory
  metrology battery and loaded bundled instrument sources outside the checkout.
- Ruff format and lint: pass.
- Test suite: 173 passed.
- Procedural fault battery: pass.
- XRD measurement-validity metrology: pass at 300 cases per class.
- Substrate-support battery: pass.
- Composed operate → observe → judge trajectory: pass with a live DSV4 baseline call.
- Keithley skill admission: correct DSV4 draft simulation-qualified; DSV4-self-accepted stale
  draft rejected.
- Confirmatory skill acquisition: 6/6 initial drafts executable across three families absent
  from method development.
- Causal repair: truthful simulator feedback qualified 6/6 paired drafts; no-feedback control
  qualified 0/6; paired uplift 1.0 with bootstrap 95% interval [1.0, 1.0].
- Confirmatory verifier metrology: 9,000 labeled simulations, zero false admissions and zero
  false rejections.
- Confirmatory replay: 12/12 episodes byte-identical and reset-idempotent, including 600
  locked conditions.
- Stateful reviewer metrology: 24/24 confirmatory mutation cases; critical-defect recall 1.0,
  valid false-alarm rate 0.0, unavailable-evidence `HOLD` accuracy 1.0, and zero hard-gate
  overrides.
- Simulation-valid evolution: drift detected for 8/8 parent skills; 8/8 validated proposals
  staged with immutable parent and rollback lineage; zero unsafe promotions.
- Evolution replay: 8/8 proposal statuses byte-identical.
- Public skill library: six exact DSV4-authored packages bound to hashes and marked
  `simulation_qualified`; every entry requires a separate hardware qualification gate.
- Evidence manifest: 139 artifacts, no hash errors.
- Public naming regression: pass; internal numbered sequencing vocabulary is absent from
  public paths and contents.

## Release approvals

- COMPLETE: Jarrod Barnes countersigned the XRD
  [manual inspection](../artifacts/evidence/metrology/manual-inspection.md) as the
  domain-competent human reviewer on 2026-07-09.
- COMPLETE: Jarrod Barnes confirmed `Dynamical-Systems-Research` as the GitHub organization
  slug on 2026-07-09.
- COMPLETE: Jarrod Barnes countersigned the separate 30-record
  [confirmatory inspection](../artifacts/evidence/confirmatory-metrology/manual-inspection.md)
  on 2026-07-09.

## Claim boundary

The strongest supported claim is simulation-only: across six instruments in three families
held out from method development, DSV4 generated executable skills, used simulator evidence to
repair them, and could not promote candidates that failed independent execution, physical,
provenance, locked-validation, or reviewer gates. A separate eight-instrument study demonstrates
simulation-valid skill evolution under versioned drift. The method uses no XRD-RL data,
VOE-Bench data, trained judgment checkpoint, or external policy-training distribution, and it
makes no claim about model pretraining.

## Explicitly outside the v0.1 simulation claim

- Real-hardware qualification and independent instrument-expert sign-off.
- MatteriX GPU/GB10 ARM64 runtime qualification; the adapter remains honestly `unavailable`.
- Binding support detection to a trained judgment policy's actual training distribution.
- A compiled PDF of the technical note.
