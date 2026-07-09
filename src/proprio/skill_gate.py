"""Deterministic admission gate for model-drafted SMU skills."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType
from typing import Any

from proprio.artifacts import source_sha256, write_canonical_json
from proprio.schema import StatusLabel
from proprio.smu import OhmicFixture, SimulatedSMUController

ALLOWED_METHODS = frozenset(
    {
        "identify",
        "reset",
        "set_current_limit",
        "set_measurement_range",
        "set_voltage",
        "enable_output",
        "measure_current",
        "disable_output",
        "error",
    }
)
ALLOWED_NODES = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Assign,
    ast.Expr,
    ast.Call,
    ast.Attribute,
    ast.Name,
    ast.Constant,
    ast.Return,
    ast.Dict,
    ast.keyword,
    ast.Load,
    ast.Store,
)


@dataclass(frozen=True)
class AdmissionResult:
    verdict: str
    status: StatusLabel
    checks: tuple[dict[str, Any], ...]
    trace: tuple[dict[str, Any], ...]
    result: dict[str, Any] | None
    skill_sha256: str
    verifier_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "proprio.skill_admission.v0.1",
            "verdict": self.verdict,
            "status": self.status.value,
            "checks": list(self.checks),
            "trace": list(self.trace),
            "result": self.result,
            "skill_sha256": self.skill_sha256,
            "verifier_sha256": self.verifier_sha256,
        }


def _load_skill(source: str) -> FunctionType:
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "run":
        raise ValueError("skill must define exactly one function named run")
    if [argument.arg for argument in functions[0].args.args] != ["controller"]:
        raise ValueError("run must take exactly one controller argument")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute):
                raise ValueError("only controller method calls are allowed")
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "controller":
                raise ValueError("calls must target the controller")
            if node.func.attr not in ALLOWED_METHODS:
                raise ValueError(f"disallowed controller method: {node.func.attr}")
    namespace: dict[str, Any] = {"__builtins__": {}}
    exec(compile(tree, "<drafted-skill>", "exec"), namespace)
    function = namespace["run"]
    if not isinstance(function, FunctionType):
        raise ValueError("run did not compile to a function")
    return function


def _check(check_id: str, passed: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": StatusLabel.SUCCEEDED if passed else StatusLabel.FAILED,
        "evidence": evidence,
    }


def evaluate_skill(source: str, fixture: OhmicFixture | None = None) -> AdmissionResult:
    fixture = fixture or OhmicFixture()
    skill_hash = hashlib.sha256(source.encode()).hexdigest()
    verifier_hash = source_sha256(Path(__file__))
    try:
        function = _load_skill(source)
    except Exception as exc:
        return AdmissionResult(
            verdict="REJECT",
            status=StatusLabel.FAILED,
            checks=(_check("static-safety", False, {"error": f"{type(exc).__name__}: {exc}"}),),
            trace=(),
            result=None,
            skill_sha256=skill_hash,
            verifier_sha256=verifier_hash,
        )

    controller = SimulatedSMUController(fixture)
    result: dict[str, Any] | None = None
    runtime_error: str | None = None
    try:
        raw_result = function(controller)
        if not isinstance(raw_result, dict):
            raise ValueError("run must return a dictionary")
        result = raw_result
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
    finally:
        trace = tuple(controller.trace)
        state = {
            "voltage_v": controller.voltage_v,
            "current_limit_a": controller.current_limit_a,
            "measurement_range_a": controller.measurement_range_a,
            "output_enabled": controller.output_enabled,
            "measurement_a": controller.measurement_a,
        }
        controller.close()

    operations = [row["operation"] for row in trace]
    output_index = operations.index("enable_output") if "enable_output" in operations else -1
    limit_index = operations.index("set_current_limit") if "set_current_limit" in operations else -1
    range_index = (
        operations.index("set_measurement_range") if "set_measurement_range" in operations else -1
    )
    expected_current = fixture.expected_current_a
    measured = state["measurement_a"]
    relative_error = (
        abs(float(measured) - expected_current) / expected_current
        if measured is not None
        else float("inf")
    )
    checks = (
        _check("static-safety", True, {"allowed_methods": sorted(ALLOWED_METHODS)}),
        _check("runtime-completed", runtime_error is None, {"error": runtime_error}),
        _check(
            "compliance-before-output",
            0 <= limit_index < output_index,
            {"limit_index": limit_index, "output_index": output_index},
        ),
        _check(
            "range-before-output",
            0 <= range_index < output_index,
            {"range_index": range_index, "output_index": output_index},
        ),
        _check(
            "voltage-contract",
            state["voltage_v"] is not None
            and abs(float(state["voltage_v"]) - fixture.target_voltage_v) <= 1e-9,
            {"observed_v": state["voltage_v"], "required_v": fixture.target_voltage_v},
        ),
        _check(
            "compliance-contract",
            state["current_limit_a"] is not None
            and fixture.minimum_compliance_a
            <= float(state["current_limit_a"])
            <= fixture.maximum_safe_compliance_a,
            {
                "observed_a": state["current_limit_a"],
                "minimum_a": fixture.minimum_compliance_a,
                "maximum_a": fixture.maximum_safe_compliance_a,
            },
        ),
        _check(
            "range-contract",
            state["measurement_range_a"] is not None
            and fixture.minimum_measurement_range_a
            <= float(state["measurement_range_a"])
            <= fixture.maximum_measurement_range_a,
            {
                "observed_a": state["measurement_range_a"],
                "minimum_a": fixture.minimum_measurement_range_a,
                "maximum_a": fixture.maximum_measurement_range_a,
            },
        ),
        _check(
            "ohms-law",
            relative_error <= fixture.relative_current_tolerance,
            {
                "measured_current_a": measured,
                "expected_current_a": expected_current,
                "relative_error": relative_error,
                "tolerance": fixture.relative_current_tolerance,
            },
        ),
        _check(
            "output-disabled-at-return",
            not bool(state["output_enabled"]),
            {"output_enabled": state["output_enabled"]},
        ),
    )
    admitted = all(check["status"] is StatusLabel.SUCCEEDED for check in checks)
    return AdmissionResult(
        verdict="ADMIT" if admitted else "REJECT",
        status=StatusLabel.SUCCEEDED if admitted else StatusLabel.FAILED,
        checks=checks,
        trace=trace,
        result=result,
        skill_sha256=skill_hash,
        verifier_sha256=verifier_hash,
    )


def persist_admission(source: str, output_path: Path) -> AdmissionResult:
    result = evaluate_skill(source)
    write_canonical_json(output_path, result.as_dict())
    return result
