# Proprio: Simulator-Verified Skill Acquisition for Scientific Instruments

**Dynamical Systems Research — Technical Report, July 2026**

[Code](https://github.com/Dynamical-Systems-Research/proprio) ·
[Skill catalog](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json) ·
[Example skill: calibrated pump dose](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/simulated/calibrated-pump-dose) ·
[Example skill: Keithley 2450](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/keithley-2450) ·
[Demo video — link pending]

*Every number in this report is recomputed from artifacts committed to `main` at
[`07868d8`](https://github.com/Dynamical-Systems-Research/proprio/commit/07868d8). Each result links
to the JSON or markdown record it comes from.*

## Abstract

Scientific agents increasingly need to operate instruments — run a scan, deliver a reagent, hold a
temperature — rather than only reason about datasets those instruments have already produced.
Autonomous-laboratory infrastructure supplies open control interfaces and increasingly capable
simulation, and recent agent demonstrations show that models can operate advanced instruments and
accumulate reusable procedural knowledge; the unresolved question is how an agent-generated
operating procedure earns admission into a laboratory's trusted capability set. Proprio is an
open-source method that converts instrument documentation into executable operating skills through
bounded inference-time search against an instrument simulator, then subjects every candidate to
independent execution and physics checks, a one-shot locked validation on conditions hidden during
development, and fail-closed admission that the generating model cannot override. On the committed
evidence, truthful simulator feedback produced 14 of 18 paired non-regressive skill repairs where
the identical drafts produced 0 of 18 without feedback (exact one-sided paired p = 0.000061); ten
independent generations per instrument qualified 60/60 candidates across six simulated instruments
in three families, while an external microscopy family qualified only 4/10 and was recorded as a
failed breadth gate; and the independent gates rejected every invalid candidate, including a
plausible draft that the drafting model had itself approved. The implication is that fast
simulation and independent verification can turn test-time compute into qualified instrument
capability in simulation — while qualification on real hardware remains a separate, explicitly
unfinished gate.

## 1. Scientific agents need qualified instrument capabilities

### 1.1 Autonomous science is constrained by its instrument interface

The case made in [*On the Need for Autonomous Science
Instruments*](https://chemrxiv.org/doi/10.26434/chemrxiv.10001836) is that scalable autonomous
laboratories require instruments with open, software-defined control, designed for automation and
modular composition. That argument has largely been won at the interface level: a growing share of
laboratory hardware is reachable through documented APIs, drivers, and orchestration frameworks.

An open API, however, only makes an instrument *accessible* to an agent. It does not establish
that an operating procedure the agent wrote is correct — that the ramp rate respects the hardware,
that the measurement it produces is physically meaningful, or that a revision made next month
still handles the conditions that worked last month. The missing object between "the agent can
call the instrument" and "the laboratory can rely on the result" is a portable, inspectable,
independently qualified **instrument skill**: an operating procedure packaged with its evidence.

### 1.2 A composable laboratory also needs composable procedural capability

NIST's vision of a [composable, modular laboratory
ecosystem](https://www.nist.gov/publications/towards-composable-modular-laboratory-ecosystem-autonomous-materials-research-and)
argues that community standards and off-the-shelf components should replace bespoke integration
across vendor interfaces. Substrates for that ecosystem already exist:
[Bluesky](https://blueskyproject.io) and [Ophyd](https://github.com/bluesky/ophyd) for experiment
orchestration and hardware abstraction, [SiLA](https://sila-standard.com) for standardized device
communication, [PyLabRobot](https://github.com/PyLabRobot/pylabrobot) for liquid-handling
hardware, [HELAO](https://github.com/High-Throughput-Experimentation) for hierarchical laboratory
orchestration, and digital twins for exercising all of the above without consuming samples.

Proprio is not another orchestration system or instrument protocol. It is a capability and
qualification layer that sits above these substrates: it consumes their documentation and
simulators as inputs and emits qualified skills — with provenance and test evidence — that
orchestration layers can then call.

### 1.3 The generation–verification gap

Recent agent systems demonstrate that instrument operation by language-model agents is feasible.
The [agentic X-ray scientist](https://www.nature.com/articles/s42256-026-01261-5) of Chen et al.
practiced in a virtual six-circle beamline before supervised real deployment, adapted to an
approximately 1.22° motor offset, and reused that correction when locating a second reflection —
while explicitly treating the limited real-beamline trials as proof-of-concept rather than
statistical evidence. The ["learn on the job"
agents](https://www.nature.com/articles/s41524-026-02005-0) of Vriza et al. operate real X-ray
nanoprobe and robotic thin-film workflows, storing human feedback as reusable memory with human
approval before execution.

These systems establish that agents can *generate* and *adapt* operating behavior. Proprio asks
the complementary question: can an agent acquire and repair procedural capability from instrument
sources alone, under a protocol in which it is structurally unable to approve its own mistakes —
and can the resulting evidence be replayed, audited, and held to preregistered thresholds?

### 1.4 Contributions

- A reusable **source → skill → simulation → qualification → admission** method, released as
  open-source code with schemas, simulators, verifiers, and a hash-bound skill catalog.
- A **causal evaluation protocol** that separates simulator-grounded repair from repeated
  generation, using paired interventions from identical drafts.
- An **open evidence and skill format** exercised across scientific-instrument families —
  including drift-triggered evolution and fail-closed promotion — with every failure preserved in
  the public record.

## 2. Related systems and the remaining seam

Organized by function rather than chronology; each of these systems contributes something Proprio
depends on or deliberately does not rebuild.

### 2.1 Instrument and laboratory infrastructure

Bluesky/Ophyd, SiLA, PyLabRobot, HELAO, and the [Acceleration
Consortium](https://acceleration.utoronto.ca) ecosystem provide interoperability, execution,
orchestration, and data flow. NIST's modular-laboratory architecture provides the standards
framing. These layers answer *how to command an instrument and move its data*; they are the
substrate a qualified skill executes against.

### 2.2 Virtual preparation and digital twins

[MatteriX](https://arxiv.org/abs/2601.13232) supplies multiscale chemistry-laboratory simulation
spanning robotic manipulation, liquids, powders, devices, heat transfer, and reaction semantics.
NVIDIA's [4D Digital Twins](https://research.nvidia.com/labs/amri/projects/4DDT/2026/) agenda
frames real-to-sim-to-real physical AI around sim-ready representations and physically grounded
training. These provide the environments in which capability can be exercised cheaply — exactly
the property Proprio's search loop consumes. (Proprio ships an optional MatteriX adapter that
currently reports itself honestly
[`unavailable`](https://github.com/Dynamical-Systems-Research/proprio/blob/main/docs/matterix-adapter.md)
rather than claiming an untested pass.)

### 2.3 Procedural skill acquisition and improvement

[Hermes `/learn`](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills#learning-a-skill-from-sources-learn)
authors reusable skills from documentation, directories, URLs, or prior workflows — Proprio adopts
this learn-from-sources interface. [SkillOpt](https://github.com/microsoft/SkillOpt) optimizes
textual skills through trajectory-driven edits and held-out validation.
[ASPIRE](https://research.nvidia.com/labs/gear/aspire/) inspects robotic execution traces, repairs
control programs, validates by re-execution, and accumulates reusable skills — Proprio follows its
debug-versus-locked-validation discipline. [Voyager](https://arxiv.org/abs/2305.16291) introduced
the executable skill library with iterative environment feedback. On the inference side, [Snell et
al.](https://arxiv.org/abs/2408.03314) show that adaptive search and verifier-guided selection let
additional inference-time compute substitute for model scale — the result Proprio applies to
procedural capability rather than answer selection.

### 2.4 Where the seam remains

| System class | Generates procedures | Executes in an environment | Learns from feedback | Independent physical admission | Historical replay before evolution |
|---|---|---|---|---|---|
| Instrument-control frameworks | No | Yes | No | Limited | No |
| Documentation-to-skill systems | Yes | Sometimes | Sometimes | No instrument-specific gate | Limited |
| Agentic instrument demonstrations | Yes | Yes | Yes | Workflow-specific | Varies |
| Robotics skill-discovery systems | Yes | Yes | Yes | Task-success validation | Varies |
| **Proprio** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

**Table 1.** Positioning against adjacent systems. No single ingredient is new; the contribution
is the composition, and specifically where the admission authority sits: in instrument-specific
execution and physics checks that the generating model cannot override.

## 3. Proprio

### 3.1 Inputs and output

| Object | Definition |
|---|---|
| Instrument sources | Manuals, API/driver documentation, and operating limits shown to the model. |
| Controller contract | The permitted commands and observable state — nothing else is callable. |
| Simulator | Executable instrument or process behavior, with explicit reset and failure semantics. |
| Physical contract | Independent, machine-checkable requirements for a valid operation and measurement (e.g., delivered volume within 0.10 mL at certified 0.050 mL/rev calibration). |
| Skill package | `SKILL.md` operating procedure, bounded control code, provenance hashes, and a link to the qualification record, hash-bound in [`catalog.json`](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json). |

The v0.1 release used DeepSeek V4 Flash (DSV4, resolved `deepseek/deepseek-v4-flash-20260423`, one
pinned provider route) as the drafting and repair model and Qwen 3.7 Plus as a separately prompted
independent reviewer. The interface is model-agnostic; every reported result stays tied to the
recorded model, route, prompts, and sampling settings that produced it.

### 3.2 Scientist-facing workflow

1. **Learn** a skill from instrument sources.
2. **Qualify** it independently in simulation.
3. **Admit** the passing skill into the catalog.
4. **Monitor** execution evidence for drift.
5. **Stage** a verified evolution proposal when drift breaks the admitted skill.

The governing principle:

> The agent drives discovery, execution, diagnosis, repair, and evolution; it cannot authorize
> promotion.

![The Proprio loop: model-driven skill development under external verification](assets/self-directed-skill-acquisition.png)

**Figure 1.** The complete loop. The model reads sources and drafts procedures (left), interacts
with the simulator and repairs from execution evidence (center), and every candidate passes
through independent execution and physical qualification, locked validation, and fail-closed
admission (right). Drift detection re-enters the loop as a staged evolution proposal. A separate
hardware gate stands between everything shown here and a real instrument.

### 3.3 Inference-time skill search

Skill acquisition is organized as verifier-guided test-time compute. The model produces multiple
independent drafts (four, in the current frozen configuration) in a bounded, executable control
dialect — finite loops, observation-conditioned branches, explicit call limits, no exception
swallowing, no access to hidden simulator state. Each draft executes against visible simulator
conditions with every action, instrument response, and measurement recorded. A small archive
(two candidates, selected on execution, physical validity, safety, and provenance) survives into
evidence-guided repair: the model must inspect the execution record, cite evidence identifiers
that actually appear in the trace, submit a bounded edit, and replay. Budgets are fixed in
advance — at most four repair rounds and twelve generated candidates per acquisition, with
episode horizons of 2–12 model turns in the study configurations. A successful patch with
fabricated provenance is ineligible for packaging.

### 3.4 Qualification and promotion

Development happens on **visible** conditions, where the model sees full execution evidence.
Qualification ends with a one-shot run on **locked** conditions that were hidden during
development, with no feedback. Deterministic execution and physical checks are authoritative
throughout. A model reviewer (or a human) may veto or hold a candidate, but nothing may rescue a
failed deterministic check. Outcomes are an honest three-way `ADMIT` / `REJECT` / `HOLD`; a `HOLD`
(insufficient evidence to decide) is reported as such rather than converted into a pass or
silently retried.

### 3.5 Drift and skill evolution

When a versioned simulator change makes a previously admitted skill fail, Proprio treats the
repair as a new admission problem, not an edit-in-place. The model generates an evolution proposal
from the observed drift evidence; the proposal must pass the changed condition, replay the full
historical set that previously worked (nominal behavior and prior repairs), and pass a fresh
locked sweep. Only a fully passing proposal is staged — with parent, rollback, evidence,
simulator, verifier, and validation hashes — and the previously admitted skill remains immutable.
A failed proposal is rejected and the parent is retained unchanged.

### 3.6 Pre-deployment boundary

Simulation qualification is a pre-deployment gate, not a deployment decision. Use on a physical
instrument still requires hardware adapters, interlocks, reference measurements on the target
instrument, recovery tests, supervised trials, and instrument-expert approval. Every skill in the
public catalog carries `hardware_qualification_required: true`, without exception.

## 4. Evaluation

### 4.1 Research questions

- **RQ1** — Can the model generate executable skills from instrument sources?
- **RQ2** — Does simulator evidence *causally* improve repair, beyond retrying generation?
- **RQ3** — Can independent gates prevent invalid promotion, including self-approved mistakes?
- **RQ4** — Does the method operate across distinct instrument families?
- **RQ5** — Can it detect drift and stage regression-free evolution?

### 4.2 Instrument families and evidence cohorts

| Cohort | Instruments | Role |
|---|---|---|
| Reference | 2D area-detector powder XRD (Bluesky/`ophyd.sim` execution, pyFAI-based verification) | Reference implementation and verifier metrology; **not** generalization data |
| Development | Keithley 2450-style SMU (PyVISA-sim); eight diagnostic instruments across liquid handling, battery cycling, additive manufacturing, and quantum transport | Admission proof; method development and mechanism evidence, excluded from the confirmatory claim |
| Confirmatory | Six instruments in three families held out of method development: absorbance and fluorescence plate reads (optical measurement), pump dose and dual-pump blending (calibrated delivery), isothermal hold and thermal cycling (thermal control) | Frozen paired causal study |
| Replication | Ten fresh generations per confirmatory instrument plus the external OpenFlexure microscope | Variance and breadth under the frozen protocol |
| External integration | [OpenFlexure microscope server](https://gitlab.com/openflexure/openflexure-microscope-server) (pinned revision `d26b93e`), run as a separate GPL-3.0 process via its public API | Externally authored simulator; breadth and evolution stress test |
| Frozen held-out round | OctoPrint virtual 3D printer, PyMoDAQ mock spectrometer, sinstruments pressure controller | Preregistered held-out panel for the frozen v0.2 method |

**Table 2.** Cohorts and their evidentiary roles. Development evidence never counts toward the
confirmatory claim; the held-out round was preregistered — families, thresholds, and per-family
pass requirements fixed — before the pinned simulators were inspected.

### 4.3 Causal repair design

Each paired unit starts from the *same* parent draft and model configuration and runs two arms:
one receives truthful, structured simulator evidence (execution trace, failed checks, telemetry);
the other receives no feedback. Success requires an actual code change, qualification on the
visible conditions, qualification on the locked conditions, and no regression on previously
working behavior. The principal mechanism analysis uses 18 non-overlapping paired units pooled
across three protocol generations — the frozen six-instrument confirmatory panel (6 units), the
eight-instrument diagnostic panel (8), and the final-protocol OpenFlexure development trials
(4)&nbsp;— with an exact one-sided McNemar test on the discordant pairs
([synthesis artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/generated/accumulated-causal-evidence/summary.json)).
Because it pools protocol generations, this is evidence about the *feedback-repair mechanism*, not
a single frozen-protocol success rate.

### 4.4 Verifier metrology

Trusting the gates requires measuring the gates. Every verifier is exercised against labeled valid
and invalid batteries with per-class false-admission and false-rejection reporting; physical
quantities are computed independently of the simulator's own internals (e.g., the microscopy
verifier never reads the simulator's focus score — it checks stage position, frame integrity, and
two separately implemented image-sharpness calculations). Batteries include an always-valid
adversary that claims every measurement is good, and adversarial cases that execute successfully
but are physically invalid. Fixed-index samples of raw records are inspected by hand and
countersigned.

### 4.5 Reproducibility

Sources, simulator revisions, prompts, budgets, provider route, seeds, and thresholds are frozen
and recorded per run. Canonical records are byte-deterministic; captured model interactions are
stored as cassettes so CI replays the full admission chain offline (fresh generation is a
separate release gate). The locked test suite (196 tests) asserts the *failed* research claims —
the external-family rejection, the reviewer-panel mismatch, the rejected evolution proposal — so
they cannot silently become passes. Engineering-smoke, diagnostic, and binding evidence are
explicitly separated, and 51 invalidated runs are retained under
[`artifacts/invalidated/`](https://github.com/Dynamical-Systems-Research/proprio/tree/main/artifacts/invalidated)
for audit rather than deleted. The evidence manifest binds 158 release artifacts by hash.

## 5. Results

### 5.1 Documentation becomes executable instrument operation

In the [70-generation replication
study](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/replication-dsv4/summary.json)
(ten independent generations per instrument, unique seeds, temperature 0.7, top-p 0.95), 68/70
initial drafts executed (97.1%; Wilson 95% CI 90.2–99.2%), 61/70 initial measurements were
physically valid (87.1%), and 64/70 final candidates passed every check (91.4%; Wilson 95% CI
82.5–96.0%). The six confirmatory instruments qualified **60/60**. The externally authored
OpenFlexure microscope is the honest boundary of that result: 10/10 drafts executed, but only
**4/10** final candidates passed the locked physical sweep against the frozen ≥8/10 threshold —
recorded as a failed breadth gate, with all six unqualified candidates rejected and no microscope
skill admitted. In the separate development cohort, DSV4 also compiled a correct Keithley
2450-style current measurement from driver and fixture documents
([admission artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/skill-admission/summary.json)).

### 5.2 Simulator evidence causes successful repair

Across the 18 paired units, truthful feedback produced **14/18** non-regressive repairs; the
identical drafts with no feedback produced **0/18** (exact one-sided paired p = 0.000061). Every
cohort showed positive uplift: 6/6 on the confirmatory panel (bootstrap 95% uplift interval
[1.0,&nbsp;1.0]), 5/8 on the diagnostic panel, 3/4 on the OpenFlexure development trials.

| Arm | Confirmatory (6) | Diagnostic (8) | OpenFlexure dev. (4) | Pooled (18) |
|---|---|---|---|---|
| Truthful simulator evidence | 6 | 5 | 3 | **14** |
| No feedback (same drafts) | 0 | 0 | 0 | **0** |

**Figure 2.** Paired intervention outcomes per protocol generation
([synthesis artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/generated/accumulated-causal-evidence/summary.json)).
The two panel cohorts score a repair as agent status `CANDIDATE`, target verdict `ADMIT`, and no
historical regression; the OpenFlexure development trials score the trial's qualification outcome
under the v0.2 protocol, which includes the locked sweep.

A representative repair, verbatim from the [calibrated-pump-dose
cassette](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/confirmatory-dsv4/calibrated-pump-dose/repair-truthful.json):
the visible-condition gate failed only `speed-support` (`maximum_rpm: 75.0`, `observed_rpm:
[100.0, 100.0]`). The model's logged diagnosis: *"Reduced prime and delivery speed from 100 rpm to
75 rpm to match the changed pump's maximum supported speed of 75.0 rpm … Calibration (0.050),
target volume (10.0 mL), halt, and return shape preserved."* The edited skill then passed the
changed condition, the historical nominal scenario, and 50 sealed locked conditions. The
no-feedback arm, given the same failing draft and the same budget, did not repair it. Improvement
comes from execution evidence, not from retries alone.

### 5.3 Independent gates prevent self-promotion

The clearest single case is the Keithley 2450 development study. DSV4 drafted two skills from
supplied documentation — one from the current fixture sheet (1 kΩ load, 1 V source, 2 mA
compliance, 10 mA range), one from a plausible stale worksheet (100 kΩ load, 200 µA compliance,
100 µA range) — and **self-judged both `ACCEPT`**
([captured completions](https://github.com/Dynamical-Systems-Research/proprio/tree/main/cassettes/dsv4)).
Proprio executed both against a PyVISA-sim instrument and checked the measured current against the
1 kΩ circuit law and the active range/compliance contract. The correct skill passed all nine
checks and was admitted; the self-accepted stale skill was rejected on the `compliance-contract`
and `range-contract` checks (observed ≈0.2 mA against a required minimum ≈1.1 mA). The rejected
draft exists only as evidence — it never entered the catalog.

The gates were then measured as instruments in their own right:

- **XRD reference verifier:** 5/5 injected execution-fault classes detected (a dropped frame is
  honestly labeled `degraded`); 0/300 false rejections on valid calibrant controls; 0 observed
  false acceptances across nine invalid classes × 300 cases; an always-valid adversary rejected in
  2,700/2,700 cases. One measured weakness is reported: the dedicated sample-displacement check
  missed direct attribution in 19/300 cases (AUROC 0.943) although adjacent shift/indexing checks
  still rejected every affected measurement
  ([metrology record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/metrology/report.md)).
- **Confirmatory-family verifiers:** 9,000 labeled simulations (1,800 valid, 7,200 invalid across
  wrong order, unsafe setting, wrong physical target, and omitted cleanup) with zero false
  admissions and zero false rejections; 30 fixed-index raw records hand-inspected and
  countersigned
  ([summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/confirmatory-metrology/summary.json)).
- **OpenFlexure verifier:** 2,700 labeled cases over eight invalid classes; zero invalid
  measurements accepted, one valid measurement in 300 falsely rejected. The two image-sharpness
  checks (frequency-domain and Laplacian) agreed on 299/300 valid frames; because they share the
  same exported frame they are not statistically independent, and that residual correlation is
  reported rather than hidden
  ([summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/microscopy/locked/metrology/summary.json)).
- **Adversarial composition:** a trajectory that executes successfully but contains a saturated
  detector frame passes procedural verification and fails validity — execution success cannot
  substitute for physical validity
  ([composition artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/composition/summary.json)).

Model judgment was measured under the same discipline. The DSV4 review prompt, frozen after
calibration, scored 100% critical-defect recall with zero false alarms on 24 unseen semantic-
mutation cases. The independent Qwen 3.7 Plus reviewer passed 56/56 calibration cases and 42/42
cases on the six confirmatory instruments, and matched 47/49 pre-fixed labels on the full panel —
where fresh replay showed both disagreements were wrong *fixture labels*, correctly rejected by
the reviewer; the panel verdict is preserved as `FAIL` rather than recalculated
([review record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/independent-review/summary.json)).
Across every battery: **zero overrides of a failed deterministic check**, by any model, in either
direction.

### 5.4 Evidence across instrument families

| Family (instruments) | Draft executes | Visible qualification | Locked qualification | Causal repair | Drift detected | Evolution | Fail-closed admission |
|---|---|---|---|---|---|---|---|
| Powder XRD (reference) | ✓ (reference) | ✓ | — | — | — | — | ✓ (saturated-frame case) |
| Electrical measurement (Keithley SMU) | ✓ | ✓ | — | — | — | — | ✓ (stale draft rejected) |
| Optical measurement (2) | 20/20 | 20/20 | 20/20 | 2/2 | — | — | ✓ |
| Calibrated delivery (2) | 20/20 | 20/20 | 20/20 | 2/2 | — | — | ✓ |
| Thermal control (2) | 20/20 | 20/20 | 20/20 | 2/2 | — | — | ✓ |
| Liquid handling (2, diagnostic) | ✓† | ✓† | — | 2/2 | 2/2 | 2/2 staged | ✓ |
| Battery cycling (2, diagnostic) | ✓† | ✓† | — | 1/2 | 2/2 | 2/2 staged | ✓ |
| Additive manufacturing (2, diagnostic) | ✓† | ✓† | — | 0/2 | 2/2 | 2/2 staged | ✓ |
| Quantum transport (2, diagnostic) | ✓† | ✓† | — | 2/2 | 2/2 | 2/2 staged | ✓ |
| Microscopy (OpenFlexure, external) | 10/10 | 6/10 | 4/10 (**FAIL** vs ≥8/10) | 3/4 (dev. trials) | 1/1 | 0/1 (**rejected**) | ✓ (nothing admitted) |
| 3D printing (OctoPrint, held-out) | — | — | — | — | — | — | ✓ (`HOLD` at preflight) |
| Spectral measurement (PyMoDAQ, held-out) | — | — | — | — | — | — | ✓ (`HOLD` at preflight) |
| Pressure control (sinstruments, held-out) | — | — | — | — | — | — | ✓ (`HOLD` at preflight) |

**Figure 3.** Cross-family claim matrix from committed artifacts. † Diagnostic-panel drafting
initially failed on a hidden executor-grammar mismatch (1/8 executable); after the executor
contract was disclosed and fixed, all eight instruments produced qualified, history-safe parents
([archive](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/dsv4-history-repair/summary.json)) —
which is why the panel is diagnostic evidence, not part of the confirmatory claim. Diagnostic
parents were qualified on visible and historical conditions; sealed 50-condition sweeps were
exercised on their evolution proposals (§5.5). Confirmatory per-family counts pool the paired
study and the ten-generation replication.

The last three rows deserve emphasis because they are the method behaving correctly on *its own
inputs*. The frozen v0.2 method was preregistered against three externally authored simulators;
deterministic fixture preflight then found that none of the pinned simulators could execute its
complete registered physical and drift contract (OctoPrint exposes no declared temperature
maxima; the pinned PyMoDAQ runtime does not expose the selected mock spectrometer; the
sinstruments emulator rejects reset/range/vent commands and its pressure readings ignore
setpoints). Proprio returned `HOLD` for all three families, spent **zero** model calls, and did
not swap in easier families
([preflight record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/heldout-generalization/preflight/summary.json)).
Cross-family generalization of the frozen method therefore remains **not established** — a
simulator-suitability result, not a model-failure result, and the next round of external-family
evidence will land in this same matrix as its artifacts are committed.

### 5.5 Skill evolution is gated rather than assumed

After a versioned simulator change broke all eight history-safe diagnostic parents, DSV4 inspected
the drift evidence and produced evolution proposals for all eight; each passed the changed
condition, full historical replay, and 50 sealed conditions, and each was **staged** — parent
immutable, rollback hash recorded, `hardware_gate_required: true` — never silently swapped in
([evolution record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/dsv4-evolution/summary.json)).
The external counterexample is retained alongside it: on the OpenFlexure family, the evolution
attempt exhausted its turn budget with a candidate that still failed the Laplacian focus threshold
and regressed the nominal FFT check; only 6/10 locked drift offsets passed, the independent
reviewer rejected it, and the parent skill was left untouched
([cassette](https://github.com/Dynamical-Systems-Research/proprio/tree/main/cassettes/microscopy-evolution)).
Evolution is *demonstrated* on the reduced-order development cases and *correctly refused*
elsewhere — not guaranteed on every stochastic attempt.

### 5.6 Verification cost and engineering burden

Test-time compute is modest by modern inference standards. The full 70-generation replication used
626 model calls and 2,527,902 tokens under fixed turn budgets (2–12 model turns per episode). The eight-instrument evolution battery used 84 calls / 473k tokens
(≈$0.03 at the recorded route pricing); building the eight qualified history parents took 53 calls
/ 224k tokens; the failed microscopy evolution burned 21 calls / 308k tokens before rejecting
itself. Additional compute paid off when the evidence pointed at a discrete cause (a speed limit,
a stale range); it hit diminishing returns when the physical contract could not be satisfied
within budget — four of the six failed OpenFlexure candidates ended at the turn limit without
submitting, and the two others passed visible repair but failed hidden starting positions.

The unavoidable human cost is verifier construction, reported as measured line counts rather than
estimates
([burden manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/engineering-burden/summary.json)):

| Instrument family | Simulator/adapter LOC | Verifier LOC | Source-bundle LOC | Physical checks | Invalid classes |
|---|---|---|---|---|---|
| Optical measurement (2) | 130 | 107 | 30 | 7 each | 4 |
| Calibrated delivery (2) | 113 | 80 | 24 | 5 / 6 | 4 |
| Thermal control (2) | 100 | 50 | 24 | 7 each | 4 |
| OpenFlexure microscopy (external) | 333 (adapter) | 162 | 32 | 10 | 8 |

Reusing the externally authored OpenFlexure simulator avoided writing a digital twin but still
required the 333-line API adapter, a 162-line verifier, and a 185-line metrology harness.
Person-hours are not reported because prospective labor logging was not active.

## 6. Discussion: verified skills as a laboratory capability layer

### 6.1 Where Proprio sits

```text
Scientific objective
        ↓
Experiment-selection or judgment policy
        ↓
Proprio-qualified instrument skill
        ↓
Instrument-control framework (Bluesky, SiLA, PyLabRobot, …)
        ↓
Simulator qualification            ← everything in this report
        ↓
Real-hardware qualification        ← separate, unfinished gate
        ↓
Laboratory operation
```

### 6.2 Why fast verification matters

No model weights change anywhere in this method. All additional compute is spent at inference
time — drafting, executing, diagnosing, repairing, replaying — and the verifier is what converts
those extra samples into qualified procedural capability rather than merely more generated text.
The paired result in §5.2 is the mechanism: with the same drafts and budget, evidence-grounded
search repaired 14/18 units and blind regeneration repaired none. The practical corollary for
laboratories is that faster simulators and richer physical contracts directly increase how much
capability can be explored, and *trusted*, before an instrument is ever touched.

### 6.3 Implications for composable laboratories

Instrument standards make capabilities portable; simulators make capability acquisition
inexpensive; independent verification makes skills admissible; and hash-bound skill catalogs make
qualified capability reusable across agents and workflows. The
[current catalog](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json)
holds eight packages — the XRD reference, the Keithley development skill, and the six confirmatory
skills — each bound to its qualification artifact and each still requiring hardware qualification.
A laboratory adding an instrument follows the documented recipe: connect the public API, provide a
simulator with explicit reset and failure behavior, write the physical contract, build the labeled
validity battery *before* asking a model to generate anything, and freeze thresholds in advance.

### 6.4 Scope

All qualification reported here is simulation-only, and simulator–reality correspondence is
imperfect by construction; each family's verifier requires instrument-specific engineering (§5.6);
model generation is stochastic, so acquisition and evolution are demonstrated capabilities with
measured variance, not guarantees (OpenFlexure's 4/10 and the rejected evolution proposal are the
canonical counterexamples); the pooled causal analysis spans protocol generations and therefore
establishes the feedback mechanism rather than a single frozen-protocol rate; and cross-family
generalization of the frozen v0.2 method remains not established after the held-out panel's
preflight `HOLD`. Real-hardware qualification — adapters, interlocks, reference measurements,
recovery tests, supervised trials, expert sign-off — is the next gate, and nothing in this report
substitutes for it.

## 7. Conclusion

Instrument operation can be treated as *acquired procedural capability*: compiled from the same
documentation a human operator would read, exercised in simulation, and packaged with its
evidence. Simulator execution plus independent physics-grounded verification provides a practical
admission mechanism — one that measurably drives repair (14/18 versus 0/18), rejects plausible
self-approved mistakes, refuses unsuitable fixtures at zero model cost, and declines to replace
working skills with unproven revisions. Proprio offers this as an open method: documentation and
test-time compute in, independently qualified skills out, with every claim traceable to a
committed artifact and a clearly marked hardware-qualification gate still ahead.

---

## Sources

- [On the Need for Autonomous Science Instruments](https://chemrxiv.org/doi/10.26434/chemrxiv.10001836) (ChemRxiv, 2026)
- [Towards a composable, modular laboratory ecosystem for autonomous materials research and development](https://www.nist.gov/publications/towards-composable-modular-laboratory-ecosystem-autonomous-materials-research-and) (NIST, 2026)
- [An agentic artificially intelligent X-ray scientist](https://www.nature.com/articles/s42256-026-01261-5) (Chen et al., *Nature Machine Intelligence*, 2026)
- [Operating advanced scientific instruments with AI agents that learn on the job](https://www.nature.com/articles/s41524-026-02005-0) (Vriza et al., *npj Computational Materials*, 2026)
- [ASPIRE: Agentic Skill Discovery for Robotics](https://research.nvidia.com/labs/gear/aspire/) (NVIDIA, 2026)
- [4D Digital Twins: Real-to-Sim-to-Real for Physical AI](https://research.nvidia.com/labs/amri/projects/4DDT/2026/) (NVIDIA, 2026)
- [MatteriX](https://arxiv.org/abs/2601.13232) (2026)
- [SkillOpt](https://github.com/microsoft/SkillOpt) (Microsoft)
- [Hermes Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) (Nous Research)
- [Scaling LLM Test-Time Compute Optimally Can Be More Effective than Scaling Model Parameters](https://arxiv.org/abs/2408.03314) (Snell et al., 2024)
- [Voyager: An Open-Ended Embodied Agent with Large Language Models](https://arxiv.org/abs/2305.16291) (Wang et al., 2023)

*Evidence artifacts cited inline are committed to
[`Dynamical-Systems-Research/proprio`](https://github.com/Dynamical-Systems-Research/proprio) and
hash-bound in the [evidence manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/manifest.json).*
