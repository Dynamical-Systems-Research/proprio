# External-simulator evidence inspection

Inspection date: 2026-07-11

Inspector: Codex agent. Jarrod previously approved the structured raw-record inspection process;
no real-hardware or independent instrument-expert sign-off is claimed.

## North pipette calibration

- The nominal water record executes reset, sample inspection, constraint query, three
  measurements, and cleanup in order.
- The observed mean is 0.0492102 mL for a 0.0500000 mL target; relative error is 1.58% and
  replicate CV is 1.48%. The record correctly admits it.
- The procedurally complete invalid record uses 0.150 mL overaspiration. Its mean is 0.162104 mL
  for the same target and the independent `volume-accuracy` check rejects it.
- Upstream wall-clock and microbenchmark fields are removed from canonical telemetry. Three fresh
  repetitions are byte-identical after reset and dual-RNG seeding; measured volume and simulated
  elapsed time remain present.
- The registered 0.80 delivery-scale change remains procedurally complete but moves the same
  nominal command outside the 4% volume-accuracy contract. The locked 0.78 condition and stronger
  0.40 evolution condition fail the same physical check, not a procedural check.

## HELAO Gamry cyclic voltammetry

- The valid record connects, queries the 0.20 V/s limit, reads and applies zero compensation,
  executes a 100-point -0.5/+0.5 V cycle, and disconnects.
- The current spans -42.60 to +19.86 mA/cm² and the observed potential extrema are approximately
  -0.49495 and +0.49495 V, consistent with the fixed 0.02 V sampling contract.
- The invalid record remains procedurally complete but requests 0.40 V/s against a 0.10 V/s
  reported limit. `scan-rate-support` rejects it.
- Metrology initially exposed a candidate-controlled verifier bug: a +0.3 V endpoint was accepted
  because expected endpoints were read from candidate arguments. The verifier now binds to the
  public -0.5/+0.5 V contract; the complete rerun observed zero false admissions.
- The registered 0.90 potential-scale change produces a regular endpoint-fidelity failure while
  retaining a finite bidirectional CV frame. The locked 0.88 condition and the evolution change
  from 0.90 on the initial probe to a stable 0.70 afterward fail `potential-sweep-fidelity`
  without changing the candidate-independent target endpoints.

## CLSLab:Light spectrometer

- The valid record configures atime 100, astep 999, and gain 64, then acquires all eight channels
  for RGB (40, 60, 20). Counts span approximately 138 to 22,901 under a 60,000-count limit.
- `clear()` produces eight zero-valued dark channels and records cleanup.
- The procedurally complete invalid record uses maximum integration and gain under the reduced
  30,000-count range. Its maximum exceeds 131 million counts and `counting-range` rejects it.
- The registered 0.005 sensitivity scale and locked 0.0045 condition reject the nominal skill only
  on the one-count lower bound. The evolution condition reports a 60,000-count limit initially and
  narrows it to 10,000 after the first acquisition; it preserves the eight-channel frame, dark
  response, and cleanup evidence while failing `counting-range`.

## Metrology composition

- Each family contains 300 nominal valid cases and 300 cases for every registered invalid class.
- North observed 3/300 valid false rejections (1.0%); HELAO and CLSLab observed 0/300.
- Every invalid class across all three families had zero false admissions.
- Every nominal, repair, drift, invalid, registered-change, locked-change, evolution-change, and
  unavailable preflight control repeated three times with byte-identical canonical gate records.

The evidence closes simulator eligibility and verifier correctness before the binding panel. The
three earlier model smoke sessions are method-development evidence and are not included in the
confirmatory counts. Documentation-to-skill generalization requires the frozen live study.
