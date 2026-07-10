# Protocol amendments and invalidated runs

The frozen confirmatory generation and locked-validation contract is hash-bound in
`src/proprio/data/confirmatory-preregistration.yaml`. Post-validation semantic-review
calibration changes are recorded here so the preregistration hash remains reproducible.

## 2026-07-10 — external unavailable-review fixture discovered after freeze

The OpenFlexure `unavailable-evidence` confirmatory case retained a different final skill even
though the target simulator was unavailable and no repair submission existed. The diagnostic
builder had already been corrected to isolate unavailability, but the separately implemented
microscope builder still selected its default 3,200-step proposed sweep rather than preserving
the 2,000-step parent. Qwen correctly rejected the unsupported change after fresh nominal
replay also failed. The raw confirmatory case remains in the reported panel, the independent-
reviewer confirmatory gate remains failed, and no prompt, expected label, result, or aggregate
was changed after inspection. The released builder now preserves identical code for future
unavailable cases and has an explicit isolation regression. This repair is not used to claim a
post-hoc confirmatory pass.

## 2026-07-10 — replication seed derivation

The first partial expanded-replication capture was invalidated before a panel result was
computed. Sharding one instrument per process used a subset-local instrument index, which
reused the same ten OpenRouter seeds across different instruments. Although conversations and
source bundles were distinct, that did not satisfy the preregistered globally unique seed
contract. Seed derivation now uses the frozen full-panel index. The study restarted from an
empty cassette directory; none of the partial candidates or outcomes is included.

## 2026-07-10 — independent reviewer omitted-provenance calibration

The first expanded reviewer calibration accepted a technically correct repair whose submitted
`evidence_refs` list was empty. Its reasoning explicitly noticed the R1 violation but treated
the replay record as a substitute for repair provenance. That contradicts Proprio's admission
contract: provenance belongs to the submitted repair and cannot be reconstructed after the
fact. The reviewer prompt now gives explicit verdict precedence and the concrete rule “empty
references plus a correct patch is `REJECT`.” All cases from that diagnostic calibration
attempt were excluded and moved under `artifacts/invalidated/`; no confirmatory reviewer case
had run, and no deterministic gate, model-generated skill, simulator, threshold, or panel
result changed.

The initial interrupt did not terminate in-flight thread-pool workers. One old-prompt case was
therefore written into the newly created output directory. Both reviewer processes were
terminated by PID, the mixed directory was moved to
`artifacts/invalidated/independent-review-stale-process-write-20260710/`, and the clean rerun
started only after process-level verification showed no reviewer process alive. The stale case
is excluded.

## 2026-07-10 — frozen verifier formatting guard

Release formatting attempted to wrap one long expression in the already-frozen microscope
verifier. The preregistered SHA-256 test failed before any commit or result regeneration. The
exact pre-freeze bytes were restored from the captured build-session record, the original hash
was recovered, and the frozen verifier was excluded from subsequent mechanical formatting.
Its hash remains enforced by the research-protocol test. No executable behavior, threshold,
model output, simulator record, or reported outcome changed.

## 2026-07-10 — unavailable-review fixture isolation

The second independent-reviewer diagnostic attempt returned `REJECT` on two cases labeled as
unavailable. Inspection showed that the fixtures exposed a second defect: one skill conflicted
with a source-declared setting, while another was treated as an omitted repair even though no
edit had been proposed. Those cases could not isolate uncertainty handling. The entire attempt
was excluded before any confirmatory review. The replacement fixture uses a source-grounded,
nominally passing, byte-identical skill on both sides of an unavailable target execution. The
rubric now states that the absence of a repair submission in that no-change case is expected,
not missing provenance. No confirmatory reviewer case, generated skill, deterministic gate,
simulator, physical threshold, or replication result changed.

## 2026-07-10 — isolated microscope replication shards

The first microscope replicate passed all ten hidden conditions but required approximately ten
minutes through the external API. The remaining frozen replicate indices were scheduled across
isolated OpenFlexure processes. Each process uses the same pinned server revision and public
API, while retaining separate in-memory simulator state. Panel-global seeds, fresh agent
histories, source bundles, prompts, physical thresholds, and hidden conditions remain
unchanged. The canonical summary is recomputed once from all ten non-overlapping replicate
directories; per-shard summaries are not reported as panel results.

## 2026-07-10 — executable versus physically admitted initial drafts

The replication summary initially implemented `initial_executable` as the complete physical
gate verdict. The external microscope made the conflation visible: a draft could compile,
execute every controller action, capture a frame, and release resources while the independent
focus check rejected the resulting image. The preregistered first claim and metric name concern
executable code, while measurement validity belongs to the next admission claim. Before a full
panel summary, the metric was corrected to require static safety and runtime completion.
Initial full measurement validity is now reported separately, including every focus rejection.
Final qualification remains unchanged: target replay, history, provenance, and all hidden
physical conditions must pass.

The same partial capture exposed a second summary omission: qualification did not explicitly
conjoin the agent's terminal status. The protocol already declares `CANDIDATE` as the only
promotable repair outcome. The summary now rejects `MAX_TURNS`, `HOLD`, and `REJECT` even when a
last replay happened to pass. Raw episodes and locked results are unchanged.

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
