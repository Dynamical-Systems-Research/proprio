# Confirmatory raw-record inspection

Inspection date: 2026-07-09

Inspector: Codex agent

Human countersign: pending before public release

## Sample

Thirty raw records were inspected: one seeded record for every combination of six
confirmatory instruments and five ground-truth classes (`valid`, `wrong_order`,
`unsafe_setting`, `wrong_target`, and `cleanup_omitted`). This sample was selected by a fixed
rule (`case index 0000`), not by outcome. Each raw file contains the generated skill, analytic
label, execution trace, controller telemetry, individual physical checks, and final verdict.

## Hand-reading result

| Instrument | Valid trace | Wrong order | Unsafe setting | Wrong target | Cleanup omitted |
| --- | --- | --- | --- | --- | --- |
| `absorbance-plate-read` | admitted after blank/sample pair and shutdown | rejected on pair/order and lifecycle | rejected on integration support, saturation, and reference signal | rejected on wavelength | rejected on plate lifecycle |
| `fluorescence-plate-read` | admitted after blank/sample pair and shutdown | rejected on pair/order and lifecycle | rejected on gain support, saturation, and reference signal | rejected on wavelength/Stokes order | rejected on plate lifecycle |
| `calibrated-pump-dose` | admitted after calibration, prime, dose, halt | rejected on missing certified calibration and controller violation | rejected on speed support | rejected on delivered target volume | rejected because pump remained active |
| `dual-pump-blend` | admitted after both channel calibrations, doses, halt | rejected on missing calibrations and controller violation | rejected on speed support | rejected on total volume and blend ratio | rejected because channels remained active |
| `isothermal-hold` | admitted after transition, hold, deactivate | rejected on missing transition and unsettled hold | rejected on transition support and controller violation | rejected on setpoint sequence | rejected because controller remained active |
| `thermal-cycle` | admitted after both transitions, holds, deactivate | rejected on missing transitions and unsettled holds | rejected on transition support and controller violation | rejected on setpoint sequence | rejected because controller remained active |

All 30 inspected verdicts match their analytic labels. Valid records include the expected
action sequence, measurements, cleanup, and no critical failed checks. Every invalid record
contains a visible causal defect in the trace or telemetry and at least one corresponding
critical failed check. No mock, exception, truncated trace, or unavailable path is labeled as
a pass.

Representative files:

- `raw-samples/absorbance-plate-read--valid--0000.json`
- `raw-samples/absorbance-plate-read--unsafe_setting--0000.json`
- `raw-samples/calibrated-pump-dose--wrong_order--0000.json`
- `raw-samples/dual-pump-blend--wrong_target--0000.json`
- `raw-samples/isothermal-hold--cleanup_omitted--0000.json`
- `raw-samples/thermal-cycle--unsafe_setting--0000.json`

The inspection supports record fidelity only. The preregistered metrology summary remains the
authority for false-admission and false-rejection counts across all 9,000 cases.
