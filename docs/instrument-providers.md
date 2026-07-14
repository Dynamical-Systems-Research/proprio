# Instrument providers

An instrument provider is a normal Python distribution. Installation makes its namespaced
instruments available to Proprio; it does not qualify hardware or admit a skill.

Publish one entry point per provider:

```toml
[project]
name = "acme-microscope-provider"
version = "1.0.0"
dependencies = ["proprio>=0.4,<0.5"]

[project.entry-points."proprio.instrument_providers"]
"acme.microscope" = "acme_microscope:instrument_provider"
```

The function returns an `InstrumentProvider`. Its `provider_version` must equal the installed
distribution version, and every instrument ID must begin with `<provider_id>.`.

```python
from proprio.instrument_plugins import InstrumentProvider, ProviderInstrument


def instrument_provider():
    return InstrumentProvider(
        api_version="1",
        provider_id="acme.microscope",
        provider_version="1.0.0",
        runtime_kind="external",
        instruments={
            "acme.microscope.flake-search": ProviderInstrument(
                instrument_id="acme.microscope.flake-search",
                family="optical_microscopy",
                source_path=SOURCE,
                upstream_revision=SIMULATOR_REVISION,
                allowed_methods=frozenset({"reset", "move", "capture"}),
                controller_factory=controller_factory,
                verifier=verify_trace,
                simulator_path=simulator_path,
                verifier_path=VERIFIER_SOURCE,
                acquisition_conditions=ACQUISITION,
                visible_conditions=VISIBLE,
                locked_conditions=LOCKED,
                evolution_conditions=EVOLUTION,
            )
        },
    )
```

`controller_factory(scenario, parameters)` returns a fresh controller with a public `trace` and
`telemetry()` method. `verifier(trace, telemetry)` returns `GateCheck` values. Candidate code can
call only `allowed_methods`; imports, direct simulator-state reads, and verifier access are rejected.
If the controller owns transport resources, expose `close()`; Proprio finalizes it after every
outcome. `evolution_conditions` may be empty for a qualified skill, but publication requires them
for a staged skill.
Adapters should raise `InstrumentRuntimeUnavailable` for transport or simulator outages. These,
standard connection/timeout errors, malformed telemetry, missing verifier code, and verifier
exceptions produce `HOLD`; candidate procedure errors remain `REJECT`.

Proprio reads entry-point metadata without importing provider code, then imports only the provider
selected by the requested namespaced instrument. It rejects incompatible APIs, provider/package
version mismatches, namespace collisions, incomplete contracts, and mismatched instrument,
scenario, simulator, verifier, or candidate hashes.

After installation, use the existing loop:

```bash
proprio inspect-source --instrument acme.microscope.flake-search
proprio execute-candidate --instrument acme.microscope.flake-search \
  --candidate-dir runs/candidate --output-dir runs/visible
proprio verify-locked --instrument acme.microscope.flake-search \
  --candidate-dir runs/candidate --output-dir runs/locked
```

Provider availability, simulation evidence, skill publication, and real-hardware qualification are
separate states. A provider cannot publish or self-admit a skill.

## Reproduce the OpenFlexure provider

The OpenFlexure server remains a separate native simulator process. Pin and start it before running
`publish-skills`:

```bash
git clone https://gitlab.com/openflexure/openflexure-microscope-server \
  /tmp/proprio-candidates/openflexure-microscope-server
git -C /tmp/proprio-candidates/openflexure-microscope-server checkout \
  d26b93e1be1093e9d696b634dd1f7dde3bb7142a
cd /tmp/proprio-candidates/openflexure-microscope-server
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python --editable . python-gitlab
.venv/bin/python pull_webapp.py -b v3
.venv/bin/openflexure-microscope-server -c ofm_config_simulation.json \
  --host 127.0.0.1 --port 5100
```

In another shell, install Proprio's client dependencies with `uv sync --extra openflexure`, then run
the normal interface or `uv run proprio publish-skills --root .`. A missing checkout, wrong revision,
unreachable server, missing raw image evidence, or verifier failure produces `HOLD`.
