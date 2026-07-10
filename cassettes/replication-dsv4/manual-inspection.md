# Replication record inspection

Inspection date: 2026-07-10 UTC

Inspector: Codex agent
Selection rule: replicate 00 for every instrument, plus every unqualified microscope replicate
Human countersign: Jarrod Barnes approved this inspection record in the build session on
2026-07-09 EDT.

The selected JSON records were opened directly. Candidate code, simulator tool order, submitted
evidence references, target replay, historical replay, terminal status, and locked conditions
were checked against each record rather than inferred from the panel summary.

## Representative qualified records

| Instrument | Initial physical verdict | Repair protocol | Final / locked result | Inspection |
| --- | --- | --- | --- | --- |
| absorbance plate read | `ADMIT` nominal; `REJECT` changed condition | read source and current skill → simulate → cite `gate:11e7fd3184a0:repair` → edit → replay → history → finish | `ADMIT`; 50/50 | Wavelength/integration/exposure edit corresponds to failed integration, blank, Beer–Lambert, and saturation checks; unloading and shutdown remain present. |
| fluorescence plate read | `ADMIT`; `REJECT` | same required event order; cited `gate:78a3209ad97e:repair` | `ADMIT`; 50/50 | Gain repair corresponds to gain-support, fluorescence-reference, and saturation failures; cleanup is preserved. |
| calibrated pump dose | `ADMIT`; `REJECT` | cited `gate:a9bc617c9d8b:repair` before changing speed | `ADMIT`; 50/50 | Repair lowers speed while preserving calibration, target volume, halt, and history. |
| dual-pump blend | `ADMIT`; `REJECT` | cited `gate:8e96975908b5f:repair` before changing both speeds | `ADMIT`; 50/50 | Both channel calibrations, the 60:40 composition, total volume, and `halt_all` remain present. |
| isothermal hold | `ADMIT`; `REJECT` | cited `gate:5dc47e37a52e:repair` before changing settle time | `ADMIT`; 50/50 | Repair addresses settle/hold violations and preserves deactivation. |
| thermal cycle | `ADMIT`; `REJECT` | cited `gate:980489cc19b0:repair` before changing both waits | `ADMIT`; 50/50 | Both temperature plateaus, hold durations, history, and deactivation are preserved. |
| microscope autofocus | `REJECT` | cited `gate:87d4e2c18724:repair` after calibrated-focus and image-focus failures | `ADMIT`; 10/10 | Sweep expands from 2,000 to 3,000 steps; calibration, settling, frame capture, release, and historical replay are present. |

Every representative qualified repair contains a simulator observation before its first edit,
an evidence reference that appeared in that observation, a later target replay, a later history
replay, and terminal `CANDIDATE` status.

## Every unqualified microscope record

| Replicate | Terminal status | Locked result | Direct reason for rejection |
| --- | --- | --- | --- |
| 01 | `CANDIDATE` | 9/10 | One frame at start z=1146.584187 fell below the frozen Laplacian-focus ratio while FFT passed. This is a strict locked false rejection, consistent with the separately measured non-zero valid-case false-reject rate. |
| 05 | `MAX_TURNS` | 6/10 | Four submitted revisions did not reach a valid finish call; the 2,400-step final sweep also missed or blurred four hidden conditions. |
| 06 | `MAX_TURNS` | 7/10 | The event chain ended without `finish_repair`; three hidden conditions failed. |
| 07 | `CANDIDATE` | 6/10 | The 2,400-step patch passed the observed start z=1200 case but failed four larger hidden offsets. The gate caught fixture-specific repair. |
| 08 | `MAX_TURNS` | 5/10 | Four revisions exhausted the turn budget; the 2,300-step final sweep was not robust. |
| 09 | `MAX_TURNS` | 6/10 | Four revisions exhausted the turn budget; the 2,500-step final sweep remained non-robust. |

No failed locked suite or `MAX_TURNS` episode is labeled qualified. The raw records support the
panel breakdown of 4 qualified candidates, 2 locked-validation failures, and 4 terminal-state
failures. The external-family 40% qualification rate fails the frozen 80% bar and is retained
as a blocker to the four-family systematic claim.
