from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/synthetic_provider"
INSTRUMENT = "third_party.synthetic.counter"


def _run_cli(arguments: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-m", "proprio.cli", *arguments],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(completed.stdout)


def test_separately_installed_provider_runs_real_cli_loop(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    site = tmp_path / "site"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist), str(FIXTURE)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    wheel = next(dist.glob("*.whl"))
    subprocess.run(
        ["uv", "pip", "install", "--target", str(site), str(wheel)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "SKILL.md").write_text(
        "---\nname: synthetic-counter\ndescription: Measure the synthetic counter.\n---\n"
        "\n# Operate\nReset and measure once.\n",
        encoding="utf-8",
    )
    (candidate / "skill.py").write_text(
        "def run(controller):\n    controller.reset()\n    return controller.measure()\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(site), str(ROOT / "src"), env.get("PYTHONPATH", "")])

    inspection = _run_cli(["inspect-source", "--instrument", INSTRUMENT], cwd=tmp_path, env=env)
    visible = _run_cli(
        [
            "execute-candidate",
            "--instrument",
            INSTRUMENT,
            "--candidate-dir",
            str(candidate),
            "--output-dir",
            str(tmp_path / "visible"),
        ],
        cwd=tmp_path,
        env=env,
    )
    locked = _run_cli(
        [
            "verify-locked",
            "--instrument",
            INSTRUMENT,
            "--candidate-dir",
            str(candidate),
            "--output-dir",
            str(tmp_path / "locked"),
        ],
        cwd=tmp_path,
        env=env,
    )

    assert inspection["instrument_id"] == INSTRUMENT
    assert inspection["provider"]["distribution"] == "proprio-synthetic-provider"
    assert visible["decision"] == "ADMIT"
    assert locked["decision"] == "ADMIT"
