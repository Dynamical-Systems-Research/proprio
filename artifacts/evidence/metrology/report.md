# Proprio v0.1 verifier metrology

This report is generated from the preregistered synthetic calibrant battery.
Thresholds are read from the frozen preregistration and are not fitted on these cases.

Overall verdict: **PASS**

| failure class | cases | false-valid | rate | target check | target-check misses | AUROC |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| geometry_miscalibration | 300 | 0 | 0.000000 | geometry-calibration | 0 | 1.000000 |
| zero_shift | 300 | 0 | 0.000000 | zero-shift | 0 | 1.000000 |
| sample_displacement | 300 | 0 | 0.000000 | sample-displacement | 19 | 0.943000 |
| saturation | 300 | 0 | 0.000000 | detector-saturation | 0 | 1.000000 |
| dead_time | 300 | 0 | 0.000000 | detector-dead-time | 0 | 1.000000 |
| insufficient_counts | 300 | 0 | 0.000000 | counting-statistics | 0 | 1.000000 |
| cake_integration_failure | 300 | 0 | 0.000000 | cake-ring-fidelity | 0 | 1.000000 |
| unindexed_peak | 300 | 0 | 0.000000 | calibrant-indexing | 0 | 1.000000 |
| chi2_lower_tail | 300 | 0 | 0.000000 | chi2-lower-tail | 0 | 1.000000 |

## Valid controls

- Cases: 300
- False rejects: 0
- False-reject rate: 0.000000

## Adversarial controls

- Invalid measurements rejected despite an always-valid claim: 2700
- Always-valid bot exploit rate: 0.000000

## Independence

- Generator: analytic NumPy Bragg-ring forward model.
- Verifier: pyFAI integration plus independent peak, detector-telemetry, azimuthal-Poisson, and support checks.
- Remaining correlated-oracle risk: both engines consume the same declared geometry, wavelength, and certified peak table/lattice provenance.
