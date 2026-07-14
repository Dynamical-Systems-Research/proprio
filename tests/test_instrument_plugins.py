from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from proprio.instrument_plugins import (
    ENTRY_POINT_GROUP,
    InstrumentProvider,
    LoadedProvider,
    ProviderIdentity,
    ProviderInstrument,
    build_instrument_registry,
    discover_provider_metadata,
    instrument_registry,
)
from proprio.instrument_types import GateCheck, SimulationScenario
from proprio.instruments import instrument_ids
from proprio.interface import (
    candidate_from_directory,
    execute_candidate,
    inspect_source,
    verify_locked,
)
from proprio.skill_search import DebugCondition


class FakeController:
    def __init__(self, scenario: SimulationScenario) -> None:
        self.scenario = scenario
        self.trace: list[dict[str, Any]] = []
        self._measured = False

    def reset(self) -> None:
        if self.scenario is SimulationScenario.UNAVAILABLE:
            raise RuntimeError("simulator unavailable")
        self.trace.append({"operation": "reset"})

    def measure(self) -> dict[str, float]:
        self._measured = True
        self.trace.append({"operation": "measure"})
        return {"value": 1.0}

    def telemetry(self) -> dict[str, bool]:
        return {"measured": self._measured}


def _fake_verifier(
    _trace: tuple[dict[str, Any], ...], telemetry: dict[str, Any]
) -> tuple[GateCheck, ...]:
    return (
        GateCheck(
            check_id="measurement-produced",
            passed=telemetry["measured"] is True,
            evidence={"measured": telemetry["measured"]},
        ),
    )


def _condition(condition_id: str, scenario: SimulationScenario) -> DebugCondition:
    return DebugCondition(condition_id=condition_id, scenario=scenario, repetitions=1)


def _fake_provider(
    source_path: Path, *, provider_id: str = "example.measurement"
) -> InstrumentProvider:
    instrument_id = f"{provider_id}.fake"
    instrument = ProviderInstrument(
        instrument_id=instrument_id,
        family="test_measurement",
        source_path=source_path,
        upstream_revision="test-revision",
        allowed_methods=frozenset({"reset", "measure"}),
        controller_factory=lambda scenario, _parameters: FakeController(scenario),
        verifier=_fake_verifier,
        simulator_path=lambda: Path(__file__),
        verifier_path=Path(__file__),
        acquisition_conditions=(_condition("acquire", SimulationScenario.NOMINAL),),
        visible_conditions=(_condition("visible", SimulationScenario.NOMINAL),),
        locked_conditions=(_condition("locked", SimulationScenario.REPAIR),),
        evolution_conditions=(_condition("drift", SimulationScenario.DRIFT),),
    )
    return InstrumentProvider(
        api_version="1",
        provider_id=provider_id,
        provider_version="2.3.4",
        instruments={instrument_id: instrument},
        runtime_kind="test",
    )


@dataclass
class FakeDistribution:
    version: str = "2.3.4"

    @property
    def metadata(self) -> dict[str, str]:
        return {"Name": "example-provider"}


class FakeEntryPoint:
    group = ENTRY_POINT_GROUP

    def __init__(self, provider: InstrumentProvider) -> None:
        self.name = provider.provider_id
        self.value = "example_provider:instrument_provider"
        self.dist = FakeDistribution()
        self.provider = provider
        self.loads = 0

    def load(self) -> Any:
        self.loads += 1
        return lambda: self.provider


def _loaded(provider: InstrumentProvider) -> LoadedProvider:
    return LoadedProvider(
        provider=provider,
        identity=ProviderIdentity(
            api_version="1",
            provider_id=provider.provider_id,
            provider_version=provider.provider_version,
            distribution="example-provider",
            distribution_version="2.3.4",
            entry_point="example_provider:instrument_provider",
        ),
    )


def test_discovery_does_not_import_installed_provider(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    entry_point = FakeEntryPoint(_fake_provider(source))

    discovered = discover_provider_metadata((entry_point,))

    assert entry_point.loads == 0
    assert discovered[0].provider_id == "example.measurement"
    assert discovered[0].distribution_version == "2.3.4"


def test_only_selected_provider_is_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    selected = FakeEntryPoint(_fake_provider(source))
    inactive = FakeEntryPoint(_fake_provider(source, provider_id="untrusted.shadow"))

    discovered = discover_provider_metadata((selected, inactive))
    monkeypatch.setattr("proprio.instrument_plugins._installed_metadata", lambda: discovered)
    instrument_registry.cache_clear()

    registry = instrument_registry("example.measurement.fake")

    assert selected.loads == 1
    assert inactive.loads == 0
    assert [item.provider.provider_id for item in registry.providers] == ["example.measurement"]
    instrument_registry.cache_clear()


def test_incompatible_api_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    provider = replace(_fake_provider(source), api_version="2")
    entry_point = FakeEntryPoint(provider)

    discovered = discover_provider_metadata((entry_point,))
    monkeypatch.setattr("proprio.instrument_plugins._installed_metadata", lambda: discovered)
    instrument_registry.cache_clear()
    with pytest.raises(ValueError, match="incompatible provider API"):
        instrument_registry("example.measurement.fake")
    instrument_registry.cache_clear()


def test_provider_version_must_match_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    provider = replace(_fake_provider(source), provider_version="9.9.9")
    entry_point = FakeEntryPoint(provider)
    discovered = discover_provider_metadata((entry_point,))
    monkeypatch.setattr("proprio.instrument_plugins._installed_metadata", lambda: discovered)
    instrument_registry.cache_clear()

    with pytest.raises(ValueError, match="provider/distribution version mismatch"):
        instrument_registry("example.measurement.fake")
    instrument_registry.cache_clear()


def test_duplicate_instrument_ids_fail_at_registry_startup(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    first = _fake_provider(source)
    second = replace(
        _fake_provider(source, provider_id="example.second"),
        instruments=first.instruments,
    )

    with pytest.raises(ValueError, match=r"duplicate instrument id: example\.measurement\.fake"):
        build_instrument_registry((_loaded(first), _loaded(second)))


def test_provider_evaluation_binds_existing_evidence_hashes(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    registry = build_instrument_registry((_loaded(_fake_provider(source)),))

    gate = registry.evaluate(
        "example.measurement.fake",
        "def run(controller):\n    controller.reset()\n    return controller.measure()\n",
    )

    assert gate.verdict == "ADMIT"
    assert gate.simulator_sha256
    assert gate.verifier_sha256
    identity = registry.provider_identity("example.measurement.fake")
    assert identity.distribution == "example-provider"
    assert identity.distribution_version == "2.3.4"


def test_mismatched_provider_evidence_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    registry = build_instrument_registry((_loaded(_fake_provider(source)),))
    instrument_id = "example.measurement.fake"
    from proprio.instrument_plugins import evaluate_controller_skill as evaluate

    def wrong_evidence(*args: Any, **kwargs: Any) -> Any:
        return evaluate(*args, **kwargs).model_copy(update={"family": "wrong-family"})

    monkeypatch.setattr("proprio.instrument_plugins.evaluate_controller_skill", wrong_evidence)
    gate = registry.evaluate(
        instrument_id,
        "def run(controller):\n    controller.reset()\n    return controller.measure()\n",
    )

    assert gate.verdict == "HOLD"
    assert "evidence identity mismatch: family" in (gate.runtime_error or "")


def test_verifier_exception_holds_instead_of_escaping(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    provider = _fake_provider(source)
    instrument_id = "example.measurement.fake"

    def broken_verifier(_trace: Any, _telemetry: Any) -> tuple[GateCheck, ...]:
        raise RuntimeError("verifier failed")

    broken = replace(provider.instruments[instrument_id], verifier=broken_verifier)
    provider = replace(provider, instruments={instrument_id: broken})
    registry = build_instrument_registry((_loaded(provider),))
    gate = registry.evaluate(
        instrument_id,
        "def run(controller):\n    controller.reset()\n    return controller.measure()\n",
    )

    assert gate.verdict == "HOLD"
    assert gate.status == "unavailable"
    assert gate.checks[-1].check_id == "verifier-execution"
    assert gate.checks[-1].passed is False


def test_transport_failure_holds_instead_of_rejecting(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    provider = _fake_provider(source)
    instrument_id = "example.measurement.fake"

    class DisconnectedController(FakeController):
        def measure(self) -> dict[str, float]:
            raise ConnectionError("simulator transport lost")

    broken = replace(
        provider.instruments[instrument_id],
        controller_factory=lambda scenario, _parameters: DisconnectedController(scenario),
    )
    registry = build_instrument_registry(
        (_loaded(replace(provider, instruments={instrument_id: broken})),)
    )
    gate = registry.evaluate(
        instrument_id,
        "def run(controller):\n    controller.reset()\n    return controller.measure()\n",
    )

    assert gate.verdict == "HOLD"
    assert gate.checks[0].check_id == "simulator-runtime"


@pytest.mark.parametrize("failure", ["missing", "malformed"])
def test_verifier_infrastructure_failure_holds(tmp_path: Path, failure: str) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    provider = _fake_provider(source)
    instrument_id = "example.measurement.fake"
    definition = provider.instruments[instrument_id]
    if failure == "missing":
        definition = replace(definition, verifier_path=tmp_path / "missing-verifier.py")
    else:
        definition = replace(definition, verifier=lambda _trace, _telemetry: None)  # type: ignore[arg-type]
    registry = build_instrument_registry(
        (_loaded(replace(provider, instruments={instrument_id: definition})),)
    )

    gate = registry.evaluate(
        instrument_id,
        "def run(controller):\n    controller.reset()\n    return controller.measure()\n",
    )

    assert gate.verdict == "HOLD"
    assert gate.status == "unavailable"


def test_agent_code_cannot_import_verifier(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    registry = build_instrument_registry((_loaded(_fake_provider(source)),))

    gate = registry.evaluate(
        "example.measurement.fake",
        "import proprio\ndef run(controller):\n    return {}\n",
    )

    assert gate.verdict == "REJECT"
    assert gate.checks[0].check_id == "static-safety"


def test_provider_runs_public_agent_interface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\nUse reset, then measure.\n", encoding="utf-8")
    registry = build_instrument_registry((_loaded(_fake_provider(source)),))
    monkeypatch.setattr(
        "proprio.instruments.instrument_registry", lambda _instrument=None: registry
    )
    instrument_id = "example.measurement.fake"

    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    (candidate_dir / "SKILL.md").write_text(
        "---\nname: fake-measurement\ndescription: Test provider.\n---\n\n# Run\nMeasure once.\n",
        encoding="utf-8",
    )
    (candidate_dir / "skill.py").write_text(
        "def run(controller):\n"
        "    controller.reset()\n"
        "    result = controller.measure()\n"
        "    return result\n",
        encoding="utf-8",
    )

    inspection = inspect_source(instrument_id)
    candidate = candidate_from_directory(instrument_id, candidate_dir, agent="test")
    visible = execute_candidate(instrument_id, candidate, output_dir=tmp_path / "visible")
    locked = verify_locked(candidate, output_dir=tmp_path / "locked")

    assert inspection["controller_methods"] == ["measure", "reset"]
    assert "locked_conditions" not in inspection
    assert "verifier" not in inspection
    assert visible["decision"] == "ADMIT"
    assert locked["decision"] == "ADMIT"


def test_repository_entry_points_expose_all_namespaced_instruments() -> None:
    assert len(instrument_ids()) == 11
    assert all(instrument_id.startswith("proprio.") for instrument_id in instrument_ids())


def test_provider_finalizes_controller_after_static_rejection(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("# Fake controller\n", encoding="utf-8")
    provider = _fake_provider(source)
    instrument_id = "example.measurement.fake"
    controllers: list[FakeController] = []

    class ClosingController(FakeController):
        closed = False

        def close(self) -> None:
            self.closed = True

    def factory(scenario: SimulationScenario, _parameters: Any) -> ClosingController:
        controller = ClosingController(scenario)
        controllers.append(controller)
        return controller

    definition = replace(provider.instruments[instrument_id], controller_factory=factory)
    registry = build_instrument_registry(
        (_loaded(replace(provider, instruments={instrument_id: definition})),)
    )

    gate = registry.evaluate(instrument_id, "import os\ndef run(controller):\n    return {}\n")

    assert gate.verdict == "REJECT"
    assert controllers[0].closed is True
