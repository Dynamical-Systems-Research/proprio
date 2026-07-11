# Proprio: Simulator-Verified Skill Acquisition for Scientific Instruments

**Dynamical Systems Research — Technical Report, July 2026**

[Code](https://github.com/Dynamical-Systems-Research/proprio) ·
[Skill catalog](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json) ·
[Example skill: calibrated pump dose](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/simulated/calibrated-pump-dose) ·
[Example skill: Keithley 2450](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/keithley-2450) ·
[Agent loop](https://github.com/Dynamical-Systems-Research/proprio/blob/main/src/proprio/agent.py) ·
[Demo video (OpenFlexure)](https://github.com/Dynamical-Systems-Research/proprio/blob/main/public/proprio-openflexure-flagship.mp4)

*Every number in this report is recomputed from evidence artifacts committed to `main` at
[`61a1caa`](https://github.com/Dynamical-Systems-Research/proprio/commit/61a1caa). The frozen
cross-family round (§4.2, §5.4) is bound to method digest `eef835…6b1`
([freeze manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/generalization-v0.3/method-freeze/manifest.json)).
Each result links to the record it comes from.*

## Abstract

Scientific agents increasingly need to operate instruments — run a scan, deliver a reagent, hold a
temperature — rather than only reason about data those instruments have already produced.
Laboratory infrastructure now supplies open control interfaces and capable simulation, and recent
agent demonstrations show that models can operate advanced instruments and accumulate reusable
procedural knowledge. The unresolved question is narrower: how does an agent-generated operating
procedure earn admission into a laboratory's trusted capability set?

Proprio is an open-source method built around that question. It converts instrument documentation
into executable operating skills through bounded inference-time search against a simulator. Every
candidate then faces gates the generating model cannot override: independent execution and physics
checks, a one-shot qualification run on locked conditions hidden during development, and
fail-closed admission.

Four results hold on the recorded evidence. Truthful simulator feedback produced 14 of 18 paired
non-regressive repairs where the identical drafts produced 0 of 18 without feedback (exact
one-sided paired p = 0.000061). Ten independent generations per instrument qualified 60/60
candidates across six simulated instruments in three families. Under a frozen
documentation-to-skill protocol, the drafting model produced independently simulation-qualified
skills across three externally authored instrument families: liquid handling, electrochemistry,
and optical spectroscopy. And the gates rejected or held every invalid result, including a
plausible draft the drafting model had itself approved and a proposal whose transport provenance
violated the frozen provider allowlist. Fast simulation and independent verification can turn
test-time compute into qualified instrument capability in simulation. Cross-family drift evolution
is not yet established, and qualification on real hardware remains a separate, unfinished gate.

## 1. Scientific agents need qualified instrument capabilities

### 1.1 Autonomous science is constrained by its instrument interface

The case made in [*On the Need for Autonomous Science
Instruments*](https://chemrxiv.org/doi/10.26434/chemrxiv.10001836) is that scalable autonomous
laboratories require instruments with open, software-defined control, designed for automation and
modular composition. That argument has largely been won at the interface level: a growing share of
laboratory hardware is reachable through documented APIs, drivers, and orchestration frameworks.

An open API, however, only makes an instrument *accessible* to an agent. It does not establish
that an operating procedure the agent wrote is correct: that the ramp rate respects the hardware,
that the measurement it produces is physically meaningful, or that a revision made next month
still handles the conditions that worked last month. What is missing between "the agent can call
the instrument" and "the laboratory can rely on the result" is an independently qualified
**instrument skill**: an operating procedure packaged with its evidence.

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
simulators as inputs and emits qualified skills, packaged with provenance and test evidence, that
orchestration layers can then call.

### 1.3 The generation–verification gap

Recent agent systems demonstrate that instrument operation by language-model agents is feasible.
The [agentic X-ray scientist](https://www.nature.com/articles/s42256-026-01261-5) of Chen et al.
practiced in a virtual six-circle beamline before supervised real deployment, adapted to an
approximately 1.22° motor offset, and reused that correction when locating a second reflection,
while explicitly treating the limited real-beamline trials as proof-of-concept rather than
statistical evidence. The ["learn on the job"
agents](https://www.nature.com/articles/s41524-026-02005-0) of Vriza et al. operate real X-ray
nanoprobe and robotic thin-film workflows, storing human feedback as reusable memory with human
approval before execution.

These systems establish that agents can *generate* and *adapt* operating behavior. Proprio tests
the complementary question: can an agent acquire and repair procedural capability from instrument
sources alone, under a protocol in which it is structurally unable to approve its own mistakes,
and can the resulting evidence be replayed, audited, and held to preregistered thresholds?

### 1.4 Contributions

- A reusable **source → skill → simulation → qualification → admission** method, released as
  open-source code with schemas, simulators, verifiers, and a hash-bound skill catalog.
- A **causal evaluation protocol** that separates simulator-grounded repair from repeated
  generation, using paired interventions from identical drafts.
- An **open evidence and skill format** exercised across scientific-instrument families,
  including drift-triggered evolution and fail-closed promotion, with every failure preserved in
  the public record.

## 2. Related systems and the remaining seam

Each system below contributes something Proprio depends on or deliberately does not rebuild.

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
training. These provide the environments in which capability can be exercised cheaply, which is
the property Proprio's search loop consumes. Proprio ships an optional MatteriX adapter; it
reports
[`unavailable`](https://github.com/Dynamical-Systems-Research/proprio/blob/main/docs/matterix-adapter.md)
rather than an untested pass.

### 2.3 Procedural skill acquisition and improvement

[Hermes `/learn`](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills#learning-a-skill-from-sources-learn)
authors reusable skills from documentation, directories, URLs, or prior workflows; Proprio adopts
this learn-from-sources interface. [SkillOpt](https://github.com/microsoft/SkillOpt) optimizes
textual skills through trajectory-driven edits and held-out validation.
[ASPIRE](https://research.nvidia.com/labs/gear/aspire/) inspects robotic execution traces, repairs
control programs, validates by re-execution, and accumulates reusable skills; Proprio follows its
debug-versus-locked-validation discipline. [Voyager](https://arxiv.org/abs/2305.16291) introduced
the executable skill library with iterative environment feedback. On the inference side, [Snell et
al.](https://arxiv.org/abs/2408.03314) show that adaptive search and verifier-guided selection let
additional inference-time compute substitute for model scale. Proprio applies that result to
procedural capability rather than answer selection.

### 2.4 Where the seam remains

| System class | Generates procedures | Executes in an environment | Learns from feedback | Independent physical admission | Historical replay before evolution |
|---|---|---|---|---|---|
| Instrument-control frameworks | No | Yes | No | Limited | No |
| Documentation-to-skill systems | Yes | Sometimes | Sometimes | No instrument-specific gate | Limited |
| Agentic instrument demonstrations | Yes | Yes | Yes | Workflow-specific | Varies |
| Robotics skill-discovery systems | Yes | Yes | Yes | Task-success validation | Varies |
| **Proprio** | **Yes** | **Yes** | **Yes** | **Yes** | **Yes** |

**Table 1.** Positioning against adjacent systems. No single ingredient is new. The contribution
is the composition: admission authority sits in instrument-specific execution and physics checks
that the generating model cannot override.

## 3. Proprio

### 3.1 Inputs and output

| Object | Definition |
|---|---|
| Instrument sources | Manuals, API/driver documentation, and operating limits shown to the model. |
| Controller contract | The permitted commands and observable state; nothing else is callable. |
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
through independent execution and physics checks, locked qualification, and fail-closed
admission (right). Drift detection re-enters the loop as a staged evolution proposal. A separate
hardware gate stands between everything shown here and a real instrument.

### 3.3 Inference-time skill search

Skill acquisition is organized as verifier-guided test-time compute. The model writes four
independent drafts in a bounded, executable control dialect: a restricted command language with
finite loops, observation-conditioned branches, and explicit call limits, and with no exception
swallowing and no access to hidden simulator state. Each draft executes against **visible**
simulator conditions, meaning conditions whose full execution evidence the model may read, and
every action, instrument response, and measurement is recorded. Two candidates survive into
repair, selected on execution, physical validity, safety, and provenance.

Repair is evidence-bound. The model must inspect the execution record, cite evidence identifiers
that actually appear in the trace, submit a bounded edit, and replay. Budgets are fixed in
advance: at most four repair rounds and twelve generated candidates per acquisition, with episode
horizons of 2–12 model turns in the study configurations. A successful patch with fabricated
provenance is ineligible for packaging.

### 3.4 One persistent agent context

The protocol generations reported in §5 ran each repair attempt as a bounded episode: the model
received the current candidate and the latest verifier record, and everything else it had learned
— earlier diagnoses, failed edits, tool results — was discarded between episodes. That design gave
a clean causal baseline, but it forces test-time compute to re-derive diagnoses and lets the model
repeat strategies that already failed.

The current method revision (v0.4) replaces those resets with one persistent agent context per
acquisition, repair, or evolution run
([`agent.py`](https://github.com/Dynamical-Systems-Research/proprio/blob/main/src/proprio/agent.py)).
The model API stays stateless; Proprio owns the context and resends it on every call. The context
keeps what an operator's notebook would: every prior action and tool result, every verifier
record, and a compact repair ledger holding, for each attempt, the candidate hash, the checks that
failed, the cited evidence, the diagnosis, the change, and the outcome. The loop checkpoints the
full state after every tool result and verifier record, so an interrupted run resumes
deterministically without re-issuing a completed model call. A submission whose candidate hash
already appears in the ledger is rejected as a duplicate. In paired causal comparisons, the
truthful and no-feedback arms branch from the same evidence-free prefix and never share a message
afterward. If a context outgrows its preregistered byte limit, compaction is deterministic and
applies only to the resent request; safety failures, candidate hashes, the ledger, and the latest
verifier record are never dropped, and the complete record stays on disk.

None of this changes who decides. The agent remembers more; admission still requires the same
deterministic execution, physical-validity, provenance, and locked-condition gates it cannot
override. The persistent loop is committed and exercised by its test battery and an engineering
smoke command; every result in §5 predates it and was produced by the episodic protocol.

### 3.5 Qualification and promotion

Development happens on visible conditions. Qualification ends with a one-shot run on **locked**
conditions that were hidden during development, with no feedback. Deterministic execution and
physics checks are authoritative throughout. A model reviewer (or a human) may veto or hold a
candidate, but its opinion is advisory input to the decision, never the decision itself, and
nothing may rescue a failed deterministic check. Admission is **fail-closed**: a candidate is
admitted only when every deterministic check passes, and any failure, missing evidence, or
unresolved veto resolves to `REJECT` or `HOLD` (insufficient evidence to decide), never to a
pass. A `HOLD` is reported as such rather than converted into a pass or silently retried.

### 3.6 Drift and skill evolution

When a versioned simulator change makes a previously admitted skill fail, Proprio treats the
repair as a new admission problem, not an edit-in-place. The model generates an evolution proposal
from the observed drift evidence; the proposal must pass the changed condition, replay the full
historical set that previously worked (nominal behavior and prior repairs), and pass a fresh
locked sweep. Only a fully passing proposal is staged, with parent, rollback, evidence,
simulator, verifier, and validation hashes, and the previously admitted skill remains immutable.
A failed proposal is rejected and the parent is retained unchanged.

### 3.7 Pre-deployment boundary

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
- **RQ5** — Can it detect drift and stage non-regressive evolution?

### 4.2 Instrument families and evidence cohorts

| Cohort | Instruments | Role |
|---|---|---|
| Reference | 2D area-detector powder XRD (Bluesky/`ophyd.sim` execution, pyFAI-based verification) | Reference implementation and verifier metrology; **not** generalization data |
| Development | Keithley 2450-style SMU (PyVISA-sim); eight diagnostic instruments across liquid handling, battery cycling, additive manufacturing, and quantum transport | Admission proof; method development and mechanism evidence, excluded from the confirmatory claim |
| Confirmatory | Six instruments in three families held out of method development: absorbance and fluorescence plate reads (optical measurement), pump dose and dual-pump blending (calibrated delivery), isothermal hold and thermal cycling (thermal control) | Frozen paired causal study |
| Replication | Ten fresh generations per confirmatory instrument plus the external OpenFlexure microscope | Variance and breadth under the frozen protocol |
| External integration | [OpenFlexure microscope server](https://gitlab.com/openflexure/openflexure-microscope-server) (pinned revision `d26b93e`), run as a separate GPL-3.0 process via its public API | Externally authored simulator; breadth and evolution stress test |
| Preflight suitability round | OctoPrint virtual 3D printer, PyMoDAQ mock spectrometer, sinstruments pressure controller | Preregistered v0.2 panel that exercised the deterministic fixture-suitability gate (§5.4) |
| Frozen cross-family round | North Robotics pipette calibration (liquid handling), HELAO Gamry cyclic voltammetry (electrochemistry), CLSLab light spectrometer (optical spectroscopy) | Externally authored control interfaces under the frozen v0.3 method; digest hash-bound before exposure; no failing family may be replaced; preserved as a bounded baseline (§5.4) |

**Table 2.** Cohorts and their evidentiary roles. Development evidence never counts toward the
confirmatory claim; both external rounds were preregistered — families, thresholds, and
per-family pass requirements fixed — before binding exposure to their simulators.

### 4.3 Causal repair design

Each paired unit starts from the *same* parent draft and model configuration and runs two arms:
one receives truthful, structured simulator evidence (execution trace, failed checks, telemetry);
the other receives no feedback. Success requires an actual code change, qualification on the
visible conditions, qualification on the locked conditions, and no regression on previously
working behavior; a repair meeting all four is called **non-regressive**. The principal mechanism
analysis uses 18 non-overlapping paired units pooled
across three protocol generations — the frozen six-instrument confirmatory panel (6 units), the
eight-instrument diagnostic panel (8), and the final-protocol OpenFlexure development trials
(4)&nbsp;— with an exact one-sided McNemar test on the discordant pairs
([synthesis artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/generated/accumulated-causal-evidence/summary.json)).
Because it pools protocol generations, this is evidence about the *feedback-repair mechanism*, not
a single frozen-protocol success rate.

### 4.4 Verifier metrology

Every verifier is exercised against labeled valid and invalid batteries with per-class
false-admission and false-rejection reporting. Physical quantities are computed independently of
the simulator's own internals: the microscopy verifier, for example, never reads the simulator's
focus score, and instead checks stage position, frame integrity, and two separately implemented
image-sharpness calculations. Batteries include an always-valid
adversary that claims every measurement is good, and adversarial cases that execute successfully
but are physically invalid. Fixed-index samples of raw records are inspected by hand and
countersigned.

### 4.5 Reproducibility

Sources, simulator revisions, prompts, budgets, provider route, seeds, and thresholds are frozen
and recorded per run. The v0.3 method was frozen before binding exposure at digest `eef835…6b1`:
the three cross-family instruments, upstream revisions, source bundles, prompts, control dialect,
search budgets, thresholds, provider allowlist, and promotion rules are hash-bound, and no failing
family may be replaced. The **provider allowlist** names the model-provider routes permitted for a
binding run (DeepInfra and GMICloud for the v0.3 round); **transport provenance** is the route
each call actually used. A result whose transport provenance falls outside the allowlist cannot
be promoted.

Evidence is tiered. A **binding** run executes under the frozen method digest and counts toward a
preregistered claim. An **engineering** run is exploratory, used to build and exercise the
machinery, and never counts. **Diagnostic** evidence comes from method development and is likewise
excluded from confirmatory claims. The tiers are kept separate throughout this report, and 51
invalidated runs are retained under
[`artifacts/invalidated/`](https://github.com/Dynamical-Systems-Research/proprio/tree/main/artifacts/invalidated)
for audit rather than deleted.

Canonical records are byte-deterministic, and captured model interactions are stored as cassettes
so CI replays the full admission chain offline; fresh generation is a separate release gate. The
locked test suite (266 tests at the [v0.3
handoff](https://github.com/Dynamical-Systems-Research/proprio/blob/main/docs/handoff.md)) asserts
the *failed* research claims — the external-family rejection, the reviewer-panel mismatch, the
rejected evolution proposals — so they cannot silently become passes. The evidence manifest binds
158 release artifacts by hash.

## 5. Results

### 5.1 Documentation becomes executable instrument operation

The [70-generation replication
study](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/replication-dsv4/summary.json)
ran ten independent generations per instrument with unique seeds, temperature 0.7, and top-p 0.95.
Three rates summarize it:

- Initial drafts that executed: 68/70 (97.1%; Wilson 95% CI 90.2–99.2%).
- Initial measurements that were physically valid: 61/70 (87.1%).
- Final candidates that passed every check: 64/70 (91.4%; Wilson 95% CI 82.5–96.0%).

The six confirmatory instruments qualified **60/60**. The externally authored
OpenFlexure microscope marks the limit of that result: 10/10 drafts executed, but only
**4/10** final candidates passed the locked physical sweep against the frozen ≥8/10 threshold —
recorded as a failed breadth gate, with all six unqualified candidates rejected and no microscope
skill admitted. In the separate development cohort, DSV4 also compiled a correct Keithley
2450-style current measurement from driver and fixture documents
([admission artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/skill-admission/summary.json)).

The frozen cross-family round extends the acquisition result to externally authored control
interfaces. Under the v0.3 protocol, DSV4 produced an executable, physically qualified,
locked-condition skill for each of the three families
([North](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/generalization-v0.3-binding/north-pipette-calibration/session-000/summary.json),
[HELAO](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/generalization-v0.3/run-stop.json),
[CLSLab](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/generalization-v0.3/clslab-light-spectrometer/session-000/summary.json)),
with independent gate decisions of `ADMIT`/`PASS` (§5.4).

### 5.2 Simulator evidence causes successful repair

Across the 18 paired units, truthful feedback produced **14/18** non-regressive repairs; the
identical drafts with no feedback produced **0/18** (exact one-sided paired p = 0.000061). Every
cohort showed positive uplift: 6/6 on the confirmatory panel (bootstrap 95% uplift interval
[1.0,&nbsp;1.0]), 5/8 on the diagnostic panel, 3/4 on the OpenFlexure development trials.

| Arm | Confirmatory (6) | Diagnostic (8) | OpenFlexure dev. (4) | Pooled (18) |
|---|---|---|---|---|
| Truthful simulator evidence | 6 | 5 | 3 | **14** |
| No feedback (same drafts) | 0 | 0 | 0 | **0** |

**Table 3.** Paired intervention outcomes per protocol generation
([synthesis artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/generated/accumulated-causal-evidence/summary.json)).
A repair counts as a success only if the edited skill reaches verdict `ADMIT` with no historical
regression; the OpenFlexure development trials are scored on the trial's qualification outcome
under the v0.2 protocol, which includes the locked sweep.

A representative repair, verbatim from the [calibrated-pump-dose
cassette](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/confirmatory-dsv4/calibrated-pump-dose/repair-truthful.json):
the visible-condition gate failed only `speed-support` (`maximum_rpm: 75.0`, `observed_rpm:
[100.0, 100.0]`). The model's logged diagnosis: *"Reduced prime and delivery speed from 100 rpm to
75 rpm to match the changed pump's maximum supported speed of 75.0 rpm … Calibration (0.050),
target volume (10.0 mL), halt, and return shape preserved."* The edited skill then passed the
changed condition, the historical nominal scenario, and 50 locked conditions. The no-feedback
arm, given the same failing draft and the same budget, did not repair it.

The frozen cross-family round reproduced the same signature. In both completed binding pairs
([North](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/generalization-v0.3-binding/north-pipette-calibration/session-000/causal/summary.json)
and
[HELAO](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/generalization-v0.3-binding/helao-gamry-cv/session-000/causal/summary.json)),
the truthful-feedback arm qualified in a single episode with locked `ADMIT` while the identical
no-feedback arm failed across four episodes with locked `REJECT`, and a
[CLSLab engineering pair](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/generalization-v0.3-smoke-final/clslab-light-spectrometer/session-003/causal/summary.json)
behaved the same way. These pairs are reported alongside, not folded into, the 18-unit synthesis.

### 5.3 Independent gates prevent self-promotion

The clearest single case is the Keithley 2450 development study. DSV4 drafted two skills from
supplied documentation: one from the current fixture sheet (1 kΩ load, 1 V source, 2 mA
compliance, 10 mA range) and one from a plausible stale worksheet (100 kΩ load, 200 µA compliance,
100 µA range). It **self-judged both `ACCEPT`**
([captured completions](https://github.com/Dynamical-Systems-Research/proprio/tree/main/cassettes/dsv4)).
Proprio executed both against a PyVISA-sim instrument and checked the measured current against the
1 kΩ circuit law and the active range/compliance contract. The correct skill passed all nine
checks and was admitted; the self-accepted stale skill was rejected on the `compliance-contract`
and `range-contract` checks (observed ≈0.2 mA against a required minimum ≈1.1 mA). The rejected
draft exists only as evidence. It never entered the catalog.

The gates themselves were then measured:

- **XRD reference verifier:** 5/5 injected execution-fault classes detected (a dropped frame is
  labeled `degraded`); 0/300 false rejections on valid calibrant controls; 0 observed
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
- **Cross-family round verifiers (frozen v0.3):** 4,200 labeled simulations across the North,
  HELAO Gamry, and CLSLab fixtures (900 valid and 3,300 invalid cases over 11 failure classes),
  with zero false admissions and 3/900 false rejections, all on the North fixture
  ([metrology records](https://github.com/Dynamical-Systems-Research/proprio/tree/main/artifacts/evidence/generalization-v0.3/metrology)).
- **Provenance gate:** a CLSLab engineering session with a staged evolution proposal and a passing
  locked sweep was reduced to `HOLD` because part of its transport ran on a provider outside the
  frozen allowlist
  ([session record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/generalization-v0.3-smoke-final/clslab-light-spectrometer/session-003/summary.json)).
  The drafting model could not override the decision.

Model judgment was measured under the same discipline. The DSV4 review prompt, frozen after
calibration, scored 100% critical-defect recall with zero false alarms on 24 unseen review cases
(12 critical-defect mutations, 6 valid controls, and 6 unavailable-evidence cases). The
independent Qwen 3.7 Plus reviewer passed 56/56 calibration cases and 42/42 cases on the six
confirmatory instruments, and matched 47/49 pre-fixed labels on the full panel. Fresh replay
showed both disagreements were wrong *fixture labels* that the reviewer had correctly rejected;
the panel verdict is preserved as `FAIL` rather than recalculated
([review record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/independent-review/summary.json)).
Across every battery, no model — drafter or reviewer — overrode a failed deterministic check.

### 5.4 Evidence across instrument families

| Family (instruments) | Draft executes | Visible qualification | Locked qualification | Causal repair | Drift detected | Evolution | Fail-closed admission |
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
| Liquid handling (North pipette calibration, external) | ✓ | ✓ | ✓ `ADMIT`/`PASS` | ✓ (paired) | 1/1 | 0/1 (**rejected**) | ✓ |
| Electrochemistry (HELAO Gamry CV, external) | ✓ | ✓ | ✓ (locked `PASS`) | ✓ (paired) | 1/1 | **rejected** (2 episodes) | ✓ |
| Optical spectroscopy (CLSLab light spectrometer, external) | ✓‡ | ✓‡ | ✓‡ `ADMIT`/`PASS` | ✓‡ (paired) | 1/1‡ | staged → `HOLD`‡ | ✓ (provenance) |

**Table 4.** Cross-family claim matrix from committed evidence. `n/m` counts passes over attempts;
✓ marks a capability demonstrated in the linked records; — marks a capability not exercised.
Confirmatory rows report the ten-generation replication; their causal-repair column reports the
paired study. † Diagnostic-panel parents were qualified on visible and historical conditions
after an initially hidden executor-grammar mismatch was disclosed and fixed (drafting was 1/8
executable before the fix), which is why the panel is diagnostic evidence rather than part of the
confirmatory claim
([archive](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/dsv4-history-repair/summary.json));
their 50-condition locked sweeps ran on the evolution proposals (§5.5). ‡ Engineering-run
evidence under the frozen v0.3 method (§4.5). The North row reports a complete binding session;
the HELAO row reports the binding evidence recorded in the
[stop record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/generalization-v0.3/run-stop.json).

Simulator suitability is checked by a deterministic gate before any model call. The v0.2 panel
was preregistered against three externally authored simulators whose pinned revisions turned out
unable to execute their complete registered physical and drift contracts (OctoPrint exposes no
declared temperature maxima; the pinned PyMoDAQ runtime does not expose the selected mock
spectrometer; the sinstruments emulator rejects reset/range/vent commands and its pressure
readings ignore setpoints). Proprio returned `HOLD` for all three families, spent **zero** model
calls, and did not swap in easier families
([preflight record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/heldout-generalization/preflight/summary.json)).

The successor cross-family round binds three externally authored control interfaces that passed
that same deterministic preflight (North Robotics pipette calibration, HELAO Gamry cyclic
voltammetry, and the CLSLab light spectrometer) under the frozen v0.3 method (§4.5). Every family
produced an independently qualified, locked-condition skill; the North and HELAO binding sessions
completed paired causal repair; and the North session carried the ladder through a
drift-evolution attempt whose proposal was rejected fail-closed rather than promoted. **Skill
acquisition and independent qualification generalize across the three external families tested;
the complete acquisition → causal repair → drift-evolution ladder is not yet established across
all three.** No repeated-generation success-rate claim is made for the frozen panel. The v0.3
round is preserved as a bounded baseline: its records are immutable
([stop record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/generalization-v0.3/run-stop.json)),
and the specified successor method — a minimal persistent agent context across repair and
evolution episodes — is to be frozen before the next binding exposure
([handoff note](https://github.com/Dynamical-Systems-Research/proprio/blob/main/docs/handoff.md)).

### 5.5 Skill evolution is gated rather than assumed

After a versioned simulator change broke all eight history-safe diagnostic parents, DSV4 inspected
the drift evidence and produced evolution proposals for all eight; each passed the changed
condition, full historical replay, and 50 locked conditions, and each was **staged**, with parent
immutable, rollback hash recorded, and `hardware_gate_required: true`, never silently swapped in
([evolution record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/dsv4-evolution/summary.json)).
The external counterexample is retained alongside it: on the OpenFlexure family, the evolution
attempt exhausted its turn budget with a candidate that still failed the Laplacian focus threshold
and regressed the nominal FFT check; only 6/10 locked drift offsets passed, the independent
reviewer rejected it, and the parent skill was left untouched
([cassette](https://github.com/Dynamical-Systems-Research/proprio/tree/main/cassettes/microscopy-evolution)).
The frozen cross-family round held to the same discipline. The North drift-evolution proposal
failed its gates in the binding session and was rejected with promotion blocked
([record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/generalization-v0.3-binding/north-pipette-calibration/session-000/evolution/summary.json));
two HELAO evolution episodes were likewise independently rejected
([stop record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/generalization-v0.3/run-stop.json));
and a staged CLSLab engineering proposal was reduced to `HOLD` when part of its transport ran on
a provider outside the frozen allowlist. Cross-family drift evolution therefore remains mixed:
demonstrated on the reduced-order development cases, correctly refused or held elsewhere, and
never promoted without passing evidence.

### 5.6 Verification cost and engineering burden

The full 70-generation replication used 626 model calls and 2,527,902 tokens under fixed turn
budgets (2–12 model turns per episode), modest by current inference standards. The
eight-instrument evolution battery used 84 calls / 473k tokens (≈$0.03 at the recorded route
pricing); building the eight qualified history parents took 53 calls / 224k tokens; the failed
microscopy evolution burned 21 calls / 308k tokens before rejecting itself. Additional compute
paid off when the evidence pointed at a discrete cause (a speed limit, a stale range). It hit
diminishing returns when the physical contract could not be satisfied within budget: four of the
six failed OpenFlexure candidates ended at the turn limit without submitting, and the other two
passed visible repair but failed hidden starting positions.

The unavoidable human cost is verifier construction, reported as measured line counts rather than
estimates
([burden manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/engineering-burden/summary.json)):

| Instrument family | Simulator/adapter LOC | Verifier LOC | Source-bundle LOC | Physical checks | Invalid classes |
|---|---|---|---|---|---|
| Optical measurement (2) | 130 | 107 | 30 | 7 each | 4 |
| Calibrated delivery (2) | 113 | 80 | 24 | 5 / 6 | 4 |
| Thermal control (2) | 100 | 50 | 24 | 7 each | 4 |
| OpenFlexure microscopy (external) | 333 (adapter) | 162 | 32 | 10 | 8 |

**Table 5.** Measured engineering burden by instrument family, in nonblank lines of code, with
physical checks and labeled invalid classes per family.

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
time on drafting, executing, diagnosing, repairing, and replaying. The verifier converts those
extra samples into qualified procedural capability rather than more generated text. The paired
result in §5.2 is the mechanism at work: given the same drafts and budget, evidence-grounded
search repaired 14/18 units and blind regeneration repaired none. The practical corollary for
laboratories is that faster simulators and richer physical contracts directly increase how much
capability can be explored and trusted before an instrument is ever touched.

### 6.3 Implications for composable laboratories

Instrument standards make capabilities portable, and simulators make their acquisition cheap.
Independent verification is what makes a skill admissible, and a hash-bound catalog is what makes
it reusable across agents and workflows. The
[current catalog](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json)
holds eight packages (the XRD reference, the Keithley development skill, and the six confirmatory
skills), each bound to its qualification artifact and each still requiring hardware qualification.
A laboratory adding an instrument follows the documented recipe: connect the public API, provide a
simulator with explicit reset and failure behavior, write the physical contract, build the labeled
validity battery *before* asking a model to generate anything, and freeze thresholds in advance.

### 6.4 Scope

All qualification reported here is simulation-only, and simulator–reality correspondence is
imperfect by construction. Each family's verifier requires instrument-specific engineering
(§5.6). Model generation is stochastic, so acquisition and evolution are demonstrated
capabilities with measured variance, not guarantees; OpenFlexure's 4/10 and the rejected
evolution proposals are the canonical counterexamples. The pooled causal analysis spans protocol
generations, so it establishes the feedback mechanism rather than a single frozen-protocol rate.
Cross-family evidence stops at the line drawn in §5.4: acquisition and independent qualification
generalize across the three external families of the frozen panel, the complete drift-evolution
ladder does not, and no repeated-generation success rate is claimed for that panel.
Real-hardware qualification (§3.7) is the next gate, and nothing in this report substitutes for
it.

## 7. Conclusion

Instrument operation can be treated as *acquired procedural capability*: compiled from the same
documentation a human operator would read, exercised in simulation, and packaged with its
evidence. Simulator execution plus independent physics-grounded verification provides a practical
admission mechanism: it measurably drives repair (14/18 versus 0/18), rejects plausible
self-approved mistakes, and never promotes an unproven revision over a working skill. Proprio
offers this as an open method: documentation and test-time compute in, independently qualified
skills out, with every claim traceable to a recorded evidence artifact and a
hardware-qualification gate still ahead.

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
