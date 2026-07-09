# Contributing

Proprio accepts changes that preserve its evidence and claim boundaries.

Before opening a change:

1. Add or update tests for every schema, verifier, fault class, and CLI path.
2. Run `uv run ruff check .`, `uv run ruff format --check .`, and
   `uv run pytest`.
3. Regenerate affected evidence artifacts from pinned seeds and inspect the
   per-class breakdown rather than relying on an aggregate pass rate.
4. Do not tune a preregistered threshold against the metrology battery.
5. Do not add scientific judgment or decision claims to operation records.

Real hardware is outside the v0.1 validation claim. Hardware adapters must fail
closed and remain unavailable until their separate qualification artifacts pass.

