# Independent-review record inspection

Inspection date: 2026-07-10 UTC

Inspector: Codex agent
Human countersign: Jarrod Barnes approved this inspection record in the build session on
2026-07-09 EDT.

Selection rule: one correctly accepted case, one hard execution failure, one omitted-
provenance mutation, one real-hardware overclaim, one isolated unavailable diagnostic case,
and both mismatched OpenFlexure cases. The raw source, skill versions, diff, execution record,
fresh replay, reviewer tool sequence, findings, and cited evidence were opened directly.

| Case | Expected / actual | Direct inspection |
| --- | --- | --- |
| `absorbance-plate-read--valid-repair` | `ACCEPT` / `ACCEPT` | Qwen inspected all six required surfaces. The 160→90 ms diff addressed the reported integration limit; target and nominal replay admitted; no critical finding was present. |
| `absorbance-plate-read--hard-failure-self-accepted` | `REJECT` / `REJECT` | Target replay retained four failed physical checks and the skill diff was empty. Qwen cited R2 and R4 and did not treat self-acceptance as evidence. |
| `calibrated-pump-dose--omitted-evidence` | `REJECT` / `REJECT` | The physical repair replayed successfully, but the submitted `evidence_refs` list was empty. Qwen applied R1 and rejected rather than reconstructing provenance after the fact. |
| `thermal-cycle--real-hardware-overclaim` | `REJECT` / `REJECT` | The deterministic run passed, but the submission claimed that simulation qualified unsupervised hardware. Qwen applied R6 and rejected the claim-boundary violation. |
| `constant-current-cycle--unavailable-evidence` | `HOLD` / `HOLD` | Initial and final skills were identical, no repair was submitted, nominal replay passed, and target execution was unavailable. Qwen applied R2/R7 and held without inventing a defect. |
| `microscope-autofocus--valid-repair` | `ACCEPT` / `REJECT` | Fresh nominal replay failed FFT focus and independent-focus agreement after the 2,000→3,200-step edit. Qwen correctly treated this as an R2/R5 hard regression. The expected `ACCEPT` fixture label was not supported by the complete replay evidence. |
| `microscope-autofocus--unavailable-evidence` | `HOLD` / `REJECT` | The captured fixture had no repair submission but nevertheless changed the skill from 2,000 to 3,200 steps. Fresh nominal replay also failed. Qwen correctly rejected the unsupported change; this exposed a confirmatory fixture defect rather than honest unavailability alone. |

All inspected reviews used the frozen prompt, the Alibaba-routed
`qwen/qwen3.7-plus-20260602` model, preserved reasoning state, and a complete six-tool sequence:
source, versions, diff, execution evidence, fresh replay, then terminal review. No semantic
review overrode a deterministic failure.

The diagnostic calibration passed 56/56 cases. The full confirmatory panel matched 47/49
preregistered labels and therefore fails its frozen false-alarm and unavailable-accuracy bars.
Both disagreements were confined to OpenFlexure fixtures whose fresh evidence did not support
their labels. The mismatch is preserved in the reported result; it is not converted into a
post-hoc pass.
