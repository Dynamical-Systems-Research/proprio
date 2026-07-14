# Proprio: Simulator-Verified Skill Acquisition for Scientific Instruments

**Dynamical Systems Research, Technical Report, July 2026**

[Code](https://github.com/Dynamical-Systems-Research/proprio) ·
[Skill catalog](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json) ·
[Published skills](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills) ·
[XRD reference](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/xrd-operate-observe) ·
[Keithley 2450](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/keithley-2450-measure-current) ·
[North pipette calibration](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/external/north-pipette-calibration) ·
[HELAO Gamry CV](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/external/helao-gamry-cv) ·
[CLSLab spectrometer](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/external/clslab-light-spectrometer) ·
[Agent loop](https://github.com/Dynamical-Systems-Research/proprio/blob/main/src/proprio/agent.py) ·
[OpenFlexure full-loop agent demo](https://github.com/Dynamical-Systems-Research/proprio/blob/main/public/proprio-demo.mp4) ·
[Video evidence manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/public/proprio-demo.json)

*Every number in this report is recomputed from evidence artifacts committed to `main` at
[`c2cd6be`](https://github.com/Dynamical-Systems-Research/proprio/commit/c2cd6be). The persistent
cross-family panel described below is bound to method digest `c1a28d…7267`
([freeze manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/artifacts/evidence/cross-family/method-freeze/manifest.json)).
Each result links to the record it comes from.*

Every new instrument brings the same integration work. Someone reads the manual, learns the control
interface, writes a procedure, tests it, and decides whether the result is safe to reuse. That work
is slow and hard to reuse because instrument operation turns on details that rarely fit a common
abstraction: command order, calibration, timing, and the gap between a script that finishes and a
measurement that is physically valid.

We wanted to know how much of that loop an agent could carry itself.

We pointed DeepSeek V4 Flash at documentation for unfamiliar scientific instruments and gave it
access to their simulators. The model drafted operating skills, executed them, inspected the
failures, and revised its procedures in one persistent context. It could learn from every attempt,
but it could not decide when its own work was good enough. A separate verifier controlled what
entered the skill library.

Truthful simulator feedback produced 14 non-regressive repairs from 18 identical starting drafts.
Without that feedback, the same drafts produced none. Across six simulated instruments in three
families, 60 of 60 independent generations passed the registered checks. Under the frozen
persistent protocol, the agent completed skill acquisition, held-out verification, repair, drift
detection, and staged evolution in each of three external simulator families without promoting an
invalid candidate.

The result is narrower than autonomous instrument deployment. It shows that persistent test-time
learning can produce reusable instrument skills across the tested simulators when admission stays
outside the model. Real hardware remains a separate validation step.

## The Instrument-Operation Gap

Scientific instruments are becoming easier to address from software. [Bluesky](https://blueskyproject.io)
and [Ophyd](https://github.com/bluesky/ophyd) expose beamline devices through Python.
[SiLA](https://sila-standard.com) defines common interfaces for laboratory services.
[PyLabRobot](https://github.com/PyLabRobot/pylabrobot) and
[HELAO](https://github.com/High-Throughput-Experimentation) connect robotic workcells and
experimental workflows. [NIST places these systems within a broader modular laboratory architecture](https://www.nist.gov/publications/towards-composable-modular-laboratory-ecosystem-autonomous-materials-research-and)
built from replaceable instruments, controllers, data systems, and local agents. [*On the Need for
Autonomous Science Instruments*](https://chemrxiv.org/doi/full/10.26434/chemrxiv.10001836/v1)
similarly argues for open control and instruments designed for autonomous operation.

These interfaces give an agent a command surface. They do not tell the agent how to turn an
unfamiliar instrument into a reliable procedure.

That procedure carries physical assumptions. A liquid handler can execute every command and
deliver the wrong volume. A source-measure unit can return a reading after entering compliance. A
diffractometer can collect a complete frame after saturation or geometric misalignment. Software
success is one observation. The physical result is the one that matters.

## Skill Acquisition Through Execution

Recent instrument agents show that models can adapt while they operate. Chen et al. developed an
[X-ray alignment workflow](https://www.nature.com/articles/s42256-026-01261-5) against a virtual
six-circle diffractometer and later deployed it under supervision at a synchrotron. During the
beamline experiment, the agent detected an unexpected motor offset and carried the correction into
its next action.

Vriza et al. took a different route. Their [agents operated an X-ray nanoprobe and a robotic
thin-film platform](https://www.nature.com/articles/s41524-026-02005-0) through restricted function
libraries. Human corrections entered persistent memory and became available in later workflows.
The agents improved at command selection and action sequencing, although textual feedback did not
fix every visual-reasoning failure.

Both results point toward the same operating model. The agent does not need every procedure written
in advance. It can acquire procedural knowledge from interaction and carry that experience forward.

Robotics and general agent systems have developed the mechanics around this idea.
[Hermes `/learn`](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills#learning-a-skill-from-sources-learn)
turns documentation and prior workflows into reusable skill files.
[SkillOpt](https://arxiv.org/abs/2605.23904) treats the skill document as the trainable state of a
frozen model and accepts edits through held-out validation. [ASPIRE](https://arxiv.org/html/2607.00272v1)
gives coding agents detailed execution traces, lets them repair robot programs, and stores validated
repairs for later tasks.

Proprio applies that pattern to scientific instruments. The model reads the documentation, writes
the procedure, runs it, and revises from simulator evidence. The object being learned is the skill,
not the model weights.

## Separating Learning from Admission

Acquiring a procedure and deciding whether to trust it are different jobs, and Proprio keeps them
apart. The agent needs detailed feedback while it works: the command that failed, the state that
changed, the expected physical response, and the check that did not pass. That evidence lets it
diagnose the procedure rather than resample another draft blindly.

Admission runs on a separate path. Each instrument defines a bounded controller, a simulator, and
an instrument-specific verification contract. The contract checks observable behavior such as
delivered volume, voltage compliance, command ordering, focus quality, or measurement validity.
Development conditions supply feedback to the agent; held-out conditions decide whether a candidate
enters the catalog. The model cannot change those conditions or their thresholds, rewrite the
verifier, or promote a candidate because its explanation reads plausibly. A skill enters the
library only when every registered check passes.

This separation is what makes the learning loop useful. Because a failed candidate stays failed, the
agent can search aggressively without the search itself becoming a risk. The verifier checks whether
a procedure satisfies the registered simulated operating contract, so the scientist does not have
to inspect every intermediate attempt. The scientist defines that contract, the hardware-validation
boundary, and the experiment the instrument should serve.

![From addressable instruments to verified skills](assets/agent-to-instrumentation-gap.png)

**Figure 1.** Open interfaces expose instrument actions and observations, while simulators provide
a controlled environment for procedural interaction. Proprio preserves the agent's execution
experience across a test-time learning trajectory and uses independently implemented execution and
physical checks to govern skill admission. A simulation-verified skill still requires separate
site-specific validation before use on real hardware.

## Method

### Inputs and Outputs

| Object | Definition |
|---|---|
| Instrument sources | Manuals, API/driver documentation, and operating limits shown to the model. |
| Controller contract | The permitted commands and observable state; nothing else is callable. |
| Simulator | Executable instrument or process behavior, with explicit reset and failure semantics. |
| Physical contract | Independent, machine-checkable requirements for a valid operation and measurement (e.g., delivered volume within 0.10 mL at certified 0.050 mL/rev calibration). |
| Skill package | `SKILL.md` operating procedure, bounded control code, provenance hashes, and a link to the verification record, hash-bound in [`catalog.json`](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json). |

**Table 1.** The inputs Proprio consumes and the skill package it produces.

All reported model-driven studies used DeepSeek V4 Flash (DSV4, resolved
`deepseek/deepseek-v4-flash-20260423`) as the drafting and repair model. Qwen 3.7 Plus served as a
separately prompted independent reviewer. The interface is model-agnostic, and every reported
result remains tied to the model, provider route or allowlist, prompts, and sampling settings that
produced it.

### Operator Workflow

1. **Learn** a skill from instrument sources.
2. **Verify** it independently in simulation.
3. **Admit** the passing skill into the catalog.
4. **Monitor** execution evidence for drift.
5. **Stage** a verified evolution proposal when drift breaks the admitted skill.

> The agent drives discovery, execution, diagnosis, repair, and evolution; it cannot authorize
> promotion.

### Persistent In-Context Acquisition

Proprio treats simulator interaction as test-time procedural learning rather than model training.
The model weights remain fixed, while the caller preserves one context across each causal-repair or
evolution trajectory
([`agent.py`](https://github.com/Dynamical-Systems-Research/proprio/blob/main/src/proprio/agent.py)).
The model API itself may be stateless; Proprio resends the accumulated context on every call. Prior
actions, simulator responses, failed checks, diagnoses, edits, and outcomes therefore remain
available when the agent proposes its next procedure.

The persistent context serves the same role as an operator's notebook. It contains the full message
history and a compact repair ledger with the candidate hash, failed checks, cited evidence,
diagnosis, change, and outcome for every attempt. The loop checkpoints after each tool result and
verifier record, so an interrupted trajectory resumes without repeating a completed model call.
Duplicate candidate hashes are rejected, and deterministic compaction may shorten the resent
request without removing safety failures, candidate hashes, the repair ledger, or the latest
verifier result. The complete uncompressed record remains on disk.

Before repair begins, the method samples an archive of six independent drafts in a bounded control
dialect and executes them on **visible** simulator conditions whose evidence the agent may inspect.
The dialect permits finite loops and observation-conditioned branches while excluding hidden
simulator state, unrestricted imports, exception swallowing, and unbounded calls. Three candidates
survive archive selection on execution, physical validity, safety, and provenance. A selected
trajectory may then consume up to six repair rounds and 24 candidate variants. Every repair must
cite evidence identifiers that appear in the recorded trace; a patch with fabricated provenance
cannot be packaged even if it executes successfully.

### Fixed Admission Authority

Persistence changes what the agent can learn within a trajectory; it does not change who decides.
Simulator and verifier records return to the agent as tool results that may ground a new diagnosis
or edit, but promotion still depends on deterministic execution, physical-validity, provenance, and
locked-condition checks the agent cannot override. In a paired causal comparison, the truthful and
no-feedback arms branch from the same evidence-free prefix and keep separate histories thereafter,
so the feedback intervention cannot leak across arms.

Proprio's earlier studies used episodic repair: each attempt received the current candidate and the
latest verifier record but discarded the prior conversation. That gave a clean causal baseline at
the cost of re-deriving context on every attempt, and it is the baseline the persistent loop
improves on. The pooled causal result reported below is drawn from those episodic studies and is
presented as mechanism evidence, while the cross-family panel exercises the persistent loop end to
end.

### Verification and Admission

Development happens on visible conditions. Verification ends with a one-shot run on **locked**
conditions that were hidden during development, with no feedback. Deterministic execution and
physics checks are authoritative throughout. A model reviewer (or a human) may veto or hold a
candidate, but its opinion is advisory input to the decision, never the decision itself, and
nothing may rescue a failed deterministic check. Admission is **fail-closed**. A candidate is
admitted only when every deterministic check passes, and any failure, missing evidence, or
unresolved veto resolves to `REJECT` or `HOLD` (insufficient evidence to decide), never to a
pass. A `HOLD` is reported as such rather than converted into a pass or silently retried.

### Drift and Evolution

When a versioned simulator change makes a previously admitted skill fail, Proprio treats the
repair as a new admission problem, not an edit-in-place. The model generates an evolution proposal
from the observed drift evidence; the proposal must pass the changed condition, replay the full
historical set that previously worked (nominal behavior and prior repairs), and pass a fresh
locked sweep. Only a fully passing proposal is staged, with parent, rollback, evidence,
simulator, verifier, and validation hashes, and the previously admitted skill remains immutable.
A failed proposal is rejected and the parent is retained unchanged.

Evolving a skill under feedback is an established pattern. [Voyager](https://arxiv.org/abs/2305.16291)
grows an executable skill library from environment interaction and agent-evaluated task completion.
[GEPA](https://arxiv.org/abs/2507.19457) evolves prompts against task rewards, while
[SkillOpt](https://arxiv.org/abs/2605.23904) admits skill edits through held-out validation.
Unmanaged skill libraries can degrade as they grow, a failure mode named
[library drift](https://arxiv.org/abs/2605.19576). Proprio shares the iterative artifact-improvement
pattern while keeping admission with independently implemented execution and physical checks for the
instrument.

### Pre-Deployment Boundary

Simulation verification is a pre-deployment gate, not a deployment decision. Use on a physical
instrument still requires hardware adapters, interlocks, reference measurements on the target
instrument, recovery tests, supervised trials, and instrument-expert approval. Every skill in the
public catalog carries `hardware_qualification_required` set to `true`, without exception.

## Evaluation

### Research Questions

- **RQ1.** Can the model generate executable skills from instrument sources?
- **RQ2.** Does simulator evidence *causally* improve repair, beyond retrying generation?
- **RQ3.** Can independent gates prevent invalid promotion, including self-approved mistakes?
- **RQ4.** Does the method operate across distinct instrument families?
- **RQ5.** Can it detect drift and stage non-regressive evolution?

### Instrument Families and Cohorts

| Cohort | Instruments | Role |
|---|---|---|
| Reference | 2D area-detector powder XRD (Bluesky/`ophyd.sim` execution, pyFAI-based verification) | Reference implementation and verifier metrology; **not** generalization data |
| Development | Keithley 2450-style SMU (PyVISA-sim); eight diagnostic instruments across liquid handling, battery cycling, additive manufacturing, and quantum transport | Admission proof; method development and mechanism evidence, excluded from the confirmatory claim |
| Confirmatory | Six instruments in three families held out of method development: absorbance and fluorescence plate reads (optical measurement), pump dose and dual-pump blending (calibrated delivery), isothermal hold and thermal cycling (thermal control) | Frozen paired causal study |
| Replication | Ten fresh generations per confirmatory instrument plus the external OpenFlexure microscope | Variance and breadth under the frozen protocol |
| External integration | [OpenFlexure microscope server](https://gitlab.com/openflexure/openflexure-microscope-server) (pinned revision `d26b93e`), run as a separate GPL-3.0 process via its public API | Externally authored simulator; breadth and evolution stress test |
| Preflight suitability round | OctoPrint virtual 3D printer, PyMoDAQ mock spectrometer, sinstruments pressure controller | Preregistered preflight round that exercised the deterministic fixture-suitability gate (see the cross-family results) |
| Persistent cross-family panel | North Robotics pipette calibration (liquid handling), HELAO Gamry cyclic voltammetry (electrochemistry), CLSLab light spectrometer (optical spectroscopy) | One binding session per externally authored family under the frozen persistent method, with persistent causal repair and drift evolution; no failing family may be replaced |

**Table 2.** Cohorts and their evidentiary roles. Development evidence never counts toward the
confirmatory claim. Both external rounds were preregistered, with families, thresholds, and
per-family pass requirements fixed before binding exposure to their simulators.

### Causal Repair Design

Each paired unit starts from the *same* parent draft and model configuration and runs two arms.
One receives truthful, structured simulator evidence (execution trace, failed checks, telemetry),
the other receives no feedback. Success requires an actual code change, verification on the
visible conditions, verification on the locked conditions, and no regression on previously
working behavior; a repair meeting all four is called **non-regressive**. The principal mechanism
analysis uses 18 non-overlapping paired units, drawn from the six-instrument confirmatory panel
(6 units), the eight-instrument diagnostic panel (8), and the OpenFlexure development trials (4),
and applies an exact one-sided McNemar test on the discordant pairs
([synthesis artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/artifacts/generated/accumulated-causal-evidence/summary.json)).
Because these units were collected as the protocol evolved, the pooled result is evidence about the
*feedback-repair mechanism*, not a single fixed-protocol success rate.

### Verifier Metrology

Every verifier is exercised against labeled valid and invalid batteries with per-class
false-admission and false-rejection reporting. Physical quantities are computed independently of
the simulator's own internals. The microscopy verifier, for example, never reads the simulator's
focus score, and instead checks stage position, frame integrity, and two separately implemented
image-sharpness calculations. Batteries include an always-valid
adversary that claims every measurement is good, and adversarial cases that execute successfully
but are physically invalid. Fixed-index samples of raw records are inspected by hand and
countersigned.

### Reproducibility

Sources, simulator revisions, prompts, budgets, provider route, seeds, and thresholds are frozen
and recorded per run. The persistent method was frozen before binding exposure at digest
`c1a28d…7267`. The three cross-family instruments, upstream revisions, source bundles, prompts,
control dialect, search budgets, context policy, thresholds, provider allowlist, and promotion
rules are hash-bound, and no failing family may be replaced. The **provider allowlist** names the
model-provider routes permitted for a binding run, which were DeepInfra and GMICloud for this
panel. **Transport provenance** is the route
each call actually used. A result whose transport provenance falls outside the allowlist cannot
be promoted.

Evidence is tiered. A **binding** run executes under the frozen method digest and counts toward a
preregistered claim. An **engineering** run is exploratory, used to build and exercise the
machinery, and never counts. **Diagnostic** evidence comes from method development and is likewise
excluded from confirmatory claims. The tiers are kept separate throughout this report, and 51
invalidated runs are retained under
[`artifacts/invalidated/`](https://github.com/Dynamical-Systems-Research/proprio/tree/c2cd6be/artifacts/invalidated)
for audit rather than deleted.

Canonical records are byte-deterministic, and captured model interactions are stored as cassettes
so CI replays the full admission chain offline, while fresh generation remains a separate release
gate. The locked test suite contains 292 tests and asserts
the *failed* research claims, including the external-family rejection, the reviewer-panel mismatch,
and the rejected evolution proposals, so they cannot silently become passes. The evidence manifest binds
177 release artifacts by hash.

## Results

### From Documentation to Executable Operation

The [70-generation replication
study](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/cassettes/replication-dsv4/summary.json)
ran ten independent generations per instrument with unique seeds, temperature 0.7, and top-p 0.95.
Three rates summarize it.

- Initial drafts that executed, 68/70 (97.1%; Wilson 95% CI 90.2–99.2%).
- Initial measurements that were physically valid, 61/70 (87.1%).
- Final candidates that passed every check, 64/70 (91.4%; Wilson 95% CI 82.5–96.0%).

The six confirmatory instruments passed verification for **60/60** candidates. The externally authored
OpenFlexure microscope marks the limit of that result. All 10 drafts executed, while only
**4/10** final candidates passed the locked physical sweep against the frozen ≥8/10 threshold.
The breadth gate therefore failed: all six candidates that missed verification were rejected, and
no microscope skill was admitted. In the separate development cohort, DSV4 also compiled a correct Keithley
2450-style current measurement from driver and fixture documents
([admission artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/skill-admission/summary.json)).

The persistent cross-family panel extends this to externally authored control interfaces. Under the
frozen method, the model produced an executable, physically verified, locked-condition skill for
each of the three external families, with independent gate decisions of `ADMIT`/`PASS`
([panel summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/summary.json)).
Those sessions are reported in full below.

### Verified Feedback Drives Repair

Across the 18 paired units, truthful feedback produced **14/18** non-regressive repairs; the
identical drafts with no feedback produced **0/18** (exact one-sided paired p = 0.000061). Every
cohort showed positive uplift, with 6/6 on the confirmatory panel (bootstrap 95% uplift interval
[1.0,&nbsp;1.0]), 5/8 on the diagnostic panel, and 3/4 on the OpenFlexure development trials.

![Non-regressive repairs with and without verified simulator feedback](assets/verified-feedback-repair.png)

**Figure 2.** Non-regressive repairs with verified simulator feedback versus none, from the same
starting drafts and search budget. A repair counts only if the edited skill reaches verdict
`ADMIT` with no historical regression; the OpenFlexure development trials are scored on the trial's
verification outcome, which includes the locked sweep. Pooled across cohorts, verified feedback
produced 14 of 18 non-regressive repairs and blind retrying produced none
([synthesis artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/artifacts/generated/accumulated-causal-evidence/summary.json)).

A representative repair appears verbatim in the [calibrated-pump-dose
cassette](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/cassettes/confirmatory-dsv4/calibrated-pump-dose/repair-truthful.json).
The visible-condition gate failed only `speed-support` (`maximum_rpm: 75.0`, `observed_rpm:
[100.0, 100.0]`). The model's logged diagnosis was *"Reduced prime and delivery speed from 100 rpm to
75 rpm to match the changed pump's maximum supported speed of 75.0 rpm … Calibration (0.050),
target volume (10.0 mL), halt, and return shape preserved."* The edited skill then passed the
changed condition, the historical nominal scenario, and 50 locked conditions. The no-feedback
arm, given the same failing draft and the same budget, did not repair it.

The persistent cross-family panel showed the same signature in its own paired arms. Verified
simulator feedback produced a verified repair in all three external families
([North](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/north-pipette-calibration/session-000/causal/summary.json),
[HELAO](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/helao-gamry-cv/session-000/causal/summary.json),
[CLSLab](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/clslab-light-spectrometer/session-000/causal/summary.json)).
The no-feedback control, which still sees its own submission outcomes but not the registered
evidence, passed verification only for North. These per-family arms are reported alongside, not folded into,
the 18-unit analysis.

### Independent Gates Prevent Invalid Promotion

The clearest single case is the Keithley 2450 development study. DSV4 drafted two skills from
supplied documentation. One came from the current fixture sheet (1 kΩ load, 1 V source, 2 mA
compliance, 10 mA range) and one from a plausible stale worksheet (100 kΩ load, 200 µA compliance,
100 µA range). It **self-judged both `ACCEPT`**
([captured completions](https://github.com/Dynamical-Systems-Research/proprio/tree/main/cassettes/skill-admission)).
Proprio executed both against a PyVISA-sim instrument and checked the measured current against the
1 kΩ circuit law and the active range/compliance contract. The correct skill passed all nine
checks and was admitted; the self-accepted stale skill was rejected on the `compliance-contract`
and `range-contract` checks (observed ≈0.2 mA against a required minimum ≈1.1 mA). The rejected
draft exists only as evidence. It never entered the catalog.

The gates themselves were then measured.

- **XRD reference verifier.** 5/5 injected execution-fault classes detected (a dropped frame is
  labeled `degraded`); 0/300 false rejections on valid calibrant controls; 0 observed
  false acceptances across nine invalid classes × 300 cases; an always-valid adversary rejected in
  2,700/2,700 cases. One measured weakness is reported. The dedicated sample-displacement check
  missed direct attribution in 19/300 cases (AUROC 0.943) although adjacent shift/indexing checks
  still rejected every affected measurement
  ([metrology record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/metrology/report.md)).
- **Confirmatory-family verifiers.** 9,000 labeled simulations (1,800 valid, 7,200 invalid across
  wrong order, unsafe setting, wrong physical target, and omitted cleanup) with zero false
  admissions and zero false rejections; 30 fixed-index raw records hand-inspected and
  countersigned
  ([summary](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/artifacts/evidence/confirmatory-metrology/summary.json)).
- **OpenFlexure verifier.** 2,700 labeled cases over eight invalid classes; zero invalid
  measurements accepted, one valid measurement in 300 falsely rejected. The two image-sharpness
  checks (frequency-domain and Laplacian) agreed on 299/300 valid frames; because they share the
  same exported frame they are not statistically independent, and that residual correlation is
  reported rather than hidden
  ([summary](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/artifacts/evidence/microscopy/locked/metrology/summary.json)).
- **Adversarial composition.** A trajectory that executes successfully but contains a saturated
  detector frame passes procedural verification and fails validity, so execution success cannot
  substitute for physical validity
  ([composition artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/composition/summary.json)).
- **Cross-family verifiers.** 4,200 labeled simulations across the North,
  HELAO Gamry, and CLSLab fixtures (900 valid and 3,300 invalid cases over 11 failure classes),
  with zero false admissions and 3/900 false rejections, all on the North fixture
  ([metrology records](https://github.com/Dynamical-Systems-Research/proprio/tree/c2cd6be/artifacts/evidence/generalization-v0.3/metrology)).
- **Provenance gate.** A CLSLab engineering session with a staged evolution proposal and a passing
  locked sweep was reduced to `HOLD` because part of its transport ran on a provider outside the
  frozen allowlist
  ([session record](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/cassettes/generalization-v0.3-smoke-final/clslab-light-spectrometer/session-003/summary.json)).
  The drafting model could not override the decision.

Model judgment was measured under the same discipline. The DSV4 review prompt, frozen after
calibration, scored 100% critical-defect recall with zero false alarms on 24 unseen review cases
(12 critical-defect mutations, 6 valid controls, and 6 unavailable-evidence cases). The
independent Qwen 3.7 Plus reviewer passed 56/56 calibration cases and 42/42 cases on the six
confirmatory instruments, and matched 47/49 pre-fixed labels on the full panel. Fresh replay
showed both disagreements were wrong *fixture labels* that the reviewer had correctly rejected;
the panel verdict is preserved as `FAIL` rather than recalculated
([review record](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/cassettes/independent-review/summary.json)).
Across every battery, no model, whether drafter or reviewer, overrode a failed deterministic check.

### Evidence Across Instrument Families

| Family (instruments) | Draft executes | Visible verification | Held-out verification | Causal repair | Drift detected | Evolution | Fail-closed admission |
|---|---|---|---|---|---|---|---|
| Powder XRD (reference) | ✓ (reference) | ✓ | — | — | — | — | ✓ (saturated-frame case) |
| Electrical measurement (Keithley SMU) | ✓ | ✓ | — | — | — | — | ✓ (stale draft rejected) |
| Optical measurement (2) | 19/20 | 20/20 | 20/20 | 2/2 | — | — | ✓ |
| Calibrated delivery (2) | 19/20 | 20/20 | 20/20 | 2/2 | — | — | ✓ |
| Thermal control (2) | 20/20 | 20/20 | 20/20 | 2/2 | — | — | ✓ |
| Liquid handling (2, diagnostic) | ✓† | ✓† | — | 2/2 | 2/2 | 2/2 staged | ✓ |
| Battery cycling (2, diagnostic) | ✓† | ✓† | — | 1/2 | 2/2 | 2/2 staged | ✓ |
| Additive manufacturing (2, diagnostic) | ✓† | ✓† | — | 0/2 | 2/2 | 2/2 staged | ✓ |
| Quantum transport (2, diagnostic) | ✓† | ✓† | — | 2/2 | 2/2 | 2/2 staged | ✓ |
| Microscopy (OpenFlexure, external) | 10/10 | 6/10 | 4/10 (**FAIL** vs ≥8/10) | 3/4 (dev. trials) | 1/1 | 0/1 (**rejected**) | ✓ (nothing admitted) |
| 3D printing (OctoPrint, held-out) | — | — | — | — | — | — | ✓ (`HOLD` at preflight) |
| Spectral measurement (PyMoDAQ, held-out) | — | — | — | — | — | — | ✓ (`HOLD` at preflight) |
| Pressure control (sinstruments, held-out) | — | — | — | — | — | — | ✓ (`HOLD` at preflight) |
| Liquid handling (North pipette calibration, external) | ✓ | ✓ | ✓ | truthful 1/1; no feedback 1/1 | 1/1 | 1/1 staged | ✓ (0 invalid promotions) |
| Electrochemistry (HELAO Gamry CV, external) | ✓ | ✓ | ✓ | truthful 1/1; no feedback 0/1 | 1/1 | 1/1 staged | ✓ (0 invalid promotions) |
| Optical spectroscopy (CLSLab light spectrometer, external) | ✓ | ✓ | ✓ | truthful 1/1; no feedback 0/1 | 1/1 | 1/1 staged | ✓ (0 invalid promotions) |

**Table 3.** Cross-family claim matrix from committed evidence. `n/m` counts passes over attempts;
✓ marks a capability demonstrated in the linked records, while an em dash marks a capability not exercised.
Confirmatory rows report the ten-generation replication; their causal-repair column reports the
paired study. † Diagnostic-panel parents passed verification on visible and historical conditions
after an initially hidden executor-grammar mismatch was disclosed and fixed (drafting was 1/8
executable before the fix), which is why the panel is diagnostic evidence rather than part of the
confirmatory claim
([archive](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/cassettes/dsv4-history-repair/summary.json));
their 50-condition locked sweeps ran on the evolution proposals described below. The three external
rows report one binding session per family under the same frozen persistent method
([panel summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/summary.json)).

Simulator suitability is checked by a deterministic gate before any model call. An earlier preflight
round was preregistered against three externally authored simulators whose pinned revisions turned
out unable to execute their complete registered physical and drift contracts (OctoPrint exposes no
declared temperature maxima; the pinned PyMoDAQ runtime does not expose the selected mock
spectrometer; the sinstruments emulator rejects reset/range/vent commands and its pressure
readings ignore setpoints). Proprio returned `HOLD` for all three families, spent **zero** model
calls, and did not swap in easier families
([preflight record](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/artifacts/evidence/heldout-generalization/preflight/summary.json)).

The persistent cross-family panel binds three externally authored control interfaces that passed the
same deterministic preflight, covering North Robotics pipette calibration, HELAO Gamry cyclic
voltammetry, and the CLSLab light spectrometer. Each family produced an executable skill that
passed visible and held-out verification. Starting from a separate self-accepted parent that failed
the registered calibration change, truthful simulator evidence produced a verified repair in all
three families, while the no-feedback control passed verification in one. Every admitted parent then
failed its registered drift condition, and all three persistent evolution trajectories produced
proposals that passed the changed condition, historical replay, and held-out verification. No
trajectory regressed historical behavior, and no invalid candidate was promoted
([panel summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/summary.json)).

This panel establishes cross-family replication of the complete simulation ladder for these three
screened external families. Each family contributes one binding session, showing that the frozen
method transferred across the tested control interfaces without estimating a repeated-generation
success rate or a statistical feedback effect. The simulators were screened for suitability before
model use, so the result does not claim untouched first exposure. The earlier episodic records
remain immutable as the baseline
([stop record](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/artifacts/evidence/generalization-v0.3/run-stop.json)).

### Evolution After Drift

After a versioned simulator change broke all eight history-safe diagnostic parents, DSV4 inspected
the drift evidence and produced evolution proposals for all eight; each passed the changed
condition, full historical replay, and 50 locked conditions. Each was **staged**, with its parent
left immutable, its rollback hash recorded, and `hardware_gate_required` set to `true`
([evolution record](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/cassettes/dsv4-evolution/summary.json)).
The external counterexample is retained alongside it. On the OpenFlexure family, the evolution
attempt exhausted its turn budget with a candidate that still failed the Laplacian focus threshold
and regressed the nominal FFT check; only 6/10 locked drift offsets passed, the independent
reviewer rejected it, and the parent skill was left untouched
([cassette](https://github.com/Dynamical-Systems-Research/proprio/tree/c2cd6be/cassettes/microscopy-evolution)).
A later, separately versioned GPT-5.6 Luna release lineage closed the complete OpenFlexure loop
under a bounded persistent-context protocol. It began from the instrument source, preserved an
initial physical rejection and repaired parent admission, detected registered drift, and submitted
a plausible same-sign residual correction that the independent gate rejected. The same context
used those readbacks to correct an evolving copy. That proposal passed changed `1/1`, historical
`3/3`, and locked `5/5` before the gate returned `STAGED`; the admitted parent remained immutable
([release cassette](https://github.com/Dynamical-Systems-Research/proprio/tree/main/cassettes/openflexure-full-loop/session-001)).
This is one mechanism-demonstration lineage, not a re-estimate of the earlier DSV4 population gate.
Verified in simulation. Hardware validation remains separate.

The persistent cross-family panel held to the same discipline. Registered drift invalidated the
admitted parent in all three families, and the model entered a persistent evolution trajectory with
the drift record, source bundle, current skill, and complete repair ledger in context. North and
HELAO each required two submitted repairs before the verifier admitted a proposal, while CLSLab
passed on its first. The two-repair cases show the persistent context earning its keep. On North,
drift dropped the pipette to 40% of its commanded delivery; the model's first proposal diagnosed the
convergence problem correctly but used a `break` statement the bounded executor forbids, and the
verifier rejected it. With that rejection and its own prior diagnosis still in context, the second
proposal kept the physical fix and restructured only the control flow the check had flagged. Every
final proposal passed the changed condition, replayed the historical acquisition conditions without
regression, passed held-out verification, and was staged with `hardware_qualification_required` set
to `true`, leaving the parent skills immutable
([North](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/north-pipette-calibration/session-000/evolution/summary.json),
[HELAO](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/helao-gamry-cv/session-000/evolution/summary.json),
[CLSLab](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/clslab-light-spectrometer/session-000/evolution/summary.json)).

### Cost and Engineering Burden

The full 70-generation replication used 626 model calls and 2,527,902 tokens under fixed turn
budgets (2–12 model turns per episode), modest by current inference standards. The
eight-instrument evolution battery used 84 calls / 473k tokens (≈$0.03 at the recorded route
pricing); building the eight verified history parents took 53 calls / 224k tokens; the failed
microscopy evolution burned 21 calls / 308k tokens before rejecting itself. Additional compute
paid off when the evidence pointed at a discrete cause (a speed limit, a stale range). It hit
diminishing returns when the physical contract could not be satisfied within budget. Four of the
six failed OpenFlexure candidates ended at the turn limit without submitting, and the other two
passed visible repair but failed hidden starting positions.

The persistent cross-family panel evaluated 30 candidate variants and captured 166 model
responses, of which 165 completed successfully. The run consumed 2,769,382 tokens at a recorded
cost of $0.262. The truthful trajectories reached their first verified repair in six model calls
for North, six for HELAO, and three for CLSLab. Deterministic request-side compaction activated in
three trajectories, two duplicate candidate hashes were rejected, and one transport error was
recorded and recovered within the frozen retry policy. These totals describe one binding session
per family rather than an expected acquisition cost
([panel summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/summary.json)).

The unavoidable human cost is verifier construction, reported as measured line counts rather than
estimates
([burden manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/c2cd6be/artifacts/evidence/engineering-burden/summary.json)).

| Instrument family | Simulator/adapter LOC | Verifier LOC | Source-bundle LOC | Physical checks | Invalid classes |
|---|---|---|---|---|---|
| Optical measurement (2) | 130 | 107 | 30 | 7 each | 4 |
| Calibrated delivery (2) | 113 | 80 | 24 | 5 / 6 | 4 |
| Thermal control (2) | 100 | 50 | 24 | 7 each | 4 |
| OpenFlexure microscopy (external) | 333 (adapter) | 162 | 32 | 10 | 8 |

**Table 4.** Measured engineering burden by instrument family, in nonblank lines of code, with
physical checks and labeled invalid classes per family.

Reusing the externally authored OpenFlexure simulator avoided writing a digital twin but still
required the 333-line API adapter, a 162-line verifier, and a 185-line metrology harness.
Person-hours are not reported because prospective labor logging was not active.

### What the Traces Retain

Because admission is external, the agent's search does not have to be discarded once a skill
passes. Every attempt in a run is written as canonical, byte-deterministic JSON: the full message
history, the model's reasoning and tool calls, the verifier record, and a structured repair ledger
that records, for each candidate, its content hash, the checks that failed, the model's diagnosis,
the evidence it cited, the change it made, and the outcome. The cross-family panel alone retained
56 model responses and 87 state checkpoints, and 51 excluded runs are kept under version control
for audit rather than deleted.

These records are legible. On HELAO's cyclic voltammetry, the ledger shows the model finding that
`lower_v2 = 0.5 * lower_v / frame_min` returned a positive value when both operands were negative,
so the third potential cycle swept only positive potentials, and correcting the sign. On the CLSLab
spectrometer, it found that the detector's overrange limit was read once and cached, so a drifted
detector never triggered a gain reduction, and moved the limit query inside the measurement loop.
Each step is a diagnosis tied to a specific failed check and a specific edit.

A verified skill is the distilled result of that search, packaged as a versioned artifact whose
control code, source bundle, and verifier are bound by hash to the evidence that admitted it. The
same records are a natural substrate for reusable skill libraries and for training signal derived
from verified operation, though the released method trains nothing and treats that as future work.

## Discussion

The simulator plays two roles in this method. It gives the agent somewhere to learn, and it gives
the verifier controlled conditions under which to test what the agent learned.

[MatteriX](https://arxiv.org/html/2601.13232v1) shows how far laboratory twins can carry this idea
by combining robotic manipulation, device models, and approximate chemical-process semantics.
NVIDIA's [4D Digital Twins](https://research.nvidia.com/labs/amri/projects/4DDT/2026/) agenda extends
the substrate toward real-to-sim-to-real development. These systems make interaction cheaper and
failure easier to inspect. They do not remove the gap between simulation and a specific physical
instrument.

Proprio stops at that boundary. A simulation-verified skill is evidence for pre-deployment review.
It still has to pass the interlocks, calibration checks, tolerances, and failure procedures of the
hardware it will operate.

### Where Proprio Sits

Proprio sits between scientific intent and instrument control. An experiment-selection or judgment
policy may decide what evidence to acquire, while Bluesky, SiLA, PyLabRobot, HELAO, or a vendor
driver supplies the interface through which an operation is executed. Proprio verifies the
procedural artifact that connects those two layers. It does not select the scientific objective,
replace the control framework, or authorize hardware deployment. Its output is a simulation-verified
skill package that remains subject to the laboratory's hardware commissioning process.

### Verification as the Scaling Axis

No model weights change anywhere in this method. All additional compute is spent at inference
time on drafting, executing, diagnosing, repairing, and replaying. The verifier converts those
extra samples into verified procedural capability rather than more generated text. The paired
result above is the mechanism at work. Given the same drafts and budget, evidence-grounded
search repaired 14/18 units and blind regeneration repaired none. The practical corollary for
laboratories is that faster simulators and richer physical contracts directly increase how much
capability can be explored and trusted before an instrument is ever touched.

### Implications for Composable Laboratories

Instrument standards make capabilities portable, and simulators make their acquisition cheap.
Independent verification is what makes a skill admissible, and a hash-bound catalog is what makes
it reusable across agents and workflows. The
[current catalog](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json)
holds 12 installable packages: one XRD reference, ten simulation-qualified procedures, and one
staged OpenFlexure evolution proposal. The flat
[`skills/`](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills) directory is the
current source of truth; each package is bound to its compact verification record and still
requires hardware validation.
A laboratory adding an instrument follows the documented recipe by connecting the public API,
providing a simulator with explicit reset and failure behavior, writing the physical contract,
building the labeled validity battery *before* asking a model to generate anything, and freezing
thresholds in advance.

### Scope and Limitations

All verification reported here is simulation-only, and simulator-to-reality correspondence is
imperfect by construction. Each family's verifier requires instrument-specific engineering
(see Verification Cost and Engineering Burden). Model generation is stochastic, so acquisition and evolution are demonstrated
capabilities with measured variance, not guarantees; OpenFlexure's 4/10 and the rejected
evolution proposals remain the canonical counterexamples. The pooled causal analysis spans protocol
generations, so it establishes the feedback mechanism rather than a single frozen-protocol rate.
The persistent panel replicates acquisition, held-out verification, causal repair, drift detection,
and non-regressive evolution across three screened external families. Because the study contains one
binding session per family and uses simulators screened before model exposure, it neither estimates
stochastic success rates nor constitutes an untouched-family test. Real-hardware validation remains
a separate gate, and nothing in this report substitutes for it.

## Conclusion

The result gives a practical way to spend test-time compute on instrument integration. The model
reads, executes, fails, and revises for as long as the simulator is informative, and the verifier
controls which parts of that experience become reusable capability. Once operating an instrument is
delegable and auditable in this way, the scientist's attention can move up, from whether the agent
can drive the instrument to what the experiment should ask.

That is the connection to the larger Dynamical thesis. Models can propose more experiments than labs
can run, and the lab is where those proposals meet physical reality. If agents are going to act
inside that loop, their operating procedures need to become inspectable, replayable, and improvable
from the evidence the instrument returns.

---

## Sources

- [On the Need for Autonomous Science Instruments: A Call to Action](https://chemrxiv.org/doi/full/10.26434/chemrxiv.10001836/v1) (ChemRxiv, 2026)
- [Towards a composable, modular laboratory ecosystem for autonomous materials research and development](https://www.nist.gov/publications/towards-composable-modular-laboratory-ecosystem-autonomous-materials-research-and) (Joress et al., *Matter*, 2026)
- [An agentic artificially intelligent X-ray scientist](https://www.nature.com/articles/s42256-026-01261-5) (Chen et al., *Nature Machine Intelligence*, 2026)
- [Operating advanced scientific instruments with AI agents that learn on the job](https://www.nature.com/articles/s41524-026-02005-0) (Vriza et al., *npj Computational Materials*, 2026)
- [ASPIRE: Agentic Skill Programming through Iterative Robot Exploration](https://arxiv.org/abs/2607.00272) (NVIDIA, 2026)
- [4D Digital Twins: Real-to-Sim-to-Real for Physical AI](https://research.nvidia.com/labs/amri/projects/4DDT/2026/) (NVIDIA, 2026)
- [MatteriX: Towards a Digital Twin for Robotics-Assisted Chemistry Lab Automation](https://arxiv.org/abs/2601.13232) (Darvish et al., arXiv, 2026)
- [SkillOpt: Executive Strategy for Self-Evolving Agent Skills](https://arxiv.org/abs/2605.23904) (Microsoft Research, 2026)
- [Voyager: An Open-Ended Embodied Agent with Large Language Models](https://arxiv.org/abs/2305.16291) (Wang et al., 2023)
- [GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](https://arxiv.org/abs/2507.19457) (Agrawal et al., 2025)
- [Library Drift: Diagnosing and Fixing a Silent Failure Mode in Self-Evolving LLM Skill Libraries](https://arxiv.org/abs/2605.19576) (Zhang et al., 2026)
- [Hermes Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) (Nous Research)

*Evidence artifacts cited inline are committed to
[`Dynamical-Systems-Research/proprio`](https://github.com/Dynamical-Systems-Research/proprio) and
hash-bound in the [evidence manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/manifest.json).*
