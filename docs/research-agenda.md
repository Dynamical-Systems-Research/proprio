# Research agenda: simulator-grounded instrument skill evolution

## North-star claim

Across scientific-instrument families held out from method development, DSV4 generates
runnable skills, uses simulator and verifier feedback to repair failed drafts, and Proprio
admits only candidates that pass independent execution and physics-grounded validity gates.
The result establishes a reproducible pre-deployment qualification method. Real-hardware
qualification remains a separate gate.

This agenda is tracked in Linear project
[Proprio: Simulator-Grounded Skill Evolution](https://linear.app/mach-10/project/proprio-simulator-grounded-skill-evolution-d146f2fb244c).
The preregistered machine-readable contract is
[`skill-evolution-preregistration.yaml`](../src/proprio/data/skill-evolution-preregistration.yaml).
The expanded replication and independent-review contract is
[`expanded-confirmatory-preregistration.yaml`](../src/proprio/data/expanded-confirmatory-preregistration.yaml).

## Decision and stakeholder

The decision is whether an agent-authored instrument skill is safe and evidence-valid enough
to advance from documentation into a supervised hardware qualification. Instrument operators,
facility owners, scientific-policy authors, and skill-library maintainers need the decision.
The useful artifact is an immutable skill package accompanied by source, simulator, verifier,
repair, replay, support, and admission provenance.

## Prior-art fidelity gate

Before an adjacent system can appear in public positioning or determine an experiment, its
primary paper must be read and reduced to a claim card with six separate fields: demonstrated
mechanism, interaction environment, adaptation loop, hardware involvement, statistical
support, and author-stated limitation. Summary language cannot replace this card. Similar
surface language such as "learns on the job" or "operates an instrument" is not evidence that
two systems use the same feedback, repair, or qualification authority.

Every related-work row must cite the exact primary location supporting each field. If a paper
shows an effect but explicitly reports that it was not statistically established, Proprio must
preserve both facts. Public copy and the experiment matrix remain blocked until this fidelity
check is complete.

The current cards and the resulting claim corrections are maintained in
[`prior-art-claim-cards.md`](prior-art-claim-cards.md).

## Claim gates

1. DSV4 drafts an executable skill from an instrument source bundle.
2. A simulator and independent physical gate admit the right draft and reject the wrong one.
3. DSV4 causally uses execution evidence to repair a failed draft.
4. The frozen method clears the same rubric across held-out instrument families.
5. Simulated deployment drift produces a staged, regression-safe evolution proposal.

Passing a later gate requires all earlier gates. A simulator-only result never establishes
unsupervised real-hardware operation.

## v0.2 method revision after the external-family failure

The v0.1 admission mechanism behaved correctly: it refused to promote six invalid or
incompletely validated OpenFlexure candidates. What failed was the straight-line skill
representation and single-trajectory repair method. OpenFlexure is therefore moved into method
development. Its prior 4/10 result remains unchanged as failure evidence and cannot contribute
to the next generalization claim.

The v0.2 method is preregistered in
[`adaptive-method-preregistration.yaml`](../src/proprio/data/adaptive-method-preregistration.yaml)
before its first adaptive OpenFlexure model call. It introduces:

- a bounded adaptive executor with finite loops, observation-conditioned branches, safe
  arithmetic, explicit call limits, and no exception swallowing or hidden-state access;
- three repeated measurements per visible condition, with deterministic ADMIT / REJECT / HOLD
  aggregation and independent recomputation from raw evidence;
- a visible multi-condition debug distribution rather than one fixture;
- four independent initial drafts, a two-candidate Pareto archive, and at most four
  evidence-grounded repair rounds, for no more than 12 generated candidates;
- deterministic fixture preflight before model invocation and one-shot locked qualification
  after candidate selection.

This is a multi-turn search/revision environment. DSV4 may inspect controller observations,
execution traces, and immutable check records, but cannot inspect verifier code, simulator
internals, locked conditions, or a golden patch. Physical and procedural gates remain the sole
promotion authority. Agent review remains a supplemental veto or hold.

The original plan required a 30-trial OpenFlexure causal panel before method freeze. Four trials
completed under one hash-bound manifest before a malformed provider response stopped the run.
The human research lead then froze the complete method configuration and redirected the remaining
live-inference budget to the held-out-family study. The four trials are locked exploratory
development evidence: truthful feedback qualified 3/4 candidates, while no feedback and
mismatched feedback qualified 0/4; the one-sided exact paired p-value is 0.125. This does not
establish the preregistered causal claim, and the report must not describe it as a confirmatory
pass.

The four-trial panel is not the complete causal evidence. Across the prior frozen six-instrument
confirmatory panel, the eight-instrument diagnostic panel, and the final-protocol OpenFlexure
trials, 18 non-overlapping paired units are available. Truthful simulator feedback produced 14/18
non-regressive repairs, compared with 0/18 from the same drafts without feedback. The exact
one-sided paired p-value is 0.000061, and all three cohorts have positive uplift. This accumulated
evidence establishes the broad simulator-feedback repair mechanism. Because the synthesis spans
three protocol generations, it remains separate from the uncompleted 30-trial OpenFlexure rate
estimate and from the binding held-out-family generalization claim.

After the configuration freeze, at least three independently maintained external simulator
families may be preregistered before inspection or invocation. Those families remain untouched by
method development, and each must independently pass acquisition, physical qualification, causal
repair, and simulated drift evolution over at least twenty fresh DSV4 generations. Aggregate
performance cannot rescue a failed instrument.

## Binding held-out simulator preflight result

The three-family panel was registered and committed before the selected upstream implementations
were cloned or imported. Deterministic capability and live-smoke preflight then failed all three
families before any DSV4 call:

| Family | Binding preflight result | Reason |
|---|---|---|
| OctoPrint virtual printer | `HOLD` | Nominal printing works, but upstream declares no maximum hotend/bed temperatures and cannot produce the registered heater-response or readback-offset drift. |
| PyMoDAQ `MockSpectro` | `HOLD` | The pinned runtime exposes `Mock`, not `MockSpectro`; cleanup is unobservable, one retained channel fails the registered Gaussian-fit threshold, and the registered drift API is absent. |
| sinstruments Pace pressure controller | `HOLD` | The emulator has no reset, range/unit queries, vent, bounds, or setpoint-coupled pressure dynamics; the Pace plugin was also not revision-pinned by the selected repository. |

The panel verdict is `FAIL`: zero of three families cleared fixture preflight, zero model calls were
made, and no family was replaced or rescued by aggregate performance. This result does not show
that DSV4 failed an executable held-out task. It shows that repository metadata and nominal mock
execution are insufficient to establish that an external simulator can support a physics-grounded
qualification contract. Cross-family generalization of the frozen v0.2 method remains not
established. Raw probe transcripts, runtime versions, source references, and per-requirement
outcomes are retained in
[`artifacts/evidence/heldout-generalization/preflight/`](../artifacts/evidence/heldout-generalization/preflight/).

## Expanded experiment matrix

| Question | Unit and intervention | Authority | Frozen pass condition | Artifact |
|---|---|---|---|---|
| Does generation success survive replication variance? | Ten fresh DSV4 histories and unique provider seeds per confirmatory instrument at temperature 0.7 | Simulator, physical checks, historical replay, and sealed conditions | At least 75% initial executable and 80% qualified for every instrument; zero unsafe promotions | `cassettes/replication-dsv4/` |
| How much instrument-specific engineering is hidden in each result? | Nonblank source lines, physical checks, invalid classes, dependencies, and prospectively logged execution latency | Repository source and generated manifests | Report every family; person-hours remain unavailable unless actually logged | `artifacts/evidence/engineering-burden/` |
| Is a non-XRD verifier coupled to its simulator? | OpenFlexure images scored by frequency-domain energy and an independently implemented spatial Laplacian measure | Conjunctive physical gate; public stage state is a third check | Zero false-valids, at most 5% false rejects, at least 90% valid-case concordance; invalid disagreement reported | `artifacts/evidence/microscopy/` |
| Does the frozen method cross another instrument-family boundary? | OpenFlexure camera, stage, calibration, and autofocus through its public LabThings API | External simulator at a pinned revision plus Proprio's independent checks | Same acquisition, repair, provenance, and locked-condition rules as the original panel | `sources/confirmatory/microscope-autofocus/` |
| Is semantic review merely correlated self-judgment? | Qwen 3.7 Plus, separately prompted, reviews labeled diagnostic and confirmatory cases with stateful tools | Supplemental veto only; deterministic gates remain authoritative | At least 95% critical recall, at most 10% valid false alarms, 100% honest holds, zero hard-failure overrides | `cassettes/independent-review/` |

## Development and confirmatory split

Method development used the area-detector powder-XRD reference, the Keithley 2450-style
simulated source-measure unit, and an eight-instrument diagnostic panel spanning liquid
handling, battery cycling, additive manufacturing, and quantum transport. The diagnostic
panel exposed the hidden executor-grammar bottleneck and was then used to add the disclosed
executor contract, historical replay, locked validation, and promotion controls. It therefore
does **not** count toward the final generalization claim, even though it was originally intended
as a held-out panel. Its failures and ablations remain reported as diagnostic evidence.

After those method decisions were frozen, a separate confirmatory panel was preregistered
before its first valid model call:

| Family | Variant | Control semantics | Physical contract |
| --- | --- | --- | --- |
| Optical measurement | `absorbance-plate-read` | wavelength, integration, plate read | signal range, integration support, clean lifecycle |
| Optical measurement | `fluorescence-plate-read` | excitation/emission, gain, plate read | spectral ordering, gain support, signal integrity |
| Calibrated delivery | `calibrated-pump-dose` | flow calibration, speed, timed dispense | delivered-volume tolerance and operating support |
| Calibrated delivery | `dual-pump-blend` | two calibrated pump channels | total-volume and blend-ratio conservation |
| Thermal control | `isothermal-hold` | setpoint, timed transition, hold | transition-time support, stability, final temperature |
| Thermal control | `thermal-cycle` | ordered setpoints and transitions | cycle order, ramp support, stability at both plateaus |
| Optical microscopy | `microscope-autofocus` | camera calibration, centered z-sweep, image acquisition | calibrated focus plane, dual-domain focus evidence, frame integrity, resource release |

The names identify reference simulation contracts, not claims of compatibility with a
specific commercial device. Source bundles cite PyLabRobot's plate-reader, pump, and
temperature-controller APIs plus an open SDL spectrophotometer example. No XRD-RL data,
VOE-Bench data, trained judgment checkpoint, or external policy-training distribution is an
input to the method or the confirmatory evaluation.

## Multi-turn environment

Environment turn structure: **multi-turn search and revision**.

- Episode horizon: 2 to 12 model turns.
- Initial state: source bundle, empty or current skill, simulator identity, and public support
  contract.
- Policy actions: inspect sources, draft, run simulator, inspect trace, inspect verifier result,
  diagnose, patch, replay, request comparison, self-assess, or hold.
- Policy-visible tools: source reader, simulator runner, trace reader, verifier-result reader,
  skill diff, reset, replay, and support inspection.
- Observations: content-addressed source excerpts, state transitions, measured values,
  postcondition outcomes, and honest error or unavailable statuses.
- Feedback timing: after every tool call; admission is terminal.
- Credit unit: the complete episode, with turn-level tool and revision diagnostics.
- Same-action-space baselines: no feedback, generic failure feedback, and mismatched feedback.
- Posthoc evaluators: hidden regression battery, hard admission gate, statistical report, and
  manual raw-record inspection.

The simulator and verifier never provide golden source code, a hidden fault label, or a patch.
The model may see measured values and public operating bounds that a real controller or
calibration procedure would expose.

## Causal repair design

Every repair comparison starts from byte-identical draft source and simulator state.

- `truthful`: complete execution and verifier evidence for the current failure.
- `generic`: failure status without quantitative or check-specific evidence.
- `none`: no simulator evidence; DSV4 is asked to reconsider the original draft.
- `mismatched`: truthful evidence from a different failure class with provenance removed.

The truthful arm must outperform the controls. Reasoning text is qualitative evidence only;
causality comes from the paired intervention and successful hidden replay.

Repairable cases include source misinterpretation, stale configuration, wrong sequencing,
wrong range, and changed fixture state. Non-repairable cases include unavailable hardware,
irrecoverable sensor failure, unsafe support excursions, and inconsistent sources without a
qualified authority. Correct behavior for non-repairable cases is `HOLD`, not a speculative
patch.

## Hybrid verification

Deterministic checks own syntax, action allowlists, state transitions, reset, safety limits,
physical postconditions, support, hidden regressions, and provenance. A stateful tool-using
agent judge reviews evidence grounding, root-cause quality, patch relevance, generality,
honest uncertainty, and attempted check bypass.

The agent judge may reject or hold a candidate. It cannot override a deterministic failure.
Judge state persists within one case and resets between cases. The judge cannot read hidden
test labels, verifier implementation, or a golden patch. Its tool calls and raw assistant
messages are captured. If the judge is unavailable, the hybrid verdict is `HOLD`.

The judge is calibrated against labeled semantic mutations and a human-inspected sample.
When DSV4 serves as both drafter and judge, the report labels the judge correlated secondary
evidence; the independent authority remains the simulator and physical gate.

## Preregistered pass bars

- Initial executable-draft rate: at least 75% across held-out variants.
- Truthful-feedback repair rate: at least 70% macro-average and at least 60% in every family.
- Causal uplift: at least 25 percentage points over `none`, with the paired 95% confidence
  interval lower bound above zero.
- Regression rate after repair: at most 5%.
- Valid false-reject rate: at most 5%.
- Safety-critical false admission: zero observed across at least 300 invalid simulations per
  failure class.
- Agent-judge critical-defect recall: at least 95%; false-alarm rate at most 10%; zero
  deterministic-failure overrides.
- Simulated-drift evolution: at least 70% of repairable drift cases staged successfully, zero
  unsafe promotions, and no mutation of the previously admitted package.

Results are reported per instrument, family, failure class, and feedback arm. The instrument
is the primary generalization unit. Aggregate success cannot hide a failing family.

## Confirmatory result

The frozen DSV4 route produced executable nominal skills for 6/6 instruments across optical
measurement, calibrated delivery, and thermal control. Starting from byte-identical drafts,
truthful simulator feedback produced 6/6 qualified repairs while no feedback produced 0/6;
the paired uplift and its bootstrap 95% interval were both 1.0. All truthful repairs preserved
nominal behavior, cited exposed evidence before editing, replayed after editing, and passed 50
sealed conditions per instrument with zero regressions.

Independent metrology covered 9,000 labeled simulations and observed zero false admissions
and zero false rejections. Offline replay reproduced all 12 arm episodes and 600 locked
conditions byte-identically. After prompt calibration on the diagnostic panel, the frozen
stateful reviewer passed 24/24 confirmatory semantic-mutation cases: 100% critical-defect
recall, 0% false alarms on valid repairs, 100% honest holds for unavailable target execution,
and zero hard-gate overrides. The model, provider, resolved revision, raw reasoning state,
tool calls, simulator traces, and usage are retained in the cassettes. None of these results
uses XRD-RL data, VOE-Bench data, or a trained judgment checkpoint.

### Expanded replication result

Ten independent DSV4 generations were then run for every confirmatory instrument with fresh
histories and panel-global unique seeds. The original six reduced-order instruments qualified
60/60 candidates. The externally simulated OpenFlexure microscope did not reproduce that
result: 10/10 drafts executed, 3/10 initial measurements passed the physical gate, and only
4/10 repaired candidates cleared target replay, historical replay, provenance, terminal
status, and all ten locked offsets. The preregistered requirement was at least 80%
qualification for every instrument, so the four-family systematic-generalization claim is
**failed** rather than averaged away.

Across all seven instruments, 68/70 initial drafts executed and 64/70 candidates qualified.
The six unqualified microscope episodes comprised four `MAX_TURNS` outcomes and two locked-
validation failures. None was promoted. One locked failure was a strict physical false
rejection consistent with the separately measured non-zero valid-case false-reject rate; the
other caught a fixture-specific repair. The full records and Wilson intervals are in
[`cassettes/replication-dsv4/summary.json`](../cassettes/replication-dsv4/summary.json), with
direct inspection of every failure in
[`manual-inspection.md`](../cassettes/replication-dsv4/manual-inspection.md).

This result supports repeated source-to-skill acquisition across the original three families
and an external-family generation-verification gap. It does not support systematic
generalization across all four families.

### Independent-review result

The frozen Qwen 3.7 Plus reviewer passed 56/56 diagnostic calibration cases and 42/42 cases on
the original six confirmatory instruments. Across the full seven-instrument panel it matched
47/49 preregistered labels. Both mismatches occurred on OpenFlexure fixtures whose fresh replay
did not support the expected label: the nominally valid repair regressed FFT focus, and the
unavailable case contained an unsubmitted skill change plus a replay failure. Qwen rejected
both under the hard-evidence rubric.

Consequently, critical-defect recall remained 100% and hard-gate overrides remained zero, but
the 14.3% valid-label false-alarm rate and 85.7% unavailable-label accuracy failed their frozen
bars. The full independent-review claim gate is `FAIL`. The released unavailable fixture is
corrected for future experiments, while the captured confirmatory result remains unchanged.
Qwen and DSV4 agreed on all 24 original shared cases (Cohen's κ=1.0); that agreement is
reported as reviewer correlation, not independent physical evidence.

## Skill evolution after simulated deployment

An admitted package is immutable. A versioned simulator change creates deployment-like
evidence for API changes, calibration or fixture shifts, timing changes, and hardware
degradation. DSV4 may propose a new package, but promotion requires the new cases, the entire
historical replay archive, support checks, and hybrid review. The proposal records its parent,
rollback target, evidence hashes, and `hardware_gate_required=true`.

The proposal is staged rather than auto-adopted. A real deployment would additionally require
shadow operation, a supervised hardware canary, facility interlocks, and operator or domain
expert sign-off.

The executed evolution battery detected simulated drift in 8/8 diagnostic instruments and
staged 8/8 repaired proposals after historical replay, locked validation, provenance checks,
and semantic review. Deterministic replay reproduced all eight statuses byte-identically, with
zero unsafe promotions and every proposal still blocked on hardware qualification.

The same evolution procedure did not close on the external OpenFlexure family. Starting from
the lowest-index qualified replication candidate, DSV4 inspected the drift evidence and tried
five autofocus sweep widths, but exhausted its turn budget with a candidate that still failed
the target Laplacian-focus threshold and regressed nominal FFT focus. The independent Qwen
reviewer rejected the hard failure. Proprio therefore did not stage or package an OpenFlexure
evolution proposal. The reduced-order evolution result remains an existence proof; it is not
evidence that evolution generalizes to the external simulator.

## Source and simulator strategy

Proprio adopts existing interfaces and simulations where they are permissively licensed and
fit the test contract:

- [PyLabRobot](https://github.com/PyLabRobot/pylabrobot) is MIT-licensed and supplies
  hardware-agnostic liquid-handling backends, including Opentrons simulation.
- [Acceleration Consortium OT-2 connector](https://github.com/AccelerationConsortium/opentrons-ot2)
  supplies SiLA2 and HTTP control semantics plus motion, calibration, and pipette simulations.
- [PyBaMM](https://github.com/pybamm-team/PyBaMM) is BSD-3-Clause and supplies physics-based
  battery models and executable cycling experiments.
- [QCoDeS](https://github.com/microsoft/Qcodes) is MIT-licensed and supplies modular quantum
  measurement drivers and simulated PyVISA instruments for magnets, temperature controllers,
  source-measure units, and acquisition devices.
- [Matterix](https://github.com/AccelerationConsortium/Matterix) is BSD-3-Clause and provides
  a higher-fidelity optional robotics and wet-lab twin; it is not required for CPU CI.
- [NIST powder-bed-fusion research](https://www.nist.gov/additive-manufacturing/research-areas/technologies/powder-bed-fusion)
  grounds the additive-manufacturing contract. The CPU release uses an explicitly labeled
  reduced-order simulator; higher-fidelity MOOSE or OpenFOAM integrations remain external.

Reduced-order reference simulators must expose their approximation and correlated-oracle
risk. They may prove the skill-acquisition method within declared support; they may not be
described as full hardware twins.

## Evidence artifacts

Each live episode writes the source hashes, prompt hash, inference configuration, raw model
messages, tool calls, skill versions, simulator trace, feedback bundle, deterministic verdict,
agent-judge trace, hidden replay results, and final status. Checked-in cassettes make CI
deterministic, while a separate live-generation command re-runs DSV4 for release evidence.

The final report includes paired repair statistics, family results, judge metrology, drift
evolution, raw manual inspection, and residual risks.

## ASPIRE-informed locked validation

[ASPIRE](https://research.nvidia.com/labs/gear/aspire/) is the closest methodological
comparator for iterative code-as-policy repair. It combines fine-grained execution traces, a
validated repair library, and evolutionary search over programs. Its algorithm separates a
debug condition set from a validation condition set, and its released prompts explicitly
lock validation seeds until the final candidate is selected. Proprio adopts that separation
in the confirmatory and evolution protocols while preserving a different admission authority:
instrument candidates must satisfy independent execution and physical postconditions, not
only a task-completion score.

The implemented protocol adds:

- fixed debug conditions available to DSV4 during repair and a preregistered one-shot
  validation sweep that is unavailable to the model during iteration;
- identical simulator, controller API, prompt, and model route across candidates;
- a simulator-information firewall that exposes controller-observable telemetry but forbids
  access to simulator internals, verifier implementation, hidden predicates, and validation
  seeds;
- bounded multi-turn candidate repair, with every submitted edit required to cite exposed
  evidence and state its expected effect and residual risks;
- selection on debug conditions followed by exactly one validation run, with no repair or
  reselection after validation evidence is revealed;
- admission of reusable repair patterns only when the final package passes the hidden sweep,
  historical regression archive, semantic review, and physics-grounded gates.

ASPIRE also reports that its execution engine produces the largest ablation gain and states
that real-world lifelong operation still requires robust success detection, safe reset,
safety monitoring, and calibration maintenance. Those observations reinforce Proprio's
focus on instrument-specific evidence validity and its explicit separation between
simulation qualification and real-hardware qualification. Proprio does not claim ASPIRE's
robotics benchmark results or direct policy transfer; it uses the paper's debug/validation
discipline and trace-guided search as research-design precedents.

## Falsifiers and stop conditions

The target claim fails if truthful feedback does not beat controls; any family misses its
floor; any hard-invalid candidate is admitted; a repair succeeds only by hardcoding one case;
the judge overrides physics; held-out prompt facts leak from development; drift mutates an
admitted skill; artifacts cannot replay; or any simulator/unavailable path is reported as a
clean pass. A failed gate is reported as a blocker and narrows the public claim.
