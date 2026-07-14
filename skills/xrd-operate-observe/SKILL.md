---
name: xrd-operate-observe
description: Acquires a single raw two-dimensional area-detector frame from the preregistered LaB6 calibrant via the XRD simulator controller (reset, select calibrant, acquire one frame, release), returning the case_id and calibrant identifiers.
---

# xrd-operate-observe

This skill operates the XRD simulator's narrow controller to acquire exactly one raw
LaB6 calibrant frame: `reset()` -> `select_calibrant("lab6")` -> `acquire_frame()` ->
`release()`. It returns a dictionary containing at least `case_id` and `calibrant`.

## Claim boundaries

- **Admission authority.** Admission of this skill depends solely on execution against
  the raw-frame simulator together with the independent preregistered metrology checks.
  The skill's own output, or any self-judgment by the model that authored or ran it, is
  never the admission authority.
- **Simulation vs. hardware.** A successful simulator run demonstrates correct controller
  sequencing in simulation only. It is not hardware qualification and makes no claim
  about behavior on physical XRD instrumentation.
- **No scientific interpretation.** This skill acquires a raw calibrant frame and nothing
  more. It does not perform, and its execution does not validate, phase assignment,
  peak indexing, lattice refinement, or any other scientific interpretation of an unknown
  sample.
