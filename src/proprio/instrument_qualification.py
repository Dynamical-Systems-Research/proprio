"""Static execution and independent qualification for diagnostic instrument skills."""

from __future__ import annotations

import ast
import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType
from typing import Any

from proprio.artifacts import source_sha256
from proprio.instrument_types import GateCheck, HardGateResult, SimulationScenario
from proprio.instrument_verifiers import verify_instrument
from proprio.reference_instruments import INSTRUMENTS, build_controller

ADAPTIVE_NODES = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Assign,
    ast.AugAssign,
    ast.Expr,
    ast.Call,
    ast.Attribute,
    ast.Name,
    ast.Constant,
    ast.Return,
    ast.Dict,
    ast.List,
    ast.Tuple,
    ast.UnaryOp,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.If,
    ast.For,
    ast.Subscript,
    ast.keyword,
    ast.Load,
    ast.Store,
)


@dataclass(frozen=True)
class AdaptiveSkillLimits:
    """Static and runtime bounds for model-authored instrument procedures."""

    max_source_bytes: int = 16_384
    max_loop_iterations: int = 16
    max_branch_depth: int = 4
    max_controller_calls: int = 96


DEFAULT_SKILL_LIMITS = AdaptiveSkillLimits()


class _ControllerBudget:
    def __init__(self, controller: Any, *, allowed_methods: frozenset[str], limit: int) -> None:
        self._controller = controller
        self._allowed_methods = allowed_methods
        self._remaining = limit

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name not in self._allowed_methods:
            raise AttributeError(name)
        target = getattr(self._controller, name)

        def bounded_call(*args: Any, **kwargs: Any) -> Any:
            if self._remaining <= 0:
                raise RuntimeError("controller call budget exhausted")
            self._remaining -= 1
            return target(*args, **kwargs)

        return bounded_call


def _literal_range_iterations(call: ast.Call, limits: AdaptiveSkillLimits) -> int:
    if not isinstance(call.func, ast.Name) or call.func.id != "range" or call.keywords:
        raise ValueError("for loops must iterate over range(...) with literal integer bounds")
    if not 1 <= len(call.args) <= 3:
        raise ValueError("range requires one to three literal integer arguments")
    values: list[int] = []
    for argument in call.args:
        if not isinstance(argument, ast.Constant) or isinstance(argument.value, bool):
            raise ValueError("range bounds must be literal integers")
        if not isinstance(argument.value, int):
            raise ValueError("range bounds must be literal integers")
        values.append(argument.value)
    iterations = len(range(*values))
    if iterations > limits.max_loop_iterations:
        raise ValueError(
            f"loop iteration bound {iterations} exceeds {limits.max_loop_iterations}"
        )
    return iterations


def _controller_call_cost(statements: Sequence[ast.stmt], limits: AdaptiveSkillLimits) -> int:
    total = 0
    for statement in statements:
        if isinstance(statement, ast.For):
            iterations = _literal_range_iterations(statement.iter, limits)
            body = _controller_call_cost(statement.body, limits)
            alternate = _controller_call_cost(statement.orelse, limits)
            total += iterations * body + alternate
        elif isinstance(statement, ast.If):
            total += max(
                _controller_call_cost(statement.body, limits),
                _controller_call_cost(statement.orelse, limits),
            )
        else:
            total += sum(
                1
                for node in ast.walk(statement)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            )
    return total


def _validate_branch_depth(node: ast.AST, limits: AdaptiveSkillLimits, depth: int = 0) -> None:
    next_depth = depth + 1 if isinstance(node, (ast.If, ast.For)) else depth
    if next_depth > limits.max_branch_depth:
        raise ValueError(f"branch depth exceeds {limits.max_branch_depth}")
    for child in ast.iter_child_nodes(node):
        _validate_branch_depth(child, limits, next_depth)

CONDITION_FIELDS = {
    "ot2-transfer": frozenset({"max_transfer_ul"}),
    "star-transfer": frozenset({"max_transfer_ul"}),
    "constant-current-cycle": frozenset({"current_limit_a"}),
    "pulse-characterization": frozenset({"current_limit_a"}),
    "powder-bed-scan": frozenset({"absorptivity"}),
    "directed-energy-deposition": frozenset({"coupling"}),
    "hall-sweep": frozenset({"required_settle_s"}),
    "cryogenic-resistance": frozenset({"current_limit_a"}),
}


def compile_instrument_skill(
    source: str,
    allowed_methods: frozenset[str],
    *,
    limits: AdaptiveSkillLimits = DEFAULT_SKILL_LIMITS,
) -> FunctionType:
    if len(source.encode()) > limits.max_source_bytes:
        raise ValueError(f"skill source exceeds {limits.max_source_bytes} bytes")
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "run":
        raise ValueError("skill must define exactly one function named run")
    if [argument.arg for argument in functions[0].args.args] != ["controller"]:
        raise ValueError("run must take exactly one controller argument")
    called_attributes = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    _validate_branch_depth(tree, limits)
    for node in ast.walk(tree):
        if not isinstance(node, ADAPTIVE_NODES):
            raise ValueError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "range":
                _literal_range_iterations(node, limits)
            elif isinstance(node.func, ast.Attribute):
                if not isinstance(node.func.value, ast.Name) or node.func.value.id != "controller":
                    raise ValueError("calls must target the controller")
                if node.func.attr not in allowed_methods:
                    raise ValueError(f"disallowed controller method: {node.func.attr}")
            else:
                raise ValueError("only controller methods and bounded range calls are allowed")
        if isinstance(node, ast.Attribute) and id(node) not in called_attributes:
            raise ValueError("direct reads of simulator state are forbidden")
    call_cost = _controller_call_cost(functions[0].body, limits)
    if call_cost > limits.max_controller_calls:
        raise ValueError(
            f"controller call bound {call_cost} exceeds {limits.max_controller_calls}"
        )
    namespace: dict[str, Any] = {"__builtins__": {"range": range}}
    exec(compile(tree, "<instrument-skill>", "exec"), namespace)
    function = namespace["run"]
    if not isinstance(function, FunctionType):
        raise ValueError("run did not compile to a function")

    def bounded(controller: Any) -> Any:
        proxy = _ControllerBudget(
            controller,
            allowed_methods=allowed_methods,
            limit=limits.max_controller_calls,
        )
        return function(proxy)

    return bounded


def evaluate_controller_skill(
    instrument_id: str,
    family: str,
    source: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    allowed_methods: frozenset[str],
    controller: Any,
    verifier: Callable[[str, str, Sequence[dict[str, Any]], dict[str, Any]], tuple[GateCheck, ...]],
    simulator_path: Path,
    verifier_path: Path,
    condition_evidence: Mapping[str, float] | None = None,
) -> HardGateResult:
    """Run one bounded skill against a supplied controller and physical verifier."""

    skill_hash = hashlib.sha256(source.encode()).hexdigest()
    try:
        function = compile_instrument_skill(source, allowed_methods)
    except Exception as exc:
        return HardGateResult(
            instrument_id=instrument_id,
            family=family,
            scenario=scenario,
            verdict="REJECT",
            status="failed",
            checks=(
                GateCheck(
                    check_id="static-safety",
                    passed=False,
                    evidence={"error": f"{type(exc).__name__}: {exc}"},
                ),
            ),
            trace=(),
            telemetry={},
            result=None,
            runtime_error=f"{type(exc).__name__}: {exc}",
            skill_sha256=skill_hash,
            simulator_sha256=source_sha256(simulator_path),
            verifier_sha256=source_sha256(verifier_path),
        )

    condition_values = dict(condition_evidence or {})
    result: dict[str, Any] | None = None
    runtime_error: str | None = None
    try:
        raw_result = function(controller)
        if not isinstance(raw_result, dict):
            raise ValueError("run must return a dictionary")
        result = raw_result
    except Exception as exc:
        runtime_error = f"{type(exc).__name__}: {exc}"
    telemetry = controller.telemetry()
    trace = tuple(controller.trace)

    if scenario is SimulationScenario.UNAVAILABLE:
        return HardGateResult(
            instrument_id=instrument_id,
            family=family,
            scenario=scenario,
            verdict="HOLD",
            status="unavailable",
            checks=(
                GateCheck(
                    check_id="simulator-available",
                    passed=False,
                    evidence={"error": runtime_error or "simulator unavailable"},
                ),
            ),
            trace=trace,
            telemetry=telemetry,
            result=result,
            runtime_error=runtime_error,
            skill_sha256=skill_hash,
            simulator_sha256=source_sha256(simulator_path),
            verifier_sha256=source_sha256(verifier_path),
        )

    checks = (
        GateCheck(
            check_id="static-safety",
            passed=True,
            evidence={"allowed_methods": sorted(allowed_methods)},
        ),
        GateCheck(
            check_id="runtime-completed",
            passed=runtime_error is None,
            evidence={"error": runtime_error},
        ),
        *(
            (
                GateCheck(
                    check_id="locked-condition-applied",
                    passed=True,
                    evidence={"condition": condition_values},
                ),
            )
            if condition_values
            else ()
        ),
        *verifier(instrument_id, family, trace, telemetry),
    )
    admitted = all(check.passed for check in checks)
    return HardGateResult(
        instrument_id=instrument_id,
        family=family,
        scenario=scenario,
        verdict="ADMIT" if admitted else "REJECT",
        status="succeeded" if admitted else "failed",
        checks=checks,
        trace=trace,
        telemetry=telemetry,
        result=result,
        runtime_error=runtime_error,
        skill_sha256=skill_hash,
        simulator_sha256=source_sha256(simulator_path),
        verifier_sha256=source_sha256(verifier_path),
    )


def evaluate_instrument_skill(
    instrument_id: str,
    source: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    condition: Mapping[str, float] | None = None,
) -> HardGateResult:
    definition = INSTRUMENTS[instrument_id]
    controller = build_controller(instrument_id, scenario)
    condition_values = dict(condition or {})
    unknown_fields = set(condition_values) - CONDITION_FIELDS[instrument_id]
    if unknown_fields:
        raise ValueError(
            f"unsupported condition fields for {instrument_id}: {sorted(unknown_fields)}"
        )
    for field, value in condition_values.items():
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"condition {field} must be positive and finite")
        setattr(controller, field, numeric)
    return evaluate_controller_skill(
        instrument_id,
        definition.family,
        source,
        scenario=scenario,
        allowed_methods=definition.allowed_methods,
        controller=controller,
        verifier=verify_instrument,
        simulator_path=Path(__file__).with_name("reference_instruments.py"),
        verifier_path=Path(__file__).with_name("instrument_verifiers.py"),
        condition_evidence=condition_values,
    )
