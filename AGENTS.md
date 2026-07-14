# AGENTS.md — Proprio

Proprio turns an instrument's documentation into a verified operating skill. An agent drafts the
skill from the instrument source alone. An independent simulator and physical checks the agent
cannot see or change decide what enters the skill library. Verified in simulation. Hardware
validation remains separate.

This is the operating guide for any coding agent in this repo. The human quickstart and
published-skill table are in `README.md`; the method and results are published at
https://dynamicalsystems.ai/blog/simulator-verified-skill-acquisition.

## Setup

Python 3.12 or 3.13, managed by `uv`.

```bash
uv sync --locked --extra dev --extra simulators
```

The instrument adapters expect pinned simulator checkouts under `/tmp/proprio-candidates`
(North-Cytation, helao-pub, self-driving-lab-demo, each at a fixed SHA). The exact clone commands
are in `.github/workflows/ci.yml` under "Check out pinned simulators" — run those before
`execute-candidate` or `verify-locked` against an instrument.

## Check your work

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run proprio publish-skills --root .
```

CI runs those three, then regenerates evidence with the batteries (`procedural-battery`,
`metrology --cases-per-class 300`, `support-battery`, `composition-battery`, `skill-admission`,
`cross-family-freeze`) and `evidence-manifest`. A change is not done until ruff and pytest pass
locally.

## The skill-acquisition loop

Any agent that edits files and runs commands can drive Proprio. The loop is six CLI commands, also
importable from `proprio.interface`:

| Command | interface fn | Role |
| --- | --- | --- |
| `proprio inspect-source` | `inspect_source` | Emit the instrument source bundle and controller contract. The only sanctioned view of the instrument while drafting. |
| `proprio execute-candidate` | `execute_candidate` | Run the candidate in the visible simulator; records an immutable attempt. |
| `proprio read-visible-evidence` | `read_visible_evidence` | Return the visible checks and an ADMIT, REJECT, or HOLD decision. |
| `proprio verify-locked` | `verify_locked` | Run the independently held conditions, never seen during drafting. |
| `proprio stage-evolution` | `stage_evolution` | Stage a proposal only if it passes a changed condition and replays its parent's admitting behavior. |
| `proprio evidence-manifest` | — | Recompute the content-addressed manifest over the repo. |

The battery and reference commands (`metrology`, `composition-battery`, `skill-admission`,
`procedural-battery`, `support-battery`, `cross-family-freeze`/`-session`/`-panel`) regenerate
published evidence. See `README.md` and CI.

## Rules that keep the results valid

- **Draft blind.** When you draft or repair a skill, use only the `inspect-source` bundle and the
  controller contract it names. Do not read `skills/`, verifier code, locked conditions, or
  `artifacts/evidence/`. Admission is held outside the model on purpose. Reading the answer key
  voids the result.
- **Evidence is immutable.** `artifacts/evidence/`, `catalog.json`, and the manifests are
  content-addressed and hash-bound. Never hand-edit them. Regenerate the compact skill records with
  `proprio publish-skills` and research evidence from pinned seeds. Inspect the per-class breakdown,
  not an aggregate pass rate.
- **Do not prune verified skills for a research release.** The installable library and the research
  evidence surface are separate. Keep every verified package in the flat `skills/<skill-name>/`
  namespace with `SKILL.md`, `agents/openai.yaml`, references, and reusable scripts.
- **Keep the remote usage-focused.** Do not commit a `cassettes/` directory, raw model
  conversations, run logs, or a duplicate technical report. Generate transient records under
  `runs/`; publish research narrative on the canonical blog. Release cleanup includes every
  branch and tag, not only the current tree: `git rev-list --objects --branches --tags
  --remotes=origin` must contain no path under `cassettes/` before a release is called clean.
  Local application refs such as `refs/codex/*` are not part of the published release surface.
- **Never tune a threshold to pass.** Preregistered thresholds, including the metrology battery, are
  fixed. Do not adjust one to make a run pass.
- **No judgment in operation records.** Operation records carry no phase, material, or
  scientific-decision claim. The schema firewall rejects a `judgment` key at any depth. Keep it that
  way.
- **Hardware fails closed.** Real-hardware adapters stay unavailable until their separate
  qualification artifacts pass. The simulation claim does not extend to hardware.
- **Installed providers extend instruments, not admission authority.** Discover
  `proprio.instrument_providers` without importing provider code, then lazily load only the provider
  selected by a namespaced instrument ID. Reject API, version, namespace, and evidence-identity
  mismatches. Installation makes an instrument available; simulator qualification, hardware
  validation, and skill admission remain separate Proprio decisions.
- **One verified-skill publication path.** Every `simulation_qualified` or `simulation_staged`
  package must name a provider instrument and regenerate its compact record through the common
  inspect, execute, visible-evidence, locked-verification, and registered-evolution runtime.
  `publish-skills` must fail on any non-reference exception. A `reference` package is explicitly
  outside the verified-skill claim until it has a complete executable provider.
- **Keep native replay out of standard CI.** Standard CI covers the provider contract and fast
  interface tests. Run the full pinned OpenFlexure `publish-skills` replay only through the manual
  release-validation workflow or explicitly during a release.

## Conventions

- Ruff is linter and formatter: line length 100, target `py312`, double quotes, space indent, lint
  set `E,F,I,B,UP,RUF`. `artifacts/` and `skills/` are excluded from ruff.
- Evidence JSON is written canonically so records are byte-identical across runs. Use
  `proprio.artifacts.write_canonical_json`; do not format evidence by hand.
- Every schema, verifier, fault class, and CLI path has a test. Add or update one with any change to
  those surfaces.

## Repository map

- `src/proprio` — persistent agent, bounded runtime, instrument adapters, verifiers, gates, CLI.
- `sources` — the documentation shown to the model.
- `skills` — the flat, installable public library: `SKILL.md`, `agents/openai.yaml`, focused
  references, reusable code under `scripts/`, and a compact verification record.
- `artifacts/evidence` — focused metrology and verification evidence.
- `catalog.json` — the content-addressed skill catalog. `schemas/` — the skill-package schema.
- `tests` — one suite per verifier, schema, fault class, and CLI path.

## Pull requests

Follow `CONTRIBUTING.md`: tests for every schema, verifier, fault class, and CLI path; `ruff check`,
`ruff format --check`, and `pytest` green; evidence regenerated from pinned seeds. Do not tune
preregistered thresholds and do not add decision claims to operation records.

## Read next

- https://dynamicalsystems.ai/blog/simulator-verified-skill-acquisition — the published findings.
- `catalog.json` — what has been admitted, and the records that admitted it.
