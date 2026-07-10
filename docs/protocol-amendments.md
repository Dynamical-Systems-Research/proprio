# Protocol amendments and invalidated runs

The frozen confirmatory generation and locked-validation contract is hash-bound in
`src/proprio/data/confirmatory-preregistration.yaml`. Post-validation semantic-review
calibration changes are recorded here so the preregistration hash remains reproducible.

## 2026-07-09 — fabricated provenance

The first partial semantic-judge calibration accepted a fabricated evidence reference when
the final code replayed successfully. The run was stopped and is excluded from all metrics.
Evidence provenance was already part of the frozen pass rule; the implementation now enforces
inspect, trace-grounded edit, and replay as a deterministic conjunctive admission condition.
The semantic-review prompt treats false provenance as an independent critical defect. No
confirmatory draft, repair, simulator result, locked condition, causal metric, or deterministic
physical threshold changed. Evidence is retained under
`artifacts/invalidated/judge-fabricated-evidence-miss-20260709/`.

## 2026-07-09 — unavailable evidence status

The second partial judge calibration returned `REJECT` rather than the preregistered honest
`HOLD` when the simulator link was unavailable. The run was stopped and excluded. The reviewer
contract now states that missing execution evidence cannot itself prove a defect. No
confirmatory generation, repair, simulator, verifier, locked condition, metric, or deterministic
admission result changed. Evidence is retained under
`artifacts/invalidated/judge-unavailable-status-miss-20260709/`.
This initial interpretation was later superseded by the confounded-fixture analysis below;
the stricter `HOLD` rule remains part of the frozen reviewer contract.

## 2026-07-09 — confounded unavailable-evidence fixture

The first unavailable-evidence fixture combined a down simulator link with a speculative edit
and unsupported diagnosis. That made `REJECT` defensible even though the category expected
`HOLD`. All captured unavailable cases using that fixture were excluded. The corrected case
isolates epistemic unavailability: no edit is made, no repair diagnosis is submitted, and the
only missing evidence is execution through the unavailable link. Other judge categories and
their captured results are unchanged.

## 2026-07-09 — judge calibration and confirmatory split

The diagnostic instrument panel was used to calibrate two explicit reviewer rules: fabricated
provenance is independently disqualifying, and a target execution gate of `HOLD` forbids
`ACCEPT` even when nominal replay passes. Diagnostic judge cases are retained under
`cassettes/judge-calibration-diagnostic/` and do not count as judge-metrology validation.
After the reviewer prompt was frozen, the reported semantic-mutation battery moved to the six
confirmatory instruments, whose judge cases had not been used during prompt calibration.

## 2026-07-09 — intermediate repair evidence in semantic review

The first additive-manufacturing evolution reviews saw only initial and final execution gates.
They therefore mislabeled valid intermediate gate references as fabricated, even though the
deterministic provenance checker found those references in the captured simulator event chain.
Those two reviews were preserved and superseded. The reviewer tool now exposes all simulator,
repair-submission, and history events when they exist; single-repair judge-metrology cases are
unchanged because they carry no captured protocol events.

## 2026-07-09 — post-format deterministic evidence refresh

Release replay detected that code formatting had changed the content hash of the confirmatory
verifier after the live model episodes were captured. Model-authored skills, raw messages,
tool calls, labels, thresholds, simulator outcomes, and pass/fail decisions were unchanged.
The deterministic initial/final gates, selection seals, locked validations, metrology records,
summary, and catalog bindings were regenerated from the unchanged candidates against the final
formatted source. Replay then returned 12/12 byte-identical and reset-idempotent episodes.
Captured raw tool and judge events remain untouched and retain the verifier hash actually seen
during the live episode.
