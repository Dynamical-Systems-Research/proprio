# Protocol amendments and invalidated runs

## 2026-07-10: repair-episode budget before the OpenFlexure causal study

The one-episode engineering pilot showed that truthful simulator feedback identified the correct
repair mechanism in all three fault cells, but two cells needed another edit after the first
repair: one to remove a DSL-incompatible cast and one to extend sweep coverage to the diagnosed
boundary. Because one or two edits would conflate causal use of feedback with an artificially
short interaction horizon, the preregistered method now permits an initial candidate followed by
at most four evidence-conditioned repair episodes. Each episode starts from the prior candidate,
receives a fresh simulator/verifier result under its assigned feedback arm, may submit at most one
repair, and must replay the visible suite. All four arms receive the same maximum episode and model
turn budgets; deterministic admission is the only early-stop condition.

This amendment was made before the 30-trial causal study and before method freeze. The earlier
one-episode run remains an excluded engineering pilot under
`artifacts/invalidated/adaptive-microscopy-causal-pilot-one-round/`. The four-episode budget is
also the frozen archive-search repair depth for subsequent families. Increasing the interaction
horizon does not transfer promotion authority to the model: only external execution and physical
checks can admit a candidate.

The first four-episode engineering rerun stopped without a verdict in the third fault cell. An
agent submitted a changed candidate at its model-turn limit before replaying it; the next episode
correctly rejected the stale suite because its candidate hash no longer matched the current code.
The harness now performs and records an external post-episode replay whenever those hashes differ,
then supplies that fresh record to the next episode. It also writes each episode and locked replay
atomically as they finish and closes provider and simulator transports on every path. The crashed
run is excluded and retained under
`artifacts/invalidated/adaptive-microscopy-causal-pilot-four-episode/`.

The same pilot showed that a valid sweep-coverage recovery can reposition in bounded increments
and then perform a second autofocus without increasing the maximum sweep width. The original AST
classifier labeled that composite procedure only as a stage correction. Before confirmatory
execution, the mechanism contract was corrected: increased repeat count maps to repeated evidence;
an increased autofocus width or an additional autofocus call maps to coverage recovery; otherwise
an added relative move maps to stage correction. Deterministic physical admission remains the
authority, and the no-feedback arm's successful source-only coverage guess remains negative causal
evidence in the preserved pilot rather than being relabeled or removed.

A later engineering attempt stopped during sweep coverage after GMICloud returned a transient
HTTP 502. The completed temporal-precision cell and every finished sweep episode are preserved,
but the attempt has no panel verdict and is excluded. Before the binding 30-trial study, the
transport policy was fixed at three attempts per model turn for connection errors, timeouts,
HTTP 408/409/429, and HTTP 5xx, with fixed one- and two-second backoff. Failed transport attempts
are recorded raw and do not consume a model turn because no model generation was returned.
Non-retryable errors and a third failed attempt still stop the run. Completed trials may resume
only when their episode and locked-replay artifacts are complete and the hash-bound run manifest
matches every protocol input and setting.

The first binding attempt then exposed a second transport failure mode: the provider returned a
response object with no choice or assistant message. Four trials completed and a fifth was
partial, but the attempt stopped twice on this malformed response shape before a panel verdict
could be computed. The entire attempt is excluded and retained under
`artifacts/invalidated/adaptive-microscopy-causal-binding-transport-incomplete-v1/`; its trial
outcomes do not contribute to any reported rate or causal test. Before restarting the binding
study from trial zero, response-shape validation was added to the already registered three-attempt
transport policy. A missing choice or assistant message is captured raw and retried with the same
request, seed, prompt, candidate, simulator state, and model-turn budget. It does not consume a
model turn because no usable model action was returned. Prompts, DSL, search and repair budgets,
faults, arms, physical checks, promotion rules, thresholds, seeds, and analysis criteria remain
unchanged. The fresh 30-trial study is the only binding causal result.

## 2026-07-10: adaptive OpenFlexure focus-contract development

The first v0.2 smoke occurred after the required fixture preflight passed and before the v0.2
method freeze. DSV4 produced a bounded, executable, repeated-measurement autofocus procedure.
The procedure reached the calibrated focus plane, passed spatial focus, and had low repeat
spread, but the development verifier rejected its FFT improvement ratio because the start-z
800 baseline was already moderately focused. Baseline-relative gain therefore changed with the
starting state even when the final measurement was valid.

An initial 20-valid/20-invalid development battery appeared to separate absolute FFT and
Laplacian scores on one simulator process. A required four-process cross-check then falsified
that contract: OpenFlexure independently generates random specimen textures, so absolute
sharpness magnitude was specimen-dependent. It caused 7/20 false rejects on nominal
three-repeat acquisitions and 8/20 on intended five-repeat repairs. Those runs are retained
under `artifacts/invalidated/adaptive-microscopy-absolute-focus-calibration/` and
`artifacts/invalidated/adaptive-microscopy-uncertainty-absolute-focus-confound/`; neither counts
toward a claim.

Before a fresh labeled battery, the replacement contract was fixed to evidence the external
autofocus action actually exports: its raw image-sharpness-versus-stage sweep must cover the
calibrated plane, contain a prominent peak near that plane, and agree with the independently read
final stage position. Raw-frame integrity, detector saturation, dynamic range, repeated evidence,
operation order, and cleanup remain required. This avoids both near-focus baseline dependence and
cross-specimen absolute-score dependence without trusting a simulator-provided success flag.

The same development pass found that single-frame spatial sharpness scores increase under high
simulated camera noise. Absolute FFT and Laplacian checks therefore cannot establish acquisition
precision by themselves. Before the labeled uncertainty battery, the adaptive verifier added a
separate repeated-frame standard-error check: median temporal pixel sigma divided by the square
root of repeat count and by spatial image contrast must be at most 1.1 percent. A provisional
one-percent limit rejected both the intended three-repeat invalid control and the intended
five-repeat repairable control; that run is retained and excluded. The 1.1-percent operating
point was then fixed before the labeled battery. The exploratory noise sweep is method-development
evidence only; it is not counted in the confirmatory battery.

The first repeat-uncertainty rerun applied elevated camera noise before both autofocus and final
measurement. Although the temporal statistic behaved as intended, 2/20 five-repeat controls lost
autofocus-curve prominence; post-focus repetition could not repair that upstream failure. That
run is retained under
`artifacts/invalidated/adaptive-microscopy-uncertainty-autofocus-noise-confound/`. Before the next
battery, the development intervention was narrowed to post-focus measurement noise while the
autofocus sweep remains at the calibrated noise setting. No threshold changed.

A subsequent partial run exposed a curve-segmentation error: prominence had been computed over
the complete autofocus transaction, including the final return to the selected peak. That return
could contaminate the edge baseline. Reanalysis of captured stage timestamps identified the
primary forward sweep as the largest positive stage displacement. On the primary segment, valid
development curves had prominence 0.607–0.859 and invalid truncated sweeps 0.130–0.336. The 0.5
prominence threshold was unchanged; the verifier now isolates the primary segment and requires at
least 15 camera samples on it. The confounded partial run is retained under
`artifacts/invalidated/adaptive-microscopy-uncertainty-full-transaction-curve-confound/`.

With curve acquisition isolated, the next battery showed that one five-frame series still
exceeded the unchanged 1.1-percent standard-error limit in more than five percent of cases. The
validity threshold was not relaxed. Before the next battery, the repair budget was increased to
two bounded five-frame series, with all ten raw frames retained by the verifier. The failed
five-frame run is retained under
`artifacts/invalidated/adaptive-microscopy-uncertainty-five-frame-budget/`.

No v0.1 frozen source, adapter, verifier, cassette, or result changed, and no future confirmatory
family has been selected or evaluated.

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
