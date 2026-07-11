"""External simulator runtimes for cross-family qualification.

The model sees only the frozen source bundle and the documented controller surface.
Upstream simulator code and the independent verifier remain outside the agent loop.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import math
import os
import random
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stdout
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from proprio.artifacts import source_sha256
from proprio.instrument_qualification import evaluate_controller_skill
from proprio.instrument_types import CandidatePackage, GateCheck, HardGateResult, SimulationScenario
from proprio.skill_search import (
    DebugCondition,
    FixturePreflightReport,
    PreflightCase,
    run_fixture_preflight,
)

ROOT = Path(__file__).resolve().parents[2]


class ExternalRuntimeUnavailable(RuntimeError):
    """Raised when a pinned external simulator checkout cannot be loaded."""


class ExternalController:
    """Common trace and availability behavior for external simulator adapters."""

    def __init__(self, scenario: SimulationScenario, condition: Mapping[str, float]) -> None:
        self.scenario = scenario
        self.condition = dict(condition)
        self.trace: list[dict[str, Any]] = []
        self.unavailable = scenario is SimulationScenario.UNAVAILABLE

    def _require_available(self) -> None:
        if self.unavailable:
            raise ExternalRuntimeUnavailable("external simulator is unavailable")

    def _log(self, operation: str, **values: Any) -> None:
        self.trace.append({"sequence": len(self.trace), "operation": operation, **values})

    def telemetry(self) -> dict[str, Any]:
        raise NotImplementedError


def _external_root(env_name: str, fallback: Path) -> Path:
    root = Path(os.environ.get(env_name, fallback)).expanduser().resolve()
    if not root.is_dir():
        raise ExternalRuntimeUnavailable(f"{env_name} does not identify a simulator checkout")
    return root


def _load_module(module_name: str, path: Path, *, search_path: Path | None = None) -> Any:
    if not path.is_file():
        raise ExternalRuntimeUnavailable(f"external simulator module is missing: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ExternalRuntimeUnavailable(f"cannot load external simulator module: {path}")
    module = importlib.util.module_from_spec(spec)
    inserted = False
    if search_path is not None and str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))
        inserted = True
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(str(search_path))
    return module


@lru_cache(maxsize=1)
def _north_module() -> Any:
    _, simulator_path = _north_paths()
    return _load_module(
        "proprio_north_calibration",
        simulator_path,
        search_path=simulator_path.parent,
    )


@lru_cache(maxsize=1)
def _helao_module() -> Any:
    _, simulator_path = _helao_paths()
    if not hasattr(np, "int"):
        np.int = int  # type: ignore[attr-defined]
    module = _load_module("proprio_helao_gamry", simulator_path)
    # The pinned simulator defines small JIT functions inside each call. Disabling
    # compilation changes only execution strategy and avoids recompiling identical
    # finite-difference kernels thousands of times during metrology.
    module.jit = lambda **_kwargs: lambda function: function
    return module


@lru_cache(maxsize=128)
def _cached_cv(
    initial_v: float,
    lower_v: float,
    upper_v: float,
    final_v: float,
    scan_rate: float,
    cycles: int,
    sample_interval: float,
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    module = _helao_module()
    params = {
        "C": 1.0,
        "D": 1e-5,
        "etai": initial_v,
        "eta0": lower_v,
        "eta1": upper_v,
        "etaf": final_v,
        "v": scan_rate,
        "n": 1.0,
        "alpha": 0.5,
        "k0": 1e-2,
        "kc": 1e-3,
        "T": 298.15,
        "cyc": cycles,
        "daq": sample_interval,
    }
    time_s, potential_v, current_ma_cm2 = module.cvsim(params, 0.45)
    return (
        tuple(float(value) for value in time_s),
        tuple(float(value) for value in potential_v),
        tuple(float(value) for value in current_ma_cm2),
    )


@lru_cache(maxsize=1)
def _clslab_module() -> Any:
    root, simulator_path = _clslab_paths()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return _load_module("proprio_clslab_light", simulator_path, search_path=src)


def _north_paths() -> tuple[Path, Path]:
    root = _external_root("PROPRIO_NORTH_ROOT", Path("/tmp/proprio-candidates/North-Cytation"))
    protocol_dir = root / "sdl_pipette_calibration" / "protocols"
    return root, protocol_dir / "calibration_protocol_simulated.py"


def _helao_paths() -> tuple[Path, Path]:
    root = _external_root("PROPRIO_HELAO_ROOT", Path("/tmp/proprio-candidates/helao-pub"))
    return root, root / "driver" / "gamry_simulate.py"


def _clslab_paths() -> tuple[Path, Path]:
    root = _external_root(
        "PROPRIO_CLSLAB_ROOT", Path("/tmp/proprio-candidates/self-driving-lab-demo")
    )
    return root, root / "src" / "self_driving_lab_demo" / "demos" / "light.py"


class NorthPipetteController(ExternalController):
    """Adapter over North-Cytation's bundled pipette-calibration simulator."""

    def __init__(self, scenario: SimulationScenario, condition: Mapping[str, float]) -> None:
        super().__init__(scenario, condition)
        module = _north_module()
        self.protocol = module.SimulatedCalibrationProtocol()
        self.seed = int(self.condition.get("seed", 1731.0))
        self.liquid = {
            SimulationScenario.NOMINAL: "water",
            SimulationScenario.REPAIR: "glycerol",
            SimulationScenario.DRIFT: "glycerol",
            SimulationScenario.UNAVAILABLE: "water",
        }[scenario]
        self.state: dict[str, Any] | None = None
        self.rows: list[dict[str, Any]] = []
        self.cleaned = False
        self.constraints: list[str] = []
        self.last_params: dict[str, float] = {}
        self.target_ml = float(self.condition.get("target_ml", 0.05))
        self.delivery_scale = float(self.condition.get("delivery_scale", 1.0))

    def reset(self) -> None:
        self._require_available()
        random.seed(self.seed)
        np.random.seed(self.seed)
        with redirect_stdout(io.StringIO()):
            self.state = self.protocol.initialize(
                {"random_seed": self.seed, "experiment": {"liquid": self.liquid}}
            )
        self.rows = []
        self.cleaned = False
        self._log("reset", seed=self.seed, liquid=self.liquid)

    def sample_info(self) -> dict[str, Any]:
        self._require_available()
        info = {"liquid": self.liquid, "target_volume_ml": self.target_ml}
        self._log("sample_info", **info)
        return info

    def get_constraints(self, target_volume_ml: float) -> dict[str, Any]:
        self._require_available()
        with redirect_stdout(io.StringIO()):
            self.constraints = list(
                self.protocol.get_parameter_constraints(float(target_volume_ml))
            )
        payload = {"constraints": list(self.constraints)}
        self._log("get_constraints", target_volume_ml=float(target_volume_ml), **payload)
        return payload

    def measure(
        self,
        target_volume_ml: float,
        overaspirate_ml: float,
        aspirate_speed: float,
        wait_s: float,
        replicates: int,
    ) -> dict[str, Any]:
        self._require_available()
        if self.state is None:
            raise RuntimeError("reset must precede measurement")
        params = {
            "overaspirate_vol": float(overaspirate_ml) * self.delivery_scale,
            "aspirate_speed": float(aspirate_speed),
            "aspirate_wait_time": float(wait_s),
        }
        self.last_params = {
            **params,
            "commanded_overaspirate_vol": float(overaspirate_ml),
            "delivery_scale": self.delivery_scale,
        }
        with redirect_stdout(io.StringIO()):
            raw_rows = self.protocol.measure(
                self.state,
                float(target_volume_ml),
                params,
                int(replicates),
            )
        rows = [
            {
                key: value
                for key, value in row.items()
                if key not in {"actual_elapsed_s", "start_time", "end_time"}
            }
            for row in raw_rows
        ]
        self.rows.extend(rows)
        volumes = [float(row["volume"]) for row in rows]
        mean_ml = statistics.fmean(volumes)
        cv = statistics.stdev(volumes) / mean_ml if len(volumes) > 1 and mean_ml else math.inf
        payload = {
            "target_volume_ml": float(target_volume_ml),
            "mean_volume_ml": mean_ml,
            "relative_error": abs(mean_ml - float(target_volume_ml)) / float(target_volume_ml),
            "coefficient_of_variation": cv,
            "replicates": len(rows),
        }
        self._log("measure", **self.last_params, **payload)
        return payload

    def cleanup(self) -> None:
        self._require_available()
        if self.state is None:
            raise RuntimeError("reset must precede cleanup")
        with redirect_stdout(io.StringIO()):
            self.protocol.wrapup(self.state)
        self.cleaned = True
        self._log("cleanup")

    def telemetry(self) -> dict[str, Any]:
        return {
            "liquid": self.liquid,
            "target_volume_ml": self.target_ml,
            "rows": self.rows,
            "constraints": self.constraints,
            "last_params": self.last_params,
            "delivery_scale": self.delivery_scale,
            "cleaned": self.cleaned,
        }


class HelaoGamryController(ExternalController):
    """Adapter over HELAO's finite-difference Gamry cyclic-voltammetry simulator."""

    def __init__(self, scenario: SimulationScenario, condition: Mapping[str, float]) -> None:
        super().__init__(scenario, condition)
        _helao_module()
        self.connected = False
        self.disconnected = False
        default_maximum_scan_rate = {
            SimulationScenario.NOMINAL: 0.20,
            SimulationScenario.REPAIR: 0.10,
            SimulationScenario.DRIFT: 0.08,
            SimulationScenario.UNAVAILABLE: 0.20,
        }[scenario]
        self.maximum_scan_rate = float(
            self.condition.get("maximum_scan_rate_v_s", default_maximum_scan_rate)
        )
        default_zero_offset = {
            SimulationScenario.NOMINAL: 0.0,
            SimulationScenario.REPAIR: 0.0,
            SimulationScenario.DRIFT: 0.03,
            SimulationScenario.UNAVAILABLE: 0.0,
        }[scenario]
        self.zero_offset_v = float(self.condition.get("zero_offset_v", default_zero_offset))
        self.potential_scale = float(self.condition.get("potential_scale", 1.0))
        self.subsequent_potential_scale = float(
            self.condition.get("subsequent_potential_scale", self.potential_scale)
        )
        self.potential_cycles = 0
        self.last_potential_scale = self.potential_scale
        self.compensation_v = 0.0
        self.data: dict[str, list[float]] = {}
        self.parameters: dict[str, float] = {}
        self.violations: list[str] = []

    def reset(self) -> None:
        self._require_available()
        self.connected = False
        self.disconnected = False
        self.data = {}
        self.parameters = {}
        self.violations = []
        self.compensation_v = 0.0
        self.potential_cycles = 0
        self.last_potential_scale = self.potential_scale
        self._log("reset")

    def connect(self) -> None:
        self._require_available()
        self.connected = True
        self.disconnected = False
        self._log("connect")

    def get_limits(self) -> dict[str, float]:
        self._require_available()
        payload = {"maximum_scan_rate_v_s": self.maximum_scan_rate}
        self._log("get_limits", **payload)
        return payload

    def read_zero_offset(self) -> float:
        self._require_available()
        self._log("read_zero_offset", offset_v=self.zero_offset_v)
        return self.zero_offset_v

    def set_zero_compensation(self, offset_v: float) -> None:
        self._require_available()
        self.compensation_v = float(offset_v)
        self._log("set_zero_compensation", offset_v=self.compensation_v)

    def potential_cycle(
        self,
        initial_v: float,
        lower_v: float,
        upper_v: float,
        final_v: float,
        scan_rate_v_s: float,
        cycles: int,
        sample_interval_v: float,
    ) -> dict[str, Any]:
        self._require_available()
        if not self.connected:
            raise RuntimeError("connect must precede potential_cycle")
        scan_rate = float(scan_rate_v_s)
        if scan_rate > self.maximum_scan_rate + 1e-12:
            self.violations.append("scan_rate_exceeds_limit")
        residual_offset = self.zero_offset_v - self.compensation_v
        time_s, potential_v, current_ma_cm2 = _cached_cv(
            float(initial_v) + residual_offset,
            float(lower_v) + residual_offset,
            float(upper_v) + residual_offset,
            float(final_v) + residual_offset,
            scan_rate,
            int(cycles),
            float(sample_interval_v),
        )
        self.parameters = {
            "initial_v": float(initial_v),
            "lower_v": float(lower_v),
            "upper_v": float(upper_v),
            "final_v": float(final_v),
            "scan_rate_v_s": scan_rate,
            "cycles": float(cycles),
            "sample_interval_v": float(sample_interval_v),
        }
        applied_scale = (
            self.potential_scale if self.potential_cycles == 0 else self.subsequent_potential_scale
        )
        self.potential_cycles += 1
        self.last_potential_scale = applied_scale
        scaled_potential = np.asarray(potential_v, dtype=float) * applied_scale
        self.data = {
            "time_s": np.asarray(time_s, dtype=float).tolist(),
            "potential_v": scaled_potential.tolist(),
            "current_ma_cm2": np.asarray(current_ma_cm2, dtype=float).tolist(),
        }
        payload = {
            "points": len(self.data["time_s"]),
            "potential_min_v": min(self.data["potential_v"]),
            "potential_max_v": max(self.data["potential_v"]),
            "current_min_ma_cm2": min(self.data["current_ma_cm2"]),
            "current_max_ma_cm2": max(self.data["current_ma_cm2"]),
        }
        self._log("potential_cycle", **self.parameters, **payload)
        return payload

    def disconnect(self) -> None:
        self._require_available()
        self.connected = False
        self.disconnected = True
        self._log("disconnect")

    def telemetry(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "disconnected": self.disconnected,
            "maximum_scan_rate_v_s": self.maximum_scan_rate,
            "zero_offset_v": self.zero_offset_v,
            "potential_scale": self.potential_scale,
            "subsequent_potential_scale": self.subsequent_potential_scale,
            "last_potential_scale": self.last_potential_scale,
            "potential_cycles": self.potential_cycles,
            "compensation_v": self.compensation_v,
            "parameters": self.parameters,
            "data": self.data,
            "violations": self.violations,
        }


class ClsLabLightController(ExternalController):
    """Adapter over CLSLab:Light's measured-basis spectral simulator."""

    def __init__(self, scenario: SimulationScenario, condition: Mapping[str, float]) -> None:
        super().__init__(scenario, condition)
        module = _clslab_module()
        self.simulator = module.SensorSimulatorLight()
        default_maximum_signal = {
            SimulationScenario.NOMINAL: 60_000.0,
            SimulationScenario.REPAIR: 30_000.0,
            SimulationScenario.DRIFT: 20_000.0,
            SimulationScenario.UNAVAILABLE: 60_000.0,
        }[scenario]
        self.maximum_signal = float(self.condition.get("maximum_signal", default_maximum_signal))
        self.subsequent_maximum_signal = float(
            self.condition.get("subsequent_maximum_signal", self.maximum_signal)
        )
        self.current_maximum_signal = self.maximum_signal
        default_gain_scale = {
            SimulationScenario.NOMINAL: 1.0,
            SimulationScenario.REPAIR: 1.0,
            SimulationScenario.DRIFT: 1.20,
            SimulationScenario.UNAVAILABLE: 1.0,
        }[scenario]
        self.gain_scale = float(self.condition.get("gain_scale", default_gain_scale))
        self.subsequent_gain_scale = float(
            self.condition.get("subsequent_gain_scale", self.gain_scale)
        )
        self.measurements = 0
        self.last_gain_scale = self.gain_scale
        self.config: dict[str, float] = {}
        self.rgb: dict[str, int] = {"R": 0, "G": 0, "B": 0}
        self.spectrum: dict[str, float] = {}
        self.dark: dict[str, float] = {}
        self.cleared = False

    def reset(self) -> None:
        self._require_available()
        self.config = {}
        self.rgb = {"R": 0, "G": 0, "B": 0}
        self.spectrum = {}
        self.dark = {}
        self.cleared = False
        self.measurements = 0
        self.last_gain_scale = self.gain_scale
        self.current_maximum_signal = self.maximum_signal
        self._log("reset")

    def get_limits(self) -> dict[str, float]:
        self._require_available()
        payload = {
            "maximum_signal": self.current_maximum_signal,
            "maximum_gain": 512.0,
            "maximum_atime": 255.0,
            "maximum_astep": 65_534.0,
        }
        self._log("get_limits", **payload)
        return payload

    def configure(self, atime: int, astep: int, gain: float) -> None:
        self._require_available()
        self.config = {"atime": int(atime), "astep": int(astep), "gain": float(gain)}
        self._log("configure", **self.config)

    def set_rgb(self, red: int, green: int, blue: int) -> None:
        self._require_available()
        self.rgb = {"R": int(red), "G": int(green), "B": int(blue)}
        self.cleared = False
        self._log("set_rgb", **self.rgb)

    def measure(self) -> dict[str, Any]:
        self._require_available()
        if not self.config:
            raise RuntimeError("configure must precede measurement")
        applied_gain_scale = (
            self.gain_scale if self.measurements == 0 else self.subsequent_gain_scale
        )
        self.measurements += 1
        self.last_gain_scale = applied_gain_scale
        self.current_maximum_signal = self.subsequent_maximum_signal
        parameters = {
            **self.rgb,
            "atime": self.config["atime"],
            "astep": self.config["astep"],
            "gain": self.config["gain"] * applied_gain_scale,
        }
        simulated = self.simulator.simulate_sensor_data(parameters)
        self.spectrum = {key: float(value) for key, value in simulated.items()}
        payload = {
            "channels": len(self.spectrum),
            "minimum_signal": min(self.spectrum.values()),
            "maximum_signal": max(self.spectrum.values()),
        }
        self._log("measure", **payload)
        return {**payload, "spectrum": dict(self.spectrum)}

    def clear(self) -> None:
        self._require_available()
        self.rgb = {"R": 0, "G": 0, "B": 0}
        parameters = {
            **self.rgb,
            "atime": self.config.get("atime", 100),
            "astep": self.config.get("astep", 999),
            "gain": self.config.get("gain", 1.0) * self.gain_scale,
        }
        simulated = self.simulator.simulate_sensor_data(parameters)
        self.dark = {key: float(value) for key, value in simulated.items()}
        self.cleared = True
        self._log("clear", maximum_dark=max(self.dark.values()))

    def telemetry(self) -> dict[str, Any]:
        return {
            "maximum_signal_limit": self.current_maximum_signal,
            "initial_maximum_signal_limit": self.maximum_signal,
            "subsequent_maximum_signal_limit": self.subsequent_maximum_signal,
            "gain_scale": self.gain_scale,
            "subsequent_gain_scale": self.subsequent_gain_scale,
            "last_gain_scale": self.last_gain_scale,
            "measurements": self.measurements,
            "config": self.config,
            "rgb": self.rgb,
            "spectrum": self.spectrum,
            "dark": self.dark,
            "cleared": self.cleared,
        }


Verifier = Callable[[str, str, Sequence[dict[str, Any]], dict[str, Any]], tuple[GateCheck, ...]]


def _order_check(trace: Sequence[dict[str, Any]], required: Sequence[str]) -> GateCheck:
    operations = [str(row.get("operation")) for row in trace]
    cursor = 0
    for operation in operations:
        if cursor < len(required) and operation == required[cursor]:
            cursor += 1
    return GateCheck(
        check_id="operation-order",
        passed=cursor == len(required),
        evidence={"required": list(required), "observed": operations},
    )


def verify_north(
    instrument_id: str,
    family: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    del instrument_id, family
    rows = telemetry.get("rows", [])
    target = float(telemetry.get("target_volume_ml", 0.0))
    volumes = [float(row["volume"]) for row in rows if "volume" in row]
    mean = statistics.fmean(volumes) if volumes else math.nan
    cv = statistics.stdev(volumes) / mean if len(volumes) > 1 and mean else math.inf
    relative_error = abs(mean - target) / target if target and math.isfinite(mean) else math.inf
    overaspirate = float(telemetry.get("last_params", {}).get("overaspirate_vol", math.inf))
    constraint_limit = 0.2 - target if target < 0.2 else 1.0 - target
    return (
        _order_check(trace, ("reset", "sample_info", "get_constraints", "measure", "cleanup")),
        GateCheck(
            check_id="replicate-count",
            passed=len(volumes) >= 3,
            evidence={"observed": len(volumes), "required": 3},
        ),
        GateCheck(
            check_id="volume-accuracy",
            passed=relative_error <= 0.04,
            evidence={"relative_error": relative_error, "maximum": 0.04, "mean_ml": mean},
        ),
        GateCheck(
            check_id="volume-repeatability",
            passed=cv <= 0.05,
            evidence={"coefficient_of_variation": cv, "maximum": 0.05},
        ),
        GateCheck(
            check_id="tip-capacity",
            passed=0.0 <= overaspirate <= constraint_limit,
            evidence={"overaspirate_ml": overaspirate, "maximum": constraint_limit},
        ),
        GateCheck(
            check_id="resource-release",
            passed=telemetry.get("cleaned") is True,
            evidence={"cleaned": telemetry.get("cleaned")},
        ),
    )


def verify_helao(
    instrument_id: str,
    family: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    del instrument_id, family
    data = telemetry.get("data", {})
    time_s = np.asarray(data.get("time_s", []), dtype=float)
    potential = np.asarray(data.get("potential_v", []), dtype=float)
    current = np.asarray(data.get("current_ma_cm2", []), dtype=float)
    params = telemetry.get("parameters", {})
    finite = bool(
        len(time_s) >= 64
        and len(time_s) == len(potential) == len(current)
        and np.all(np.isfinite(time_s))
        and np.all(np.isfinite(potential))
        and np.all(np.isfinite(current))
    )
    scan_rate = float(params.get("scan_rate_v_s", math.inf))
    maximum_scan_rate = float(telemetry.get("maximum_scan_rate_v_s", 0.0))
    # The qualification endpoints are fixed by the public task contract. They
    # must never be inferred from candidate-controlled command arguments.
    expected_low = -0.5
    expected_high = 0.5
    sweep_ok = bool(
        finite
        and abs(float(np.min(potential)) - expected_low) <= 0.02
        and abs(float(np.max(potential)) - expected_high) <= 0.02
    )
    bidirectional = bool(finite and float(np.min(current)) < 0.0 < float(np.max(current)))
    return (
        _order_check(
            trace,
            (
                "reset",
                "connect",
                "get_limits",
                "read_zero_offset",
                "set_zero_compensation",
                "potential_cycle",
                "disconnect",
            ),
        ),
        GateCheck(
            check_id="scan-rate-support",
            passed=scan_rate <= maximum_scan_rate and not telemetry.get("violations"),
            evidence={
                "scan_rate_v_s": scan_rate,
                "maximum_scan_rate_v_s": maximum_scan_rate,
                "violations": telemetry.get("violations", []),
            },
        ),
        GateCheck(
            check_id="cv-frame-integrity",
            passed=finite,
            evidence={"points": len(time_s), "finite": finite},
        ),
        GateCheck(
            check_id="potential-sweep-fidelity",
            passed=sweep_ok,
            evidence={
                "observed_min_v": float(np.min(potential)) if len(potential) else None,
                "observed_max_v": float(np.max(potential)) if len(potential) else None,
                "expected_min_v": expected_low,
                "expected_max_v": expected_high,
                "tolerance_v": 0.02,
            },
        ),
        GateCheck(
            check_id="redox-response",
            passed=bidirectional,
            evidence={
                "current_min_ma_cm2": float(np.min(current)) if len(current) else None,
                "current_max_ma_cm2": float(np.max(current)) if len(current) else None,
            },
        ),
        GateCheck(
            check_id="resource-release",
            passed=telemetry.get("disconnected") is True,
            evidence={"disconnected": telemetry.get("disconnected")},
        ),
    )


def verify_clslab(
    instrument_id: str,
    family: str,
    trace: Sequence[dict[str, Any]],
    telemetry: dict[str, Any],
) -> tuple[GateCheck, ...]:
    del instrument_id, family
    spectrum = [float(value) for value in telemetry.get("spectrum", {}).values()]
    dark = [float(value) for value in telemetry.get("dark", {}).values()]
    finite = bool(len(spectrum) == 8 and all(math.isfinite(value) for value in spectrum))
    maximum_signal = max(spectrum) if spectrum else math.inf
    minimum_signal = min(spectrum) if spectrum else -math.inf
    maximum_allowed = float(telemetry.get("maximum_signal_limit", 0.0))
    dark_maximum = max(dark) if dark else math.inf
    return (
        _order_check(trace, ("reset", "get_limits", "configure", "set_rgb", "measure", "clear")),
        GateCheck(
            check_id="spectral-frame-integrity",
            passed=finite,
            evidence={"channels": len(spectrum), "finite": finite},
        ),
        GateCheck(
            check_id="counting-range",
            passed=finite and minimum_signal >= 1.0 and maximum_signal <= maximum_allowed,
            evidence={
                "minimum_signal": minimum_signal,
                "maximum_signal": maximum_signal,
                "maximum_allowed": maximum_allowed,
            },
        ),
        GateCheck(
            check_id="dark-response",
            passed=len(dark) == 8 and dark_maximum <= 1e-9,
            evidence={"channels": len(dark), "maximum_dark": dark_maximum},
        ),
        GateCheck(
            check_id="resource-release",
            passed=telemetry.get("cleared") is True,
            evidence={"cleared": telemetry.get("cleared")},
        ),
    )


@dataclass(frozen=True)
class ExternalInstrumentDefinition:
    instrument_id: str
    family: str
    source_path: Path
    allowed_methods: frozenset[str]
    controller_type: type[ExternalController]
    verifier: Verifier
    simulator_path: Callable[[], Path]
    upstream_revision: str
    verifier_path: Path
    acquisition_conditions: tuple[DebugCondition, ...]
    visible_conditions: tuple[DebugCondition, ...]
    locked_conditions: tuple[DebugCondition, ...]
    evolution_conditions: tuple[DebugCondition, ...]


def _north_simulator_path() -> Path:
    return _north_paths()[1]


def _helao_simulator_path() -> Path:
    return _helao_paths()[1]


def _clslab_simulator_path() -> Path:
    return _clslab_paths()[1]


EXTERNAL_INSTRUMENTS: dict[str, ExternalInstrumentDefinition] = {
    "north-pipette-calibration": ExternalInstrumentDefinition(
        instrument_id="north-pipette-calibration",
        family="calibrated_liquid_delivery",
        source_path=ROOT / "sources/instruments/north-pipette-calibration/source.md",
        allowed_methods=frozenset(
            {"reset", "sample_info", "get_constraints", "measure", "cleanup"}
        ),
        controller_type=NorthPipetteController,
        verifier=verify_north,
        simulator_path=_north_simulator_path,
        upstream_revision="3f49b5faba803a4a5d22544aa2ea5923ec513e20",
        verifier_path=Path(__file__),
        acquisition_conditions=(
            DebugCondition(
                condition_id="acquire-water-50ul",
                scenario=SimulationScenario.NOMINAL,
                repetitions=3,
            ),
        ),
        visible_conditions=(
            DebugCondition(
                condition_id="water-50ul", scenario=SimulationScenario.NOMINAL, repetitions=3
            ),
            DebugCondition(
                condition_id="glycerol-delivery-drift",
                scenario=SimulationScenario.REPAIR,
                parameters=(("delivery_scale", 0.80),),
                repetitions=3,
            ),
        ),
        locked_conditions=(
            DebugCondition(
                condition_id="locked-glycerol-delivery-drift",
                scenario=SimulationScenario.DRIFT,
                parameters=(("delivery_scale", 0.78),),
                repetitions=3,
            ),
        ),
        evolution_conditions=(
            DebugCondition(
                condition_id="deployment-delivery-drift",
                scenario=SimulationScenario.DRIFT,
                parameters=(("delivery_scale", 0.40),),
                repetitions=3,
            ),
        ),
    ),
    "helao-gamry-cv": ExternalInstrumentDefinition(
        instrument_id="helao-gamry-cv",
        family="electrochemical_measurement",
        source_path=ROOT / "sources/instruments/helao-gamry-cv/source.md",
        allowed_methods=frozenset(
            {
                "reset",
                "connect",
                "get_limits",
                "read_zero_offset",
                "set_zero_compensation",
                "potential_cycle",
                "disconnect",
            }
        ),
        controller_type=HelaoGamryController,
        verifier=verify_helao,
        simulator_path=_helao_simulator_path,
        upstream_revision="d644716e17c40c2bdfce74d5ebe82a04ff70cc6a",
        verifier_path=Path(__file__),
        acquisition_conditions=(
            DebugCondition(
                condition_id="acquire-nominal-cv",
                scenario=SimulationScenario.NOMINAL,
                repetitions=3,
            ),
        ),
        visible_conditions=(
            DebugCondition(
                condition_id="nominal-cv", scenario=SimulationScenario.NOMINAL, repetitions=3
            ),
            DebugCondition(
                condition_id="potential-scale-drift",
                scenario=SimulationScenario.REPAIR,
                parameters=(("potential_scale", 0.90),),
                repetitions=3,
            ),
        ),
        locked_conditions=(
            DebugCondition(
                condition_id="locked-potential-scale-drift",
                scenario=SimulationScenario.DRIFT,
                parameters=(("potential_scale", 0.88),),
                repetitions=3,
            ),
        ),
        evolution_conditions=(
            DebugCondition(
                condition_id="deployment-potential-scale-drift",
                scenario=SimulationScenario.DRIFT,
                parameters=(
                    ("potential_scale", 0.90),
                    ("subsequent_potential_scale", 0.70),
                ),
                repetitions=3,
            ),
        ),
    ),
    "clslab-light-spectrometer": ExternalInstrumentDefinition(
        instrument_id="clslab-light-spectrometer",
        family="spectral_measurement",
        source_path=ROOT / "sources/instruments/clslab-light-spectrometer/source.md",
        allowed_methods=frozenset(
            {"reset", "get_limits", "configure", "set_rgb", "measure", "clear"}
        ),
        controller_type=ClsLabLightController,
        verifier=verify_clslab,
        simulator_path=_clslab_simulator_path,
        upstream_revision="34e4e8cd880bc7b788109d8a56da3f6fae978518",
        verifier_path=Path(__file__),
        acquisition_conditions=(
            DebugCondition(
                condition_id="acquire-nominal-detector",
                scenario=SimulationScenario.NOMINAL,
                repetitions=3,
            ),
        ),
        visible_conditions=(
            DebugCondition(
                condition_id="nominal-detector", scenario=SimulationScenario.NOMINAL, repetitions=3
            ),
            DebugCondition(
                condition_id="low-sensitivity-detector",
                scenario=SimulationScenario.REPAIR,
                parameters=(("maximum_signal", 60_000.0), ("gain_scale", 0.005)),
                repetitions=3,
            ),
        ),
        locked_conditions=(
            DebugCondition(
                condition_id="locked-gain-drift",
                scenario=SimulationScenario.DRIFT,
                parameters=(("maximum_signal", 60_000.0), ("gain_scale", 0.0045)),
                repetitions=3,
            ),
        ),
        evolution_conditions=(
            DebugCondition(
                condition_id="deployment-gain-drift",
                scenario=SimulationScenario.DRIFT,
                parameters=(
                    ("maximum_signal", 60_000.0),
                    ("subsequent_maximum_signal", 10_000.0),
                    ("gain_scale", 1.0),
                ),
                repetitions=3,
            ),
        ),
    ),
}


def load_external_source(instrument_id: str) -> tuple[str, str]:
    definition = EXTERNAL_INSTRUMENTS[instrument_id]
    text = definition.source_path.read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()


def external_simulator_identity(instrument_id: str) -> dict[str, Any]:
    """Return and validate the exact tracked upstream simulator revision in use."""

    definition = EXTERNAL_INSTRUMENTS[instrument_id]
    simulator_path = definition.simulator_path()
    try:
        root = Path(
            subprocess.run(
                ["git", "-C", str(simulator_path.parent), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tracked_changes = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ExternalRuntimeUnavailable(
            f"cannot establish the pinned simulator identity for {instrument_id}"
        ) from exc
    relative_path = simulator_path.relative_to(root)
    payload = {
        "instrument_id": instrument_id,
        "expected_revision": definition.upstream_revision,
        "observed_revision": revision,
        "tracked_worktree_clean": not bool(tracked_changes),
        "simulator_relative_path": relative_path.as_posix(),
        "simulator_sha256": source_sha256(simulator_path),
    }
    payload["verdict"] = (
        "PASS" if revision == definition.upstream_revision and not tracked_changes else "FAIL"
    )
    return payload


def _hold_result(
    definition: ExternalInstrumentDefinition,
    skill_py: str,
    scenario: SimulationScenario,
    error: Exception,
) -> HardGateResult:
    skill_hash = hashlib.sha256(skill_py.encode()).hexdigest()
    simulator = definition.simulator_path
    simulator_hash = "unavailable"
    try:
        simulator_hash = source_sha256(simulator())
    except Exception:
        pass
    return HardGateResult(
        instrument_id=definition.instrument_id,
        family=definition.family,
        scenario=scenario,
        verdict="HOLD",
        status="unavailable",
        checks=(
            GateCheck(
                check_id="simulator-available",
                passed=False,
                evidence={"error": f"{type(error).__name__}: {error}"},
            ),
        ),
        trace=(),
        telemetry={},
        result=None,
        runtime_error=f"{type(error).__name__}: {error}",
        skill_sha256=skill_hash,
        simulator_sha256=simulator_hash,
        verifier_sha256=source_sha256(definition.verifier_path),
    )


def evaluate_external_skill(
    instrument_id: str,
    skill_py: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    condition: Mapping[str, float] | None = None,
) -> HardGateResult:
    definition = EXTERNAL_INSTRUMENTS[instrument_id]
    condition_values = dict(condition or {})
    try:
        controller = definition.controller_type(scenario, condition_values)
        simulator_path = definition.simulator_path()
    except Exception as exc:
        return _hold_result(definition, skill_py, scenario, exc)
    return evaluate_controller_skill(
        instrument_id,
        definition.family,
        skill_py,
        scenario=scenario,
        allowed_methods=definition.allowed_methods,
        controller=controller,
        verifier=definition.verifier,
        simulator_path=simulator_path,
        verifier_path=definition.verifier_path,
        condition_evidence=condition_values,
    )


def _fixture_candidate(instrument_id: str, skill_py: str) -> CandidatePackage:
    _, source_hash = load_external_source(instrument_id)
    return CandidatePackage(
        instrument_id=instrument_id,
        skill_md=(
            f"---\nname: {instrument_id}\ndescription: Fixture-only conformance procedure.\n---\n\n"
            "Hidden conformance fixture; never shown to the drafting model.\n"
        ),
        skill_py=skill_py,
        self_judgment={"verdict": "HOLD", "basis": ["fixture-only"]},
        source_sha256=source_hash,
        prompt_sha256="fixture",
        model="fixture",
        raw_response={},
    )


VALID_FIXTURES = {
    "north-pipette-calibration": """def run(controller):
    controller.reset()
    sample = controller.sample_info()
    target = sample[\"target_volume_ml\"]
    controller.get_constraints(target)
    if sample[\"liquid\"] == \"water\":
        overaspirate = 0.00125
    else:
        overaspirate = 0.003125
    result = controller.measure(target, overaspirate, 20.0, 1.0, 3)
    controller.cleanup()
    return result
""",
    "helao-gamry-cv": """def run(controller):
    controller.reset()
    controller.connect()
    limits = controller.get_limits()
    offset = controller.read_zero_offset()
    controller.set_zero_compensation(offset)
    result = controller.potential_cycle(
        0.0, -0.5, 0.5, 0.0, limits[\"maximum_scan_rate_v_s\"], 1, 0.02
    )
    controller.disconnect()
    return result
""",
    "clslab-light-spectrometer": """def run(controller):
    controller.reset()
    limits = controller.get_limits()
    gain = 64.0
    if limits[\"maximum_signal\"] < 40000.0:
        gain = 16.0
    controller.configure(100, 999, gain)
    controller.set_rgb(40, 60, 20)
    result = controller.measure()
    controller.clear()
    return result
""",
}


INVALID_FIXTURES = {
    "north-pipette-calibration": """def run(controller):
    controller.reset()
    sample = controller.sample_info()
    target = sample[\"target_volume_ml\"]
    controller.get_constraints(target)
    result = controller.measure(target, 0.15, 1.0, 0.0, 3)
    controller.cleanup()
    return result
""",
    "helao-gamry-cv": """def run(controller):
    controller.reset()
    controller.connect()
    controller.get_limits()
    offset = controller.read_zero_offset()
    controller.set_zero_compensation(offset)
    result = controller.potential_cycle(0.0, -0.5, 0.5, 0.0, 0.4, 1, 0.02)
    controller.disconnect()
    return result
""",
    "clslab-light-spectrometer": """def run(controller):
    controller.reset()
    controller.get_limits()
    controller.configure(255, 65534, 512.0)
    controller.set_rgb(89, 89, 89)
    result = controller.measure()
    controller.clear()
    return result
""",
}

INVALID_REQUIRED_CHECKS = {
    "north-pipette-calibration": ("volume-accuracy",),
    "helao-gamry-cv": ("scan-rate-support",),
    "clslab-light-spectrometer": ("counting-range",),
}

CHANGE_REQUIRED_CHECKS = {
    "north-pipette-calibration": ("volume-accuracy",),
    "helao-gamry-cv": ("potential-sweep-fidelity",),
    "clslab-light-spectrometer": ("counting-range",),
}


def run_external_preflight(instrument_id: str) -> FixturePreflightReport:
    definition = EXTERNAL_INSTRUMENTS[instrument_id]
    identity = external_simulator_identity(instrument_id)
    if identity["verdict"] != "PASS":
        raise ExternalRuntimeUnavailable(
            f"pinned simulator identity failed for {instrument_id}: {identity}"
        )
    valid = _fixture_candidate(instrument_id, VALID_FIXTURES[instrument_id])
    invalid = _fixture_candidate(instrument_id, INVALID_FIXTURES[instrument_id])
    cases = (
        PreflightCase(
            case_id=f"{instrument_id}:valid",
            candidate=valid,
            condition=DebugCondition(
                condition_id="valid-control", scenario=SimulationScenario.NOMINAL, repetitions=3
            ),
            expected_verdict="ADMIT",
        ),
        PreflightCase(
            case_id=f"{instrument_id}:repair-valid",
            candidate=valid,
            condition=DebugCondition(
                condition_id="repair-valid-control",
                scenario=SimulationScenario.REPAIR,
                repetitions=3,
            ),
            expected_verdict="ADMIT",
        ),
        PreflightCase(
            case_id=f"{instrument_id}:drift-valid",
            candidate=valid,
            condition=DebugCondition(
                condition_id="drift-valid-control",
                scenario=SimulationScenario.DRIFT,
                repetitions=3,
            ),
            expected_verdict="ADMIT",
        ),
        PreflightCase(
            case_id=f"{instrument_id}:invalid",
            candidate=invalid,
            condition=DebugCondition(
                condition_id="invalid-control", scenario=SimulationScenario.REPAIR, repetitions=3
            ),
            expected_verdict="REJECT",
            required_failed_checks=INVALID_REQUIRED_CHECKS[instrument_id],
        ),
        PreflightCase(
            case_id=f"{instrument_id}:registered-change",
            candidate=valid,
            condition=definition.visible_conditions[-1],
            expected_verdict="REJECT",
            required_failed_checks=CHANGE_REQUIRED_CHECKS[instrument_id],
        ),
        PreflightCase(
            case_id=f"{instrument_id}:locked-change",
            candidate=valid,
            condition=definition.locked_conditions[0],
            expected_verdict="REJECT",
            required_failed_checks=CHANGE_REQUIRED_CHECKS[instrument_id],
        ),
        PreflightCase(
            case_id=f"{instrument_id}:evolution-change",
            candidate=valid,
            condition=definition.evolution_conditions[0],
            expected_verdict="REJECT",
            required_failed_checks=CHANGE_REQUIRED_CHECKS[instrument_id],
        ),
        PreflightCase(
            case_id=f"{instrument_id}:unavailable",
            candidate=valid,
            condition=DebugCondition(
                condition_id="unavailable-control",
                scenario=SimulationScenario.UNAVAILABLE,
                repetitions=3,
            ),
            expected_verdict="HOLD",
            required_failed_checks=("simulator-available",),
        ),
    )
    return run_fixture_preflight(cases, evaluator=evaluate_external_skill)


METROLOGY_INVALID_FIXTURES: dict[str, dict[str, tuple[str, SimulationScenario]]] = {
    "north-pipette-calibration": {
        "inaccurate_volume": (
            INVALID_FIXTURES["north-pipette-calibration"],
            SimulationScenario.REPAIR,
        ),
        "insufficient_replicates": (
            """def run(controller):
    controller.reset()
    sample = controller.sample_info()
    target = sample[\"target_volume_ml\"]
    controller.get_constraints(target)
    result = controller.measure(target, 0.003125, 20.0, 1.0, 1)
    controller.cleanup()
    return result
""",
            SimulationScenario.REPAIR,
        ),
        "tip_capacity": (
            """def run(controller):
    controller.reset()
    sample = controller.sample_info()
    target = sample[\"target_volume_ml\"]
    controller.get_constraints(target)
    result = controller.measure(target, 0.16, 20.0, 1.0, 3)
    controller.cleanup()
    return result
""",
            SimulationScenario.NOMINAL,
        ),
        "cleanup_omitted": (
            """def run(controller):
    controller.reset()
    sample = controller.sample_info()
    target = sample[\"target_volume_ml\"]
    controller.get_constraints(target)
    return controller.measure(target, 0.00125, 20.0, 1.0, 3)
""",
            SimulationScenario.NOMINAL,
        ),
    },
    "helao-gamry-cv": {
        "scan_rate_exceeded": (INVALID_FIXTURES["helao-gamry-cv"], SimulationScenario.REPAIR),
        "zero_shift_uncompensated": (
            """def run(controller):
    controller.reset()
    controller.connect()
    limits = controller.get_limits()
    controller.read_zero_offset()
    controller.set_zero_compensation(0.0)
    result = controller.potential_cycle(
        0.0, -0.5, 0.5, 0.0, limits[\"maximum_scan_rate_v_s\"], 1, 0.02
    )
    controller.disconnect()
    return result
""",
            SimulationScenario.DRIFT,
        ),
        "wrong_sweep_endpoint": (
            """def run(controller):
    controller.reset()
    controller.connect()
    limits = controller.get_limits()
    offset = controller.read_zero_offset()
    controller.set_zero_compensation(offset)
    result = controller.potential_cycle(
        0.0, -0.5, 0.3, 0.0, limits[\"maximum_scan_rate_v_s\"], 1, 0.02
    )
    controller.disconnect()
    return result
""",
            SimulationScenario.NOMINAL,
        ),
        "cleanup_omitted": (
            """def run(controller):
    controller.reset()
    controller.connect()
    limits = controller.get_limits()
    offset = controller.read_zero_offset()
    controller.set_zero_compensation(offset)
    return controller.potential_cycle(
        0.0, -0.5, 0.5, 0.0, limits[\"maximum_scan_rate_v_s\"], 1, 0.02
    )
""",
            SimulationScenario.NOMINAL,
        ),
    },
    "clslab-light-spectrometer": {
        "saturation": (INVALID_FIXTURES["clslab-light-spectrometer"], SimulationScenario.REPAIR),
        "insufficient_signal": (
            """def run(controller):
    controller.reset()
    controller.get_limits()
    controller.configure(1, 1, 0.5)
    controller.set_rgb(1, 1, 1)
    result = controller.measure()
    controller.clear()
    return result
""",
            SimulationScenario.NOMINAL,
        ),
        "cleanup_omitted": (
            """def run(controller):
    controller.reset()
    controller.get_limits()
    controller.configure(100, 999, 16.0)
    controller.set_rgb(40, 60, 20)
    return controller.measure()
""",
            SimulationScenario.NOMINAL,
        ),
    },
}


def run_external_metrology(
    instrument_id: str,
    *,
    cases_per_class: int = 300,
) -> dict[str, Any]:
    """Measure false decisions against labeled fixture truth before model generation."""

    if cases_per_class < 1:
        raise ValueError("cases_per_class must be positive")
    valid_rows = []
    for index in range(cases_per_class):
        scenario = SimulationScenario.NOMINAL
        gate = evaluate_external_skill(
            instrument_id,
            VALID_FIXTURES[instrument_id],
            scenario=scenario,
            condition={"seed": float(1_700_000 + index)},
        )
        valid_rows.append(
            {
                "case_id": f"valid-{index:04d}",
                "scenario": scenario.value,
                "observed": gate.verdict,
                "false_reject": gate.verdict != "ADMIT",
                "failed_checks": [check.check_id for check in gate.checks if not check.passed],
            }
        )

    invalid_groups: dict[str, Any] = {}
    total_false_admits = 0
    for class_name, (skill_py, scenario) in METROLOGY_INVALID_FIXTURES[instrument_id].items():
        rows = []
        for index in range(cases_per_class):
            gate = evaluate_external_skill(
                instrument_id,
                skill_py,
                scenario=scenario,
                condition={"seed": float(1_800_000 + index)},
            )
            false_admit = gate.verdict == "ADMIT"
            total_false_admits += int(false_admit)
            rows.append(
                {
                    "case_id": f"{class_name}-{index:04d}",
                    "observed": gate.verdict,
                    "false_admit": false_admit,
                    "failed_checks": [check.check_id for check in gate.checks if not check.passed],
                }
            )
        invalid_groups[class_name] = {
            "cases": cases_per_class,
            "false_admits": sum(row["false_admit"] for row in rows),
            "rows": rows,
        }

    false_rejects = sum(row["false_reject"] for row in valid_rows)
    false_reject_rate = false_rejects / cases_per_class
    passed = total_false_admits == 0 and false_reject_rate <= 0.05
    return {
        "schema_version": "proprio.external_metrology.v0.4",
        "instrument_id": instrument_id,
        "cases_per_class": cases_per_class,
        "valid": {
            "cases": cases_per_class,
            "false_rejects": false_rejects,
            "false_reject_rate": false_reject_rate,
            "rows": valid_rows,
        },
        "invalid": invalid_groups,
        "total_false_admits": total_false_admits,
        "verdict": "PASS" if passed else "FAIL",
    }
