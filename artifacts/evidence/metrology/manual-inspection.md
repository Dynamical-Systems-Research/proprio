# Raw validity-record inspection

Inspection date: 2026-07-09  
Inspector: Codex (structured agent inspection)  
Battery: `proprio.verifier_metrology.v0.1`, preregistration SHA-256
`80ffcee38cf7219b50a2e6a5b4d114b074578127a08f18711b492a5a8e52f113`

## Method

For the checked-in representative of every class, the inspector:

1. opened the 256 × 256 rendered raw frame at original resolution;
2. read the corresponding `.record.json`, including injected ground truth, every check status,
   metric, and threshold;
3. loaded the `.npy` frame with `allow_pickle=False` and inspected shape, extrema, mean,
   nonzero count, and fraction at the maximum value;
4. compared expected validity to the overall verifier status and failed checks.

## Findings

| class | visual/raw observation | record finding | confirmed |
| --- | --- | --- | --- |
| valid | two complete concentric rings; 16–18,266 counts; no clipped plateau | all nine checks `succeeded` | yes |
| geometry miscalibration | ring center visibly displaced relative to the declared image center | geometry, zero-shift, indexing, and cake checks failed | yes |
| zero shift | complete rings with a regular radial shift; no missing sector or clipping | `zero-shift` failed at injected 0.47847° | yes |
| sample displacement | complete rings with systematic geometry-dependent displacement | sample-displacement, zero-shift, and indexing checks failed | yes |
| saturation | clipped bright rings; 2.4338% of pixels equal detector maximum 65,535 | `detector-saturation` failed | yes |
| dead time | complete rings with compressed intensity relative to a comparable valid frame | `detector-dead-time` failed at injected fraction 0.163323 | yes |
| insufficient counts | sparse photon field; maximum 34, mean 0.4659, only 6,020 nonzero pixels | counting-statistics and chi-squared lower-tail checks failed | yes |
| cake integration failure | a large common azimuthal sector is absent from both rings | `cake-ring-fidelity` failed at injected missing sector 109.543° | yes |
| unindexed peak | an additional complete ring lies between the two expected inner/outer rings | `calibrant-indexing` failed at injected peak 34.0497° | yes |
| chi-squared lower tail | frame is visually plausible, as expected for an uncertainty-model fault | `chi2-lower-tail` failed using reported variance scale 1,636,888.038 | yes |

The visual inspection and the raw records agree with the labeled ground truth for all ten
representatives. The two intentionally non-visual classes are not inferred from appearance:
dead time is grounded in injected detector telemetry, and the chi-squared lower-tail case is
grounded in the injected uncertainty scale. Neither is relabeled as visually proven.

## Known limitation found in aggregate evidence

This representative sample does not erase the aggregate sample-displacement attribution
weakness: the dedicated target check missed 19/300 injected cases. The overall verifier caught
all 300 through adjacent shift/index checks. See `report.md` and `summary.json`.

## Sign-off

- Structured agent inspection: **CONFIRMED**, 2026-07-09.
- Jarrod Barnes, domain-competent human countersignature: **CONFIRMED**, 2026-07-09.
- Independent diffraction-expert real-hardware qualification: **NOT PART OF v0.1; REQUIRED
  BEFORE REAL-HARDWARE DEPLOYMENT**.
