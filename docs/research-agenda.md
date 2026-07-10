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

## Decision and stakeholder

The decision is whether an agent-authored instrument skill is safe and evidence-valid enough
to advance from documentation into a supervised hardware qualification. Instrument operators,
facility owners, scientific-policy authors, and skill-library maintainers need the decision.
The useful artifact is an immutable skill package accompanied by source, simulator, verifier,
repair, replay, support, and admission provenance.

## Claim gates

1. DSV4 drafts an executable skill from an instrument source bundle.
2. A simulator and independent physical gate admit the right draft and reject the wrong one.
3. DSV4 causally uses execution evidence to repair a failed draft.
4. The frozen method clears the same rubric across held-out instrument families.
5. Simulated deployment drift produces a staged, regression-safe evolution proposal.

Passing a later gate requires all earlier gates. A simulator-only result never establishes
unsupervised real-hardware operation.

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
