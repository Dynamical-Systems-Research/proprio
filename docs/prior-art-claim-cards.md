# Prior-art claim cards

These cards separate interaction, adaptation, hardware, statistics, and limitations before a
comparison is allowed into Proprio's public language. They are evidence constraints, not a
novelty table.

## Agentic AI X-ray scientist

Primary source: Chen et al., [“An agentic artificially intelligent X-ray
scientist”](https://www.nature.com/articles/s42256-026-01261-5), *Nature Machine
Intelligence* (2026), especially “Virtual beamline experiments,” “Real-world beamline
experiments,” and “Limitations.”

- Demonstrated mechanism: a tool-using LLM plans, executes, observes, and revises diffraction
  alignment through a structured interface and persistent experiment state.
- Interaction environment: a virtual six-circle beamline followed by experiments at a real
  synchrotron beamline.
- Adaptation loop: iterative simulator interaction is direct and automatic in the virtual
  experiments. In the real experiment, the agent detected an approximately 1.22° eta offset,
  updated the alignment, and reused the correction for a second reflection.
- Hardware involvement: real commands were relayed by a human for facility safety, then
  executed without modification. That is real instrument adaptation, not autonomous hardware
  actuation.
- Statistical support: the simulation evaluation used ten independent runs per evaluated
  model with randomized motor offsets.
- Author-stated limitation: real-beamline trials were limited; the paper explicitly says the
  offset result should not be interpreted as a statistically established capability.

Implication for Proprio: iterative simulator interaction and adaptation are prior art. The
incremental claim must instead test whether a frozen, reusable skill-acquisition method repairs
candidate control programs from independent physical evidence across held-out instrument
families and prevents the agent from promoting its own mistakes.

## AI agents that learn on the job

Primary source: Liu et al., [“Operating advanced scientific instruments with AI agents that
learn on the job”](https://www.nature.com/articles/s41524-026-02005-0), *npj Computational
Materials* (2026), especially “Multi-agent framework,” “Teachability,” the two instrument
demonstrations, and “Discussion.”

- Demonstrated mechanism: a human-in-the-loop multi-agent system writes and reviews control
  code, invokes bounded instrument functions, and stores reusable feedback memories.
- Interaction environment: an X-ray nanoprobe and a robotic thin-film synthesis platform.
- Adaptation loop: human instructions are stored as input-output examples in a vector database
  and retrieved for related future tasks; the system improves from reusable human feedback.
- Hardware involvement: the paper demonstrates real scientific-instrument operation with
  deterministic low-level control and human approval or oversight around execution.
- Statistical support: the paper evaluates function calling, action ordering, code quality,
  correctness, execution, repeatability, and reproducibility; benefits are strongest where
  textual or procedural feedback can correct the task.
- Author-stated limitation: low-level action spaces remain restricted and validated, new
  procedures or instruments must be taught, and inherent visual-reasoning limits are not
  removed by feedback memory.

Implication for Proprio: reusable operational memory and real instrument control are prior art.
The paper does not establish autonomous simulator-grounded skill repair or independent
physics-gated promotion, so those mechanisms require their own controlled evidence.

## Public comparison rule

Proprio does not claim that prior systems lack adaptation, instrument operation, memory, or
simulation. Its simulator-only question is narrower: can a frozen method acquire executable
procedural capability from public instrument sources, causally repair failures from simulator
and verifier evidence, generalize to instrument families absent from method development, and
stage later evolution without letting model self-judgment override independent gates?
