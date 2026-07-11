# Proprio: Simulator-Verified Skill Acquisition for Scientific Instruments

**Dynamical Systems Research, Technical Report, July 2026**

[Code](https://github.com/Dynamical-Systems-Research/proprio) ·
[Skill catalog](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json) ·
[Example skill, calibrated pump dose](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/simulated/calibrated-pump-dose) ·
[Example skill, Keithley 2450](https://github.com/Dynamical-Systems-Research/proprio/tree/main/skills/keithley-2450) ·
[Agent loop](https://github.com/Dynamical-Systems-Research/proprio/blob/main/src/proprio/agent.py) ·
[Demo video (OpenFlexure)](https://github.com/Dynamical-Systems-Research/proprio/blob/main/public/proprio-openflexure-flagship.mp4)

*Every number in this report is recomputed from evidence artifacts committed to `main` at
[`c2cd6be`](https://github.com/Dynamical-Systems-Research/proprio/commit/c2cd6be). The persistent
cross-family panel (§4.2, §5.4) is bound to method digest `c1a28d…7267`
([freeze manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/cross-family/method-freeze/manifest.json)).
Each result links to the record it comes from.*

## Abstract

Scientific agents cannot close an experimental loop merely by choosing the next experiment. They
must translate that decision into a physically valid instrument operation, and the laboratory
needs evidence that the procedure producing the measurement can be trusted. Open interfaces,
modular laboratory standards, and digital twins are making instruments easier to address and
simulate, while recent agent systems show that operating procedures can be generated, repaired,
and remembered. What remains unresolved for scientific instruments is a reusable, physics-grounded
qualification method. A model-written procedure may execute without error and still violate an
operating limit, produce invalid evidence, or repair one condition by breaking another.

Proprio is an open-source method for acquiring instrument skills in context while keeping
promotion authority outside the generating model. An agent reads instrument documentation,
executes bounded candidate procedures in simulation, and retains actions, observations, failed
checks, diagnoses, and edits in a persistent trajectory. Independent execution and physical
contracts determine whether a candidate may proceed to a locked qualification run, and only a
fully passing candidate enters the skill catalog. The same fail-closed process governs later
evolution under simulated drift.

Truthful simulator feedback produced 14 of 18 paired non-regressive repairs, whereas the identical
drafts produced 0 of 18 without feedback (exact one-sided paired p = 0.000061). Ten independent
generations per instrument qualified 60/60 candidates across six simulated instruments in three
families. Under the frozen persistent protocol, one binding session in each of three screened
external simulator families completed acquisition, locked qualification, truthful repair, drift
detection, and non-regressive staged evolution with zero invalid promotions. This evidence supports
a reproducible simulation-based pre-deployment qualification method across the tested families; it
does not establish a population-level generalization rate or readiness for unsupervised hardware
operation.

## 1. The agent-to-instrumentation gap is a qualification problem

### 1.1 Open interfaces make instruments addressable

Scientific instrumentation is moving from equipment designed around a human operator toward
software-addressable, modular laboratory systems. [*On the Need for Autonomous Science
Instruments: A Call to Action*](https://chemrxiv.org/doi/full/10.26434/chemrxiv.10001836/v1)
argues that autonomous laboratories require open data and software-defined control, physical
design for robotic operation, and modularity. NIST's [composable laboratory
ecosystem](https://www.nist.gov/publications/towards-composable-modular-laboratory-ecosystem-autonomous-materials-research-and)
places instruments within a broader architecture of scientific decision-making, orchestration,
sample management, data systems, local instrument agents, and device controllers connected through
community standards.

These proposals address a real infrastructure bottleneck. Autonomous-laboratory teams still spend
substantial effort bridging proprietary interfaces and adapting equipment designed for human hands,
which makes systems expensive to reproduce and difficult to reconfigure. Control substrates such as
[Bluesky](https://blueskyproject.io), [Ophyd](https://github.com/bluesky/ophyd),
[SiLA](https://sila-standard.com), [PyLabRobot](https://github.com/PyLabRobot/pylabrobot), and
[HELAO](https://github.com/High-Throughput-Experimentation) make a growing range of instruments
callable. Addressability is necessary, but it does not establish that a procedure written by an
agent is correct.

### 1.2 A callable instrument is not yet a qualified capability

NIST's architecture locates an important boundary near the instrument. A device controller owns
native motion, readiness signals, interlocks, and measurement commands, while a local agent
translates generic experimental intent into instrument-specific coordinates and parameters. In the
paper's X-ray diffraction example, that local layer may also reduce data and detect misalignment or
detector errors without deciding the broader scientific question.

This local translation is procedural capability, not command syntax. A script may run to completion
while using the wrong range, violating a calibration assumption, saturating a detector, or producing
evidence outside the conditions its downstream policy can interpret. A repair may solve the visible
failure and silently regress a condition that worked before. The gap between an addressable
instrument and a reusable laboratory capability is therefore a qualification boundary. The
procedure needs evidence that it executed honestly, satisfied an instrument-specific physical
contract, remained valid on conditions withheld during development, and preserved prior behavior.

### 1.3 Instrument agents establish feasibility and expose the remaining gap

Recent work establishes that language-model agents can operate advanced instruments and adapt
within constrained workflows. Chen et al.'s [agentic X-ray
scientist](https://www.nature.com/articles/s42256-026-01261-5) developed a guided alignment workflow
in a virtual six-circle beamline before supervised deployment at a synchrotron. During the physical
run, the agent identified an approximately 1.22° motor offset and reused the empirical correction
while locating a second reflection. This is meaningful within-trajectory adaptation, although the
authors explicitly state that the limited real-beamline result is not a statistically established
capability and note that the operating guidance itself was developed and refined in simulation.

Vriza et al. demonstrate a complementary form of continuity in [agents that learn on the
job](https://www.nature.com/articles/s41524-026-02005-0). Their agents coordinate X-ray nanoprobe
and robotic thin-film workflows through supplied function libraries, review, and human approval.
Corrective human demonstrations are generalized into retrievable memory and reused in later tasks.
The work establishes real instrument orchestration and persistent human teaching, while also showing
that textual feedback does not repair every visual-reasoning failure.

Together, these studies show that agents can execute instrument workflows, carry experimental state
through a trajectory, and reuse expert corrections. The next deployment-facing question is whether
an agent can construct a reusable procedure from instrument documentation and simulator evidence,
repair it without a human supplying the correction, and pass an independent physical admission gate.
Proprio is designed around that question by allowing the agent to propose, diagnose, and repair
while reserving promotion for an independent gate.

### 1.4 Contributions

- A lightweight **persistent in-context acquisition loop** that turns instrument documentation and
  simulator evidence into executable, versioned skills without changing model weights.
- An **independent qualification boundary** based on execution integrity, instrument-specific
  physical contracts, provenance, and conditions hidden during repair, with fail-closed
  `ADMIT`, `REJECT`, and `HOLD` decisions.
- A **causal and cross-family evaluation** of acquisition, evidence-guided repair, and
  drift-triggered non-regressive evolution, with every promoted and rejected candidate preserved as
  replayable evidence.

![The agent-to-instrumentation qualification gap](assets/agent-to-instrumentation-gap.png)

**Figure 1.** Open interfaces make scientific instruments callable, while digital twins provide a
place to rehearse operating procedures. Proprio uses that environment for persistent in-context
acquisition, while independent execution, physical-contract, and locked-condition checks retain
promotion authority. A simulation-qualified skill still enters a separate hardware qualification
process before laboratory use.

## 2. Related work supplies the components of the qualification lifecycle

### 2.1 Digital twins make procedural interaction affordable

[MatteriX](https://arxiv.org/html/2601.13232v1) combines robotic manipulation with fluid, powder,
thermal, device, and approximate reaction semantics in a chemistry-laboratory twin. It includes
explicit action success and failure semantics and an integrated qualitative workflow verifier that
checks reaction preconditions and expected products. MatteriX therefore provides more than motion
completion, and it is a substantive example of the simulation substrate Proprio is designed to
consume. Its reaction models remain semi-quantitative, and its physical deployments expose the
calibration, perception, and digital-to-physical mismatches that make hardware qualification
unavoidable.

NVIDIA's [4D Digital Twins](https://research.nvidia.com/labs/amri/projects/4DDT/2026/) workshop
frames the upstream real-to-sim-to-real agenda around sim-ready reconstruction, physically grounded
agent training, and deployment back into the world. This is an environment-building agenda rather
than an evaluated skill-acquisition method. Proprio begins once a suitable simulator exists and asks
what procedural capability may be qualified from interaction with it. The optional MatteriX adapter
in this release reports
[`unavailable`](https://github.com/Dynamical-Systems-Research/proprio/blob/main/docs/matterix-adapter.md)
rather than treating an untested integration as a pass.

### 2.2 Skill systems turn sources and trajectories into procedural memory

[Hermes `/learn`](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills#learning-a-skill-from-sources-learn)
shows how an agent can gather documentation, code, URLs, notes, or a prior workflow and author a
reusable `SKILL.md`. Hermes also provides persistent agent-managed skills and optional human approval
for skill writes. Its authoring contract asks the model to include verification guidance, but the
`/learn` path does not require the procedure to execute or pass a physical check before it is saved.

[SkillOpt](https://arxiv.org/abs/2605.23904) provides a disciplined method for improving textual
skills without changing the target model. It samples scored trajectories, retains rejected edits and
failure evidence, proposes bounded changes, and replaces the current skill only when performance
strictly improves on a held-out selection split, which gives it an authority stronger than model
self-judgment. Its gate asks whether a candidate improves a task score; Proprio asks whether an
instrument procedure satisfies an absolute, preregistered operating contract.

### 2.3 Execution traces support iterative program repair

[ASPIRE](https://arxiv.org/html/2607.00272v1) is a close methodological analogue. It
records fine-grained multimodal robot execution traces, diagnoses failures, searches over repaired
code-as-policy programs, validates the selected program on held-out seeds, and distills reusable
repair knowledge into a skill library. Its persistent task-analysis state and debug-versus-evaluation
separation demonstrate how simulator interaction can become test-time procedural learning rather than
disposable retrying.

ASPIRE evaluates robotic task completion and transfer. Proprio adopts the same broad logic for
scientific instruments but changes the admission object and evidence contract. A scientific
instrument skill must not only complete a task; it must execute within the controller contract,
produce physically usable evidence, satisfy locked qualification conditions, preserve historical
behavior during evolution, and carry provenance that the generating model cannot rewrite. Proprio
also remains intentionally smaller, using one persistent agent loop and instrument-specific
contracts rather than a multi-agent robotics stack or open-ended task curriculum.

### 2.4 Proprio composes these components into a qualification lifecycle

| Research line | What it supplies | Boundary relative to Proprio |
|---|---|---|
| Automation-native instruments and modular laboratories | Open control, robotic compatibility, replaceable interfaces, and system standards | Makes instruments addressable and composable; does not qualify agent-authored procedures |
| Digital twins and laboratory simulation | Resettable interaction, controlled faults, device and process dynamics, and potential transfer | Supplies experience and test conditions; does not by itself control skill promotion |
| Documentation-to-skill systems | Reusable procedural artifacts synthesized from sources and prior workflows | Authors procedural knowledge; write approval is not physical qualification |
| Text-space skill optimization | Trajectory-driven edits, retained failures, and held-out improvement gates | Optimizes relative task performance rather than an absolute instrument contract |
| Robotics skill discovery | Rich traces, program repair, evolutionary search, locked evaluation, and reusable repair knowledge | Qualifies robotic task success rather than scientific measurement validity |
| Scientific-instrument agents | Tool use, closed-loop operation, within-run adaptation, and persistent human teaching | Establishes feasibility on concrete workflows; does not provide a reusable cross-family admission method |
| **Proprio** | Persistent simulator-grounded acquisition, physical qualification, locked replay, provenance, and non-regressive evolution | A simulation-based pre-deployment gate; hardware qualification remains separate |

**Table 1.** The enabling components already exist across instrument infrastructure, simulation,
agent learning, and robotics. Proprio composes them at the instrument boundary so that procedural
experience can accumulate in context while promotion remains governed by independently implemented
execution and physical contracts.

## 3. Proprio

### 3.1 Inputs and output

| Object | Definition |
|---|---|
| Instrument sources | Manuals, API/driver documentation, and operating limits shown to the model. |
| Controller contract | The permitted commands and observable state; nothing else is callable. |
| Simulator | Executable instrument or process behavior, with explicit reset and failure semantics. |
| Physical contract | Independent, machine-checkable requirements for a valid operation and measurement (e.g., delivered volume within 0.10 mL at certified 0.050 mL/rev calibration). |
| Skill package | `SKILL.md` operating procedure, bounded control code, provenance hashes, and a link to the qualification record, hash-bound in [`catalog.json`](https://github.com/Dynamical-Systems-Research/proprio/blob/main/catalog.json). |

All reported model-driven studies used DeepSeek V4 Flash (DSV4, resolved
`deepseek/deepseek-v4-flash-20260423`) as the drafting and repair model. Qwen 3.7 Plus served as a
separately prompted independent reviewer. The interface is model-agnostic, and every reported
result remains tied to the model, provider route or allowlist, prompts, and sampling settings that
produced it.

### 3.2 Scientist-facing workflow

1. **Learn** a skill from instrument sources.
2. **Qualify** it independently in simulation.
3. **Admit** the passing skill into the catalog.
4. **Monitor** execution evidence for drift.
5. **Stage** a verified evolution proposal when drift breaks the admitted skill.

> The agent drives discovery, execution, diagnosis, repair, and evolution; it cannot authorize
> promotion.

### 3.3 Persistent in-context skill acquisition

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

Before repair begins, the method samples an archive of 6 independent drafts in a bounded control
dialect and executes them on **visible** simulator conditions whose evidence the agent may inspect.
The dialect permits finite loops and observation-conditioned branches while excluding hidden
simulator state, unrestricted imports, exception swallowing, and unbounded calls. Three candidates
survive archive selection on execution, physical validity, safety, and provenance. A selected
trajectory may then consume up to 6 repair rounds and 24 candidate variants. Every repair must cite
evidence identifiers that appear in the recorded trace; a patch with fabricated provenance cannot
be packaged even if it executes successfully.

### 3.4 Experience accumulates without transferring admission authority

Persistence changes what the agent can learn during a trajectory, but it does not change who
decides. Simulator and verifier records return to the agent as tool results that may support a new
diagnosis or edit. Promotion still depends on deterministic execution, physical-validity,
provenance, and locked-condition checks that the agent cannot override. In a paired causal
comparison, the truthful and no-feedback arms branch from the same evidence-free prefix and keep
separate persistent histories thereafter, so the feedback intervention does not leak across arms.

The earlier studies reported in Sections 5.1–5.3 used bounded episodic repair. Each attempt received
the current candidate and latest verifier record but discarded the earlier conversation, which
created a clean causal baseline at the cost of repeatedly reconstructing state. The persistent
cross-family results in Sections 5.4–5.6 use the frozen v0.4 protocol described above. This protocol
history is reported explicitly because the pooled causal result spans method generations, whereas
the cross-family panel evaluates the current persistent loop.

### 3.5 Qualification and promotion

Development happens on visible conditions. Qualification ends with a one-shot run on **locked**
conditions that were hidden during development, with no feedback. Deterministic execution and
physics checks are authoritative throughout. A model reviewer (or a human) may veto or hold a
candidate, but its opinion is advisory input to the decision, never the decision itself, and
nothing may rescue a failed deterministic check. Admission is **fail-closed**. A candidate is
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
public catalog carries `hardware_qualification_required` set to `true`, without exception.

## 4. Evaluation

### 4.1 Research questions

- **RQ1.** Can the model generate executable skills from instrument sources?
- **RQ2.** Does simulator evidence *causally* improve repair, beyond retrying generation?
- **RQ3.** Can independent gates prevent invalid promotion, including self-approved mistakes?
- **RQ4.** Does the method operate across distinct instrument families?
- **RQ5.** Can it detect drift and stage non-regressive evolution?

### 4.2 Instrument families and evidence cohorts

| Cohort | Instruments | Role |
|---|---|---|
| Reference | 2D area-detector powder XRD (Bluesky/`ophyd.sim` execution, pyFAI-based verification) | Reference implementation and verifier metrology; **not** generalization data |
| Development | Keithley 2450-style SMU (PyVISA-sim); eight diagnostic instruments across liquid handling, battery cycling, additive manufacturing, and quantum transport | Admission proof; method development and mechanism evidence, excluded from the confirmatory claim |
| Confirmatory | Six instruments in three families held out of method development: absorbance and fluorescence plate reads (optical measurement), pump dose and dual-pump blending (calibrated delivery), isothermal hold and thermal cycling (thermal control) | Frozen paired causal study |
| Replication | Ten fresh generations per confirmatory instrument plus the external OpenFlexure microscope | Variance and breadth under the frozen protocol |
| External integration | [OpenFlexure microscope server](https://gitlab.com/openflexure/openflexure-microscope-server) (pinned revision `d26b93e`), run as a separate GPL-3.0 process via its public API | Externally authored simulator; breadth and evolution stress test |
| Preflight suitability round | OctoPrint virtual 3D printer, PyMoDAQ mock spectrometer, sinstruments pressure controller | Preregistered v0.2 panel that exercised the deterministic fixture-suitability gate (§5.4) |
| Persistent cross-family panel | North Robotics pipette calibration (liquid handling), HELAO Gamry cyclic voltammetry (electrochemistry), CLSLab light spectrometer (optical spectroscopy) | One binding session per externally authored family under the frozen v0.4 method, with persistent causal repair and drift evolution; no failing family may be replaced (§5.4) |

**Table 2.** Cohorts and their evidentiary roles. Development evidence never counts toward the
confirmatory claim. Both external rounds were preregistered, with families, thresholds, and
per-family pass requirements fixed before binding exposure to their simulators.

### 4.3 Causal repair design

Each paired unit starts from the *same* parent draft and model configuration and runs two arms.
One receives truthful, structured simulator evidence (execution trace, failed checks, telemetry),
the other receives no feedback. Success requires an actual code change, qualification on the
visible conditions, qualification on the locked conditions, and no regression on previously
working behavior; a repair meeting all four is called **non-regressive**. The principal mechanism
analysis uses 18 non-overlapping paired units pooled
across three protocol generations, including the frozen six-instrument confirmatory panel (6 units), the
eight-instrument diagnostic panel (8), and the final-protocol OpenFlexure development trials
(4). The analysis uses an exact one-sided McNemar test on the discordant pairs
([synthesis artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/generated/accumulated-causal-evidence/summary.json)).
Because it pools protocol generations, this is evidence about the *feedback-repair mechanism*, not
a single frozen-protocol success rate.

### 4.4 Verifier metrology

Every verifier is exercised against labeled valid and invalid batteries with per-class
false-admission and false-rejection reporting. Physical quantities are computed independently of
the simulator's own internals. The microscopy verifier, for example, never reads the simulator's
focus score, and instead checks stage position, frame integrity, and two separately implemented
image-sharpness calculations. Batteries include an always-valid
adversary that claims every measurement is good, and adversarial cases that execute successfully
but are physically invalid. Fixed-index samples of raw records are inspected by hand and
countersigned.

### 4.5 Reproducibility

Sources, simulator revisions, prompts, budgets, provider route, seeds, and thresholds are frozen
and recorded per run. The persistent method was frozen before binding exposure at digest
`c1a28d…7267`. The 3 cross-family instruments, upstream revisions, source bundles, prompts,
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
[`artifacts/invalidated/`](https://github.com/Dynamical-Systems-Research/proprio/tree/main/artifacts/invalidated)
for audit rather than deleted.

Canonical records are byte-deterministic, and captured model interactions are stored as cassettes
so CI replays the full admission chain offline, while fresh generation remains a separate release
gate. The locked test suite contains 292 tests and asserts
the *failed* research claims, including the external-family rejection, the reviewer-panel mismatch,
and the rejected evolution proposals, so they cannot silently become passes. The evidence manifest binds
177 release artifacts by hash.

## 5. Results

### 5.1 Documentation becomes executable instrument operation

The [70-generation replication
study](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/replication-dsv4/summary.json)
ran ten independent generations per instrument with unique seeds, temperature 0.7, and top-p 0.95.
Three rates summarize it.

- Initial drafts that executed, 68/70 (97.1%; Wilson 95% CI 90.2–99.2%).
- Initial measurements that were physically valid, 61/70 (87.1%).
- Final candidates that passed every check, 64/70 (91.4%; Wilson 95% CI 82.5–96.0%).

The six confirmatory instruments qualified **60/60** candidates. The externally authored
OpenFlexure microscope marks the limit of that result. All 10 drafts executed, while only
**4/10** final candidates passed the locked physical sweep against the frozen ≥8/10 threshold.
The breadth gate therefore failed, with all 6 unqualified candidates rejected and no microscope
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
cohort showed positive uplift, with 6/6 on the confirmatory panel (bootstrap 95% uplift interval
[1.0,&nbsp;1.0]), 5/8 on the diagnostic panel, and 3/4 on the OpenFlexure development trials.

| Arm | Confirmatory (6) | Diagnostic (8) | OpenFlexure dev. (4) | Pooled (18) |
|---|---|---|---|---|
| Truthful simulator evidence | 6 | 5 | 3 | **14** |
| No feedback (same drafts) | 0 | 0 | 0 | **0** |

**Table 3.** Paired intervention outcomes per protocol generation
([synthesis artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/generated/accumulated-causal-evidence/summary.json)).
A repair counts as a success only if the edited skill reaches verdict `ADMIT` with no historical
regression; the OpenFlexure development trials are scored on the trial's qualification outcome
under the v0.2 protocol, which includes the locked sweep.

A representative repair appears verbatim in the [calibrated-pump-dose
cassette](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/confirmatory-dsv4/calibrated-pump-dose/repair-truthful.json).
The visible-condition gate failed only `speed-support` (`maximum_rpm: 75.0`, `observed_rpm:
[100.0, 100.0]`). The model's logged diagnosis was *"Reduced prime and delivery speed from 100 rpm to
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
supplied documentation. One came from the current fixture sheet (1 kΩ load, 1 V source, 2 mA
compliance, 10 mA range) and one from a plausible stale worksheet (100 kΩ load, 200 µA compliance,
100 µA range). It **self-judged both `ACCEPT`**
([captured completions](https://github.com/Dynamical-Systems-Research/proprio/tree/main/cassettes/dsv4)).
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
  ([summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/confirmatory-metrology/summary.json)).
- **OpenFlexure verifier.** 2,700 labeled cases over eight invalid classes; zero invalid
  measurements accepted, one valid measurement in 300 falsely rejected. The two image-sharpness
  checks (frequency-domain and Laplacian) agreed on 299/300 valid frames; because they share the
  same exported frame they are not statistically independent, and that residual correlation is
  reported rather than hidden
  ([summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/microscopy/locked/metrology/summary.json)).
- **Adversarial composition.** A trajectory that executes successfully but contains a saturated
  detector frame passes procedural verification and fails validity, so execution success cannot
  substitute for physical validity
  ([composition artifact](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/composition/summary.json)).
- **Cross-family round verifiers (frozen v0.3).** 4,200 labeled simulations across the North,
  HELAO Gamry, and CLSLab fixtures (900 valid and 3,300 invalid cases over 11 failure classes),
  with zero false admissions and 3/900 false rejections, all on the North fixture
  ([metrology records](https://github.com/Dynamical-Systems-Research/proprio/tree/main/artifacts/evidence/generalization-v0.3/metrology)).
- **Provenance gate.** A CLSLab engineering session with a staged evolution proposal and a passing
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
Across every battery, no model, whether drafter or reviewer, overrode a failed deterministic check.

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
| Liquid handling (North pipette calibration, external) | ✓ | ✓ | ✓ | truthful 1/1; no feedback 1/1 | 1/1 | 1/1 staged | ✓ (0 invalid promotions) |
| Electrochemistry (HELAO Gamry CV, external) | ✓ | ✓ | ✓ | truthful 1/1; no feedback 0/1 | 1/1 | 1/1 staged | ✓ (0 invalid promotions) |
| Optical spectroscopy (CLSLab light spectrometer, external) | ✓ | ✓ | ✓ | truthful 1/1; no feedback 0/1 | 1/1 | 1/1 staged | ✓ (0 invalid promotions) |

**Table 4.** Cross-family claim matrix from committed evidence. `n/m` counts passes over attempts;
✓ marks a capability demonstrated in the linked records, while an em dash marks a capability not exercised.
Confirmatory rows report the ten-generation replication; their causal-repair column reports the
paired study. † Diagnostic-panel parents were qualified on visible and historical conditions
after an initially hidden executor-grammar mismatch was disclosed and fixed (drafting was 1/8
executable before the fix), which is why the panel is diagnostic evidence rather than part of the
confirmatory claim
([archive](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/dsv4-history-repair/summary.json));
their 50-condition locked sweeps ran on the evolution proposals (§5.5). The 3 external rows report
one binding session per family under the same frozen v0.4 method
([panel summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/summary.json)).

Simulator suitability is checked by a deterministic gate before any model call. The v0.2 panel
was preregistered against three externally authored simulators whose pinned revisions turned out
unable to execute their complete registered physical and drift contracts (OctoPrint exposes no
declared temperature maxima; the pinned PyMoDAQ runtime does not expose the selected mock
spectrometer; the sinstruments emulator rejects reset/range/vent commands and its pressure
readings ignore setpoints). Proprio returned `HOLD` for all three families, spent **zero** model
calls, and did not swap in easier families
([preflight record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/heldout-generalization/preflight/summary.json)).

The persistent cross-family panel binds 3 externally authored control interfaces that passed the
same deterministic preflight, covering North Robotics pipette calibration, HELAO Gamry cyclic
voltammetry, and the CLSLab light spectrometer. Each family produced an executable skill that
passed visible and locked qualification. Starting from a separate self-accepted parent that failed
the registered calibration change, truthful simulator evidence produced a qualified repair in all
3 families, while the no-feedback control qualified in 1. Every admitted parent then failed its
registered drift condition, and all 3 persistent evolution trajectories produced proposals that
passed the changed condition, historical replay, and locked qualification. No trajectory regressed
historical behavior, and no invalid candidate was promoted
([panel summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/summary.json)).

This panel establishes cross-family replication of the complete simulation ladder for these 3
screened external families. Each family contributes one binding session, showing that the frozen
method transferred across the tested control interfaces without estimating a repeated-generation
success rate or a statistical feedback effect. The simulators were screened for suitability before
v0.3 model use, so the result does not claim untouched first exposure. The
earlier v0.3 records remain immutable as the episodic baseline
([stop record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/generalization-v0.3/run-stop.json)).

### 5.5 Skill evolution is gated rather than assumed

After a versioned simulator change broke all eight history-safe diagnostic parents, DSV4 inspected
the drift evidence and produced evolution proposals for all eight; each passed the changed
condition, full historical replay, and 50 locked conditions. Each was **staged**, with its parent
left immutable, its rollback hash recorded, and `hardware_gate_required` set to `true`
([evolution record](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/dsv4-evolution/summary.json)).
The external counterexample is retained alongside it. On the OpenFlexure family, the evolution
attempt exhausted its turn budget with a candidate that still failed the Laplacian focus threshold
and regressed the nominal FFT check; only 6/10 locked drift offsets passed, the independent
reviewer rejected it, and the parent skill was left untouched
([cassette](https://github.com/Dynamical-Systems-Research/proprio/tree/main/cassettes/microscopy-evolution)).
The persistent cross-family panel held to the same discipline. Registered drift invalidated the
admitted parent in all 3 families, and DSV4 entered a persistent evolution trajectory with the
drift record, source bundle, current skill, and complete repair ledger in context. North and HELAO
each required 2 submitted repairs before the verifier admitted a proposal, while CLSLab qualified
its first submitted repair. Every final proposal passed the changed condition, replayed the
historical acquisition conditions without regression, passed locked qualification, and was staged
with `hardware_qualification_required` set to `true`. The parent skills remain immutable
([North](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/north-pipette-calibration/session-000/evolution/summary.json),
[HELAO](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/helao-gamry-cv/session-000/evolution/summary.json),
[CLSLab](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/clslab-light-spectrometer/session-000/evolution/summary.json)).

### 5.6 Verification cost and engineering burden

The full 70-generation replication used 626 model calls and 2,527,902 tokens under fixed turn
budgets (2–12 model turns per episode), modest by current inference standards. The
eight-instrument evolution battery used 84 calls / 473k tokens (≈$0.03 at the recorded route
pricing); building the eight qualified history parents took 53 calls / 224k tokens; the failed
microscopy evolution burned 21 calls / 308k tokens before rejecting itself. Additional compute
paid off when the evidence pointed at a discrete cause (a speed limit, a stale range). It hit
diminishing returns when the physical contract could not be satisfied within budget. Four of the
six failed OpenFlexure candidates ended at the turn limit without submitting, and the other two
passed visible repair but failed hidden starting positions.

The persistent cross-family panel evaluated 30 candidate variants and captured 166 model
responses, of which 165 completed successfully. The run consumed 2,769,382 tokens at a recorded
cost of $0.262. The truthful trajectories reached their first qualified repair in 6 model calls for
North, 6 for HELAO, and 3 for CLSLab. Deterministic request-side compaction activated in 3
trajectories, 2 duplicate candidate hashes were rejected, and one HTTP 502 response was recorded
and recovered within the frozen transport policy. These totals describe one binding session per
family rather than an expected acquisition cost
([panel summary](https://github.com/Dynamical-Systems-Research/proprio/blob/main/cassettes/cross-family/summary.json)).

The unavoidable human cost is verifier construction, reported as measured line counts rather than
estimates
([burden manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/engineering-burden/summary.json)).

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

Proprio sits between scientific intent and instrument control. An experiment-selection or judgment
policy may decide what evidence to acquire, while Bluesky, SiLA, PyLabRobot, HELAO, or a vendor
driver supplies the interface through which an operation is executed. Proprio qualifies the
procedural artifact that connects those two layers. It does not select the scientific objective,
replace the control framework, or authorize hardware deployment. Its output is a simulation-qualified
skill package that remains subject to the laboratory's hardware commissioning process.

### 6.2 Why fast verification matters

No model weights change anywhere in this method. All additional compute is spent at inference
time on drafting, executing, diagnosing, repairing, and replaying. The verifier converts those
extra samples into qualified procedural capability rather than more generated text. The paired
result in §5.2 is the mechanism at work. Given the same drafts and budget, evidence-grounded
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
A laboratory adding an instrument follows the documented recipe by connecting the public API,
providing a simulator with explicit reset and failure behavior, writing the physical contract,
building the labeled validity battery *before* asking a model to generate anything, and freezing
thresholds in advance.

### 6.4 Scope

All qualification reported here is simulation-only, and simulator-to-reality correspondence is
imperfect by construction. Each family's verifier requires instrument-specific engineering
(§5.6). Model generation is stochastic, so acquisition and evolution are demonstrated
capabilities with measured variance, not guarantees; OpenFlexure's 4/10 and the rejected
evolution proposals remain the canonical counterexamples. The pooled causal analysis spans protocol
generations, so it establishes the feedback mechanism rather than a single frozen-protocol rate.
The persistent panel replicates acquisition, locked qualification, causal repair, drift detection,
and non-regressive evolution across 3 screened external families. Because the study contains one
binding session per family and uses simulators screened before model exposure in v0.3, it neither
estimates stochastic success rates nor constitutes an untouched-family test. Real-hardware
qualification (§3.7) remains a separate gate, and nothing in this report substitutes for it.

## 7. Conclusion

Instrument operation can be treated as *acquired procedural capability*, compiled from the same
documentation a human operator would read, exercised in simulation, and packaged with its
evidence. Simulator execution plus independent physics-grounded verification provides a practical
admission mechanism. It measurably drives repair (14/18 versus 0/18), rejects plausible
self-approved mistakes, and never promotes an unproven revision over a working skill. Proprio
offers this as an open method, with documentation and test-time compute producing independently
qualified skills whose evidence remains attached. Under the frozen persistent protocol, all 3
screened external families completed acquisition, locked qualification, truthful repair, drift
detection, and non-regressive staged evolution with zero invalid promotions. The result establishes
a reproducible simulation-based pre-deployment method across the tested families, with every claim
traceable to a recorded artifact and a hardware-qualification gate still ahead.

---

## Sources

- [On the Need for Autonomous Science Instruments: A Call to Action](https://chemrxiv.org/doi/full/10.26434/chemrxiv.10001836/v1) (ChemRxiv, 2026)
- [Towards a composable, modular laboratory ecosystem for autonomous materials research and development](https://www.nist.gov/publications/towards-composable-modular-laboratory-ecosystem-autonomous-materials-research-and) (Joress et al., *Matter*, 2026)
- [An agentic artificially intelligent X-ray scientist](https://www.nature.com/articles/s42256-026-01261-5) (Chen et al., *Nature Machine Intelligence*, 2026)
- [Operating advanced scientific instruments with AI agents that learn on the job](https://www.nature.com/articles/s41524-026-02005-0) (Vriza et al., *npj Computational Materials*, 2026)
- [ASPIRE: Agentic Skill Discovery for Robotics](https://arxiv.org/abs/2607.00272) (NVIDIA, 2026)
- [4D Digital Twins: Real-to-Sim-to-Real for Physical AI](https://research.nvidia.com/labs/amri/projects/4DDT/2026/) (NVIDIA, 2026)
- [MATTERIX: A multiscale virtual laboratory for automated experiments](https://www.nature.com/articles/s43588-025-00924-4) (Pei et al., *Nature Computational Science*, 2025)
- [SkillOpt: Executive Strategy for Self-Evolving Agent Skills](https://arxiv.org/abs/2605.23904) (Microsoft Research, 2026)
- [Hermes Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) (Nous Research)

*Evidence artifacts cited inline are committed to
[`Dynamical-Systems-Research/proprio`](https://github.com/Dynamical-Systems-Research/proprio) and
hash-bound in the [evidence manifest](https://github.com/Dynamical-Systems-Research/proprio/blob/main/artifacts/evidence/manifest.json).*
