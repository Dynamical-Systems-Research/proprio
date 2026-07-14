# Contributing

Proprio accepts changes that preserve its evidence and claim boundaries.

Before opening a change:

1. Keep every published package at `skills/<skill-name>/` with `SKILL.md`,
   `agents/openai.yaml`, compact references, and reusable code under `scripts/` when needed.
2. Run `uv run proprio publish-skills --root .`; never hand-edit `catalog.json` or a package's
   `references/verification.json`.
3. Add or update tests for every schema, verifier, fault class, and CLI path.
4. Run `uv run ruff check .`, `uv run ruff format --check .`, and
   `uv run pytest`.
5. Regenerate affected evidence artifacts from pinned seeds and inspect the
   per-class breakdown rather than relying on an aggregate pass rate.
6. Do not tune a preregistered threshold against the metrology battery.
7. Do not add scientific judgment or decision claims to operation records.

The installable library is the release surface. Do not add raw agent conversations or execution
logs to a skill package. Keep only the minimal code, controller contract, and compact verification
record needed to use, reproduce, or extend the procedure.

Real hardware is outside the simulation qualification claim. Hardware adapters must fail
closed and remain unavailable until their separate qualification artifacts pass.
