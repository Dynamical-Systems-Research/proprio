"""Matched transfer study with a trace-derived public result and native Pi."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

if __package__:
    from . import runtime as base
else:
    import runtime as base

evaluate, outcome, summarize = base.evaluate, base.outcome, base.summarize

ROOT, HERE = base.ROOT, base.HERE
RUNS = ROOT / "runs/pi-reuse-new"
CONTRACT_PATH = HERE / "contract.json"
C = json.loads(CONTRACT_PATH.read_text())
SYSTEM = base.SYSTEM
AUTHOR = """Read source.md and produce skill.py plus SKILL.md for its complete operating
procedure. Define run(controller) in the documented bounded language. Save both files
using bash before finishing. You have no execution feedback. Describe your unverified
procedure honestly; do not claim simulation admission or hardware qualification."""
REPAIR = """Improve the supplied skill.py and SKILL.md using source.md and development
execution feedback. These files are your own earlier draft. Run execute_candidate on
the draft, diagnose failures, and repair the procedure within at most six executions.
Preserve correct behavior. Leave your final skill.py and concise operating instructions
in SKILL.md, recording what you actually tested and remaining limitations. Development
checks do not establish private admission or hardware qualification. Save files with bash."""
CONSUMER = """Prepare skill.py for a complete optical flake search over the declared region.
Read source.md and reference/skill.py plus reference/SKILL.md; reuse or revise them as
useful. Handle documented disturbances honestly and release the instrument. Define
run(controller) in the documented bounded language. Call complete_scan exactly once
with the appropriate outcome, then release. The harness constructs the result from that
observed completion; no return dictionary is required or used. You may use at most two
execute_candidate development tests. Separate
private simulator instances grade observed behavior, not code identity. Save skill.py
using bash before finishing, then state briefly what you tested. A code block in your
final response is not a saved procedure file."""
SMOKE1 = """Runtime preflight only. Use bash to write skill.py containing exactly:
def run(controller):
    return
Then write completion.txt containing ready. Read both files back with bash and finish.
Do not inspect source.md or claim an instrument result."""
SMOKE2 = """Runtime preflight only. Use bash to save this intentionally incomplete procedure
in skill.py:
def run(controller):
    controller.reset()
    controller.complete_scan(4)
    controller.release()
Execute it once using execute_candidate. Rejection of the incomplete scan is expected;
do not repair it. After receiving feedback write completion.txt containing ready, read
it back, and finish. This checks tool and file delivery, not instrument success."""


def freeze():
    if (RUNS / "freeze.json").exists():
        raise FileExistsError("already frozen")
    paths = [
        HERE / n
        for n in [
            "run.py",
            "extension.ts",
            "source.md",
            "runtime.py",
        ]
    ]
    paths += [
        ROOT / "src/proprio" / n
        for n in [
            "flake_search_simulator.py",
            "flake_search_verifier.py",
            "instrument_qualification.py",
            "instrument_plugins.py",
            "instrument_types.py",
            "builtin_providers.py",
            "flake_search_types.py",
            "data/flake-search-preregistration.yaml",
        ]
    ]
    paths += [ROOT / "uv.lock", CONTRACT_PATH]
    base.write(
        RUNS / "freeze.json",
        {
            "time": time.time(),
            "files": {
                str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): base.digest(p)
                for p in paths
            },
            "prompts": {
                "system": SYSTEM,
                "author": AUTHOR,
                "repair": REPAIR,
                "consumer": CONSUMER,
                "smoke1": SMOKE1,
                "smoke2": SMOKE2,
            },
        },
    )


def check():
    f = json.loads((RUNS / "freeze.json").read_text())
    assert all(base.digest(ROOT / p) == h for p, h in f["files"].items())
    assert base.digest(RUNS / "sealed-cases.json") == C["private_hash"]


def execute(folder, candidate):
    meta = json.loads((folder / "run.json").read_text())
    candidate = candidate.resolve()
    assert candidate.is_relative_to((folder / "workspace").resolve())
    assert candidate.is_file() and candidate.stat().st_size <= 16384
    attempts = folder / "attempts"
    attempts.mkdir(exist_ok=True)
    n = len(list(attempts.glob("*.json")))
    if n >= meta["execution_limit"]:
        raise ValueError("development execution budget exhausted")
    code = candidate.read_text()
    visible = meta["contract"]["visible"]
    gates = evaluate(code, visible)
    ensure_available(gates, folder)
    base.write(attempts / f"{n + 1:02}.json", {"source": code, "gates": gates})
    print(
        json.dumps(
            {
                "attempt": n + 1,
                "conditions": [
                    {
                        "name": c["name"],
                        "result": g["result"],
                        "runtime_error": g["runtime_error"],
                        "trace": g["trace"],
                        "checks": [
                            {"check_id": x["check_id"], "passed": x["passed"]}
                            for x in g["checks"]
                            if x["check_id"] != "locked-condition-applied"
                        ],
                    }
                    for c, g in zip(visible, gates, strict=True)
                ],
            }
        )
    )


def ensure_available(gates, folder):
    if any(g["verdict"] == "HOLD" for g in gates):
        base.write(folder / "evaluator-failure.json", {"gates": gates})
        raise RuntimeError("Evaluator unavailable; stop study and preserve failure")


def require_receipt(name):
    r = json.loads((RUNS / name / "receipt.json").read_text())
    assert r["operationally_complete"], name
    return r


def package(pair, version):
    p = RUNS / "packages" / f"{pair}-{version}"
    hashes = json.loads((p / "hashes.json").read_text())
    assert all(base.digest(p / n) == h for n, h in hashes.items())
    return p


def publish_packages(version):
    check()
    stage = "draft" if version == "before" else "repair"
    for i in range(1, 4):
        folder = RUNS / f"{stage}-{i}"
        r = json.loads((folder / "receipt.json").read_text())
        if stage == "draft" and (not r["operationally_complete"] or not r["files_complete"]):
            raise RuntimeError("draft acquisition did not deliver matched pair; preserve and stop")
        dest = RUNS / "packages" / f"{i}-{version}"
        dest.mkdir(parents=True, exist_ok=False)
        use_original = stage == "repair" and (
            not r["operationally_complete"] or not r["files_complete"]
        )
        for name in ["skill.py", "SKILL.md"]:
            source = package(i, "before") / name if use_original else folder / "final" / name
            (dest / name).write_bytes(source.read_bytes())
        base.write(
            dest / "hashes.json", {n: base.digest(dest / n) for n in ["skill.py", "SKILL.md"]}
        )
        base.write(
            dest / "provenance.json",
            {"source": str(folder), "repair_complete": r["operationally_complete"], "receipt": r},
        )


def run(name):
    pi_binary = shutil.which(os.environ.get("PI_BIN", "pi"))
    if pi_binary is None:
        raise RuntimeError("Set PI_BIN to the Pi executable or put pi on PATH")
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise RuntimeError("Set OPENROUTER_API_KEY in the environment")
    if subprocess.check_output([pi_binary, "--version"], text=True).strip() != C["pi_version"]:
        raise RuntimeError("Pi version differs from the frozen contract")
    if shutil.which("bwrap") is None:
        raise RuntimeError("Install bubblewrap before starting a session")
    allowed = {"smoke-1", "smoke-2", *C["order"]}
    allowed.update(f"{stage}-{i}" for stage in ("draft", "repair") for i in (1, 2, 3))
    if name not in allowed:
        raise ValueError("Unknown study session")
    check()
    if list(RUNS.glob("*/evaluator-failure.json")):
        raise RuntimeError("Evaluator failure requires diagnosis before any launch")
    stage = name.split("-")[0]
    if stage != "smoke":
        assert all(require_receipt(f"smoke-{i}")["files_complete"] for i in [1, 2])
    if stage == "repair":
        assert all((RUNS / "packages" / f"{i}-before/hashes.json").exists() for i in [1, 2, 3])
    if stage == "consumer":
        assert all((RUNS / "packages" / f"{i}-after/hashes.json").exists() for i in [1, 2, 3])
    folder = RUNS / name
    folder.mkdir(exist_ok=False)
    receipts = [json.loads(p.read_text()) for p in RUNS.glob("*/receipt.json")]
    exposure = C["prior_exposure_usd"] + sum(
        r["usage"]["cost_usd"] + (0 if r["operationally_complete"] else 1.1) for r in receipts
    )
    if exposure + 3 * 1.1 > C["global_budget_usd"]:
        raise RuntimeError("global budget reserve exhausted")
    if stage == "consumer":
        workspace = RUNS / "agent-workspaces" / f"slot-{C['order'].index(name) + 1:02}"
        workspace.mkdir(parents=True)
        (folder / "workspace").symlink_to(workspace, target_is_directory=True)
    else:
        workspace = folder / "workspace"
        workspace.mkdir()
    (workspace / "source.md").write_bytes((HERE / "source.md").read_bytes())
    limit = 0 if stage == "draft" or name == "smoke-1" else (6 if stage == "repair" else 2)
    task = {
        "draft": AUTHOR,
        "repair": REPAIR,
        "consumer": CONSUMER,
        "smoke": SMOKE1 if name == "smoke-1" else SMOKE2,
    }[stage]
    if stage in ["consumer", "repair"]:
        pair = int(name.split("-")[1])
        version = name.split("-")[2] if stage == "consumer" else "before"
        src = package(pair, version)
        dest = workspace / "reference" if stage == "consumer" else workspace
        dest.mkdir(exist_ok=True)
        for n in ["skill.py", "SKILL.md"]:
            (dest / n).write_bytes((src / n).read_bytes())
    base.write(
        folder / "run.json",
        {
            "name": name,
            "stage": stage,
            "started": time.time(),
            "execution_limit": limit,
            "contract": C,
            "inputs": {
                str(p.relative_to(workspace)): base.digest(p)
                for p in workspace.rglob("*")
                if p.is_file()
            },
        },
    )
    cfg = folder / "pi-config"
    base.write(
        cfg / "models.json",
        {
            "providers": {
                C["provider"]: {
                    "modelOverrides": {
                        C["model"]: {
                            "maxTokens": C["max_output_tokens"],
                            "contextWindow": C["context_window"],
                            "cost": C["price"],
                        }
                    }
                }
            }
        },
    )
    base.write(
        cfg / "settings.json",
        {
            "compaction": {"enabled": False},
            "retry": {"enabled": False, "provider": {"maxRetries": 0, "timeoutMs": 180000}},
        },
    )
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(Path.home()),
        "OPENROUTER_API_KEY": os.environ["OPENROUTER_API_KEY"],
        "PI_CODING_AGENT_DIR": str(cfg),
        "PI_OFFLINE": "1",
        "PI_TELEMETRY": "0",
        "PROPRIO_ROOT": str(ROOT),
        "PROPRIO_RUN_DIR": str(folder),
        "PROPRIO_WORKSPACE": str(workspace),
        "PROPRIO_AUTHOR_ONLY": "1" if limit == 0 else "0",
        "PROPRIO_RUNNER": str(HERE / "run.py"),
        "PROPRIO_EXECUTION_LIMIT": str(max(1, limit)),
        "PROPRIO_MAX_MESSAGES": str(C["max_messages"]),
        "PROPRIO_MAX_OUTPUT_TOKENS": str(C["max_output_tokens"]),
        "PROPRIO_SESSION_COST": str(C["session_cost_usd"]),
    }
    args = [
        pi_binary,
        "--offline",
        "--provider",
        C["provider"],
        "--model",
        C["model"],
        "--thinking",
        C["thinking"],
        "--mode",
        "json",
        "--print",
        "--tools",
        "bash" if limit == 0 else "bash,execute_candidate",
        "--no-extensions",
        "-e",
        str(HERE / "extension.ts"),
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
        "--no-themes",
        "--no-session",
        "--system-prompt",
        SYSTEM,
        task,
    ]
    start = time.monotonic()
    with (folder / "trace.jsonl").open("w") as out, (folder / "stderr.txt").open("w") as err:
        p = subprocess.Popen(
            args, cwd=workspace, env=env, stdout=out, stderr=err, start_new_session=True
        )
        try:
            rc = p.wait(timeout=C["max_seconds"])
            timeout = False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            rc = p.wait()
            timeout = True
    u = base.usage(folder / "trace.jsonl")
    ext = (
        json.loads((folder / "usage.json").read_text()) if (folder / "usage.json").exists() else {}
    )
    reconciled = ext.get("messages") == u["assistant_messages"] and ext.get("tokens") == u["tokens"]
    reconciled &= abs(ext.get("cost_usd", -1) - u["cost_usd"]) < 1e-8
    complete = bool(
        rc == 0
        and not timeout
        and u["accounting_complete"]
        and not u["errors"]
        and reconciled
        and not ext.get("stopped_by_budget", True)
    )
    names = ["skill.py", "SKILL.md"] if stage in ["draft", "repair"] else ["skill.py"]
    if stage == "smoke":
        names += ["completion.txt"]
    final = folder / "final"
    final.mkdir()
    for n in names:
        src = workspace / n
        if src.is_file() and not src.is_symlink():
            (final / n).write_bytes(src.read_bytes())
    files = all((final / n).is_file() for n in names)
    attempts = len(list((folder / "attempts").glob("*.json")))
    if name == "smoke-2":
        complete &= attempts == 1
    r = {
        "name": name,
        "stage": stage,
        "operationally_complete": complete,
        "files_complete": files,
        "usage": u,
        "extension_usage": ext,
        "seconds": time.monotonic() - start,
        "timeout": timeout,
        "exit_code": rc,
        "executions": attempts,
        "final_hashes": {p.name: base.digest(p) for p in final.iterdir()},
    }
    base.write(folder / "receipt.json", r)
    print(json.dumps(r, indent=2))


def score():
    check()
    if not all((RUNS / n / "receipt.json").exists() for n in C["order"]):
        raise RuntimeError("finish all12consumers before private grading")
    cases = json.loads((RUNS / "sealed-cases.json").read_text())
    rows = []
    for name in C["order"]:
        folder = RUNS / name
        r = json.loads((folder / "receipt.json").read_text())
        p = folder / "final/skill.py"
        gates = evaluate(p.read_text(), cases) if p.exists() else []
        ensure_available(gates, folder)
        outcomes = [
            outcome(g, c["expected_status"]) for g, c in zip(gates, cases, strict=bool(gates))
        ]
        row = {
            **r,
            "pair": int(name.split("-")[1]),
            "version": name.split("-")[2],
            "success": r["operationally_complete"]
            and len(outcomes) == 8
            and all(x["passed"] for x in outcomes),
            "outcomes": outcomes,
        }
        base.write(folder / "private-grading.json", {"gates": gates, "result": row})
        rows.append(row)
    base.write(RUNS / "summary.json", {"sessions": rows, "comparison": summarize(rows)})
    print(
        json.dumps(
            [
                {k: r[k] for k in ["name", "success", "operationally_complete", "files_complete"]}
                for r in rows
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=RUNS)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("freeze")
    commands.add_parser("score")
    session = commands.add_parser("run")
    session.add_argument("name")
    packages = commands.add_parser("packages")
    packages.add_argument("version", choices=["before", "after"])
    execution = commands.add_parser("execute")
    execution.add_argument("folder", type=Path)
    execution.add_argument("candidate", type=Path)
    args = parser.parse_args()
    RUNS = args.run_dir.resolve()
    CONTRACT_PATH = args.contract.resolve()
    C = json.loads(CONTRACT_PATH.read_text())
    if args.command == "execute":
        execute(args.folder, args.candidate)
    elif args.command == "run":
        run(args.name)
    elif args.command == "packages":
        publish_packages(args.version)
    else:
        {"freeze": freeze, "score": score}[args.command]()
