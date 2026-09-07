"""Final reuse study runtime, isolated from the production result interface."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from proprio import instrument_qualification
from proprio.instrument_plugins import instrument_registry
from proprio.instrument_types import SimulationScenario

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INSTRUMENT = "proprio.flake_search.2d-flake-search"


SYSTEM = """You are operating a simulated scientific instrument using its supplied documentation.
Use bash to read and write files in /workspace. The instrument runtime is available only through
execute_candidate, when that tool is provided. It executes the bounded run(controller) procedure
and returns development feedback. You may inspect, revise, and test your work within the budget.
Other files, networks, and instruments are unavailable. Do not invent measurements or claim
hardware qualification. Work independently and leave the requested files before finishing."""


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(code: str, cases: list[dict]) -> list[dict]:
    """Keep the bounded runtime and verifier; derive the interface result from behavior.

    The wrapper never catches procedure exceptions or rewrites source. Optional return
    values have no meaning in this study. Patching is scoped to this synchronous call;
    the production evaluator and all earlier study files remain unchanged.
    """
    original_compile = instrument_qualification.compile_instrument_skill

    def compile_with_result(source, allowed_methods, **kwargs):
        bounded = original_compile(source, allowed_methods, **kwargs)

        def run_with_result(controller):
            bounded(controller)
            completions = [row for row in controller.trace if row["operation"] == "complete_scan"]
            if len(completions) != 1:
                raise ValueError("public result requires exactly one complete_scan")
            status = completions[0].get("status_code")
            telemetry = controller.telemetry()
            if (
                type(status) is not int
                or status not in {0, 1, 2, 3, 4}
                or telemetry.get("completed") is not True
                or telemetry.get("status_code") != status
            ):
                raise ValueError(
                    "public result requires a valid completion agreeing with telemetry"
                )
            return {"status_code": status}

        return run_with_result

    with patch.object(instrument_qualification, "compile_instrument_skill", compile_with_result):
        registry = instrument_registry(INSTRUMENT)
        return [
            registry.evaluate(
                INSTRUMENT,
                code,
                scenario=SimulationScenario.NOMINAL,
                condition=case["parameters"],
            ).model_dump(mode="json")
            for case in cases
        ]


def outcome(gate: dict, expected: int) -> dict:
    returned = (gate.get("result") or {}).get("status_code")
    completions = [x for x in gate["trace"] if x["operation"] == "complete_scan"]
    status = completions[0].get("status_code") if len(completions) == 1 else None
    agrees = status is not None and returned == status
    failed = [c["check_id"] for c in gate["checks"] if not c["passed"]]
    result = {
        "passed": gate["verdict"] == "ADMIT" and status == expected and agrees,
        "returned_status": returned,
        "status_agrees": agrees,
        "status": status,
        "expected_status": expected,
        "failed_checks": failed,
        "invalid_completed_operation": (status == 0 or returned == 0)
        and (gate["verdict"] != "ADMIT" or not agrees),
        "inappropriate_stop": expected == 0 and status not in (None, 0),
        "runtime_error": gate["runtime_error"],
        "controller_calls": len(gate["trace"]),
    }

    result["invalid_completed_operation"] |= result["status"] == 0 and expected != 0
    return result


def usage(trace: Path) -> dict:
    result = {
        "assistant_messages": 0,
        "tokens": 0,
        "cost_usd": 0.0,
        "errors": [],
        "accounting_complete": True,
    }
    pending = 0
    for line in trace.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            result["accounting_complete"] = False
            continue
        msg = event.get("message", {})
        if event.get("type") == "message_start" and msg.get("role") == "assistant":
            pending += 1
        if event.get("type") != "message_end" or msg.get("role") != "assistant":
            continue
        pending = max(0, pending - 1)
        result["assistant_messages"] += 1
        u = msg.get("usage", {})
        if (
            not u
            or not isinstance(u.get("cost", {}).get("total"), (int, float))
            or any(
                not isinstance(u.get(k), (int, float))
                for k in ("input", "output", "cacheRead", "cacheWrite")
            )
        ):
            result["accounting_complete"] = False
        if msg.get("stopReason") in ("length", "error", "aborted"):
            result["errors"].append("stopReason=" + msg["stopReason"])
        result["tokens"] += sum(u.get(k, 0) for k in ("input", "output", "cacheRead", "cacheWrite"))
        result["cost_usd"] += u.get("cost", {}).get("total", 0)
        if msg.get("errorMessage"):
            result["errors"].append(msg["errorMessage"])
    result["accounting_complete"] &= (
        result["tokens"] > 0 and result["cost_usd"] > 0 and pending == 0
    )
    return result


def summarize(rows):
    import statistics

    pairs = []
    for pair in [1, 2, 3]:
        arms = {}
        for version in ["before", "after"]:
            group = [r for r in rows if r["pair"] == pair and r["version"] == version]
            assert len(group) == 2
            arms[version] = {
                "successes": sum(r["success"] for r in group),
                "median_tokens": statistics.median(r["usage"]["tokens"] for r in group),
                "false_completion_sessions": sum(
                    any(o["invalid_completed_operation"] for o in r["outcomes"]) for r in group
                ),
            }
        pairs.append(
            {
                "pair": pair,
                **arms,
                "success_fraction_difference": (
                    arms["after"]["successes"] - arms["before"]["successes"]
                )
                / 2,
            }
        )
    totals = {v: sum(p[v]["successes"] for p in pairs) for v in ["before", "after"]}
    operational = all(r["operationally_complete"] for r in rows)
    no_regression = all(
        p["after"]["successes"] >= p["before"]["successes"]
        and p["after"]["false_completion_sessions"] <= p["before"]["false_completion_sessions"]
        for p in pairs
    )
    improved = (
        totals["after"] >= totals["before"] + 2
        and sum(p["success_fraction_difference"] > 0 for p in pairs) >= 2
    )
    cheaper = (
        totals["before"] == totals["after"] == 6
        and sum(p["after"]["median_tokens"] <= 0.8 * p["before"]["median_tokens"] for p in pairs)
        >= 2
        and all(p["after"]["median_tokens"] <= 1.1 * p["before"]["median_tokens"] for p in pairs)
    )
    return {
        "pairs": pairs,
        "successful_consumers": totals,
        "planned_consumers_per_arm": 6,
        "operationally_complete": operational,
        "minimum_useful_improvement_met": operational and no_regression and (improved or cheaper),
    }
