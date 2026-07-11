# ruff: noqa: E501, RUF001
"""Evidence-bound OpenFlexure flagship demo.

This module presents one captured DSV4 repair episode and re-executes its
candidate skills against the pinned OpenFlexure simulator.  Presentation state
is written to a canonical JSON sidecar so the video never becomes the only
evidence for a claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from proprio.adaptive_microscopy import (
    AdaptiveMicroscopyController,
    AdaptiveOpenFlexureBackend,
    evaluate_adaptive_microscopy_skill,
)
from proprio.artifacts import file_sha256, write_canonical_json
from proprio.instrument_types import HardGateResult, SimulationScenario
from proprio.microscopy import OPENFLEXURE_REVISION

ROOT = Path(__file__).resolve().parents[2]
TRIAL = (
    ROOT
    / "artifacts"
    / "invalidated"
    / "adaptive-microscopy-causal-binding-transport-incomplete-v1"
    / "trials"
    / "trial-003"
)
REPAIR_PATH = TRIAL / "repair-truthful-round-1.json"
CAUSAL_PATH = ROOT / "artifacts" / "generated" / "accumulated-causal-evidence" / "summary.json"
DEVELOPMENT_PATH = (
    ROOT / "artifacts" / "generated" / "adaptive-microscopy-causal-development" / "summary.json"
)
EVOLUTION_PATH = ROOT / "cassettes" / "microscopy-evolution" / "summary.json"
METHOD_PATH = ROOT / "artifacts" / "generated" / "adaptive-method-freeze" / "manifest.json"
SOURCE_PATH = ROOT / "sources" / "development" / "microscope-autofocus" / "source.md"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def load_demo_evidence() -> dict[str, Any]:
    """Load the exact release artifacts used by the demo and verify key bindings."""

    repair = _load(REPAIR_PATH)
    causal = _load(CAUSAL_PATH)
    development = _load(DEVELOPMENT_PATH)
    evolution = _load(EVOLUTION_PATH)
    method = _load(METHOD_PATH)
    initial = repair["initial_candidate"]["skill_py"]
    final = repair["final_candidate"]["skill_py"]
    source_sha256 = file_sha256(SOURCE_PATH)
    if source_sha256 != "a0a9f0bc76230324fcadf3a15c9ca64bf0c6617114848ecc0c067a911c0feccc":
        raise ValueError("OpenFlexure source bundle no longer matches the captured repair")
    if _sha256_text(initial) != "d1b109f05b1f24d2dfed19c8f82d35af63a2d485bd3a149aa1b35e9b5695723c":
        raise ValueError("initial candidate hash mismatch")
    if _sha256_text(final) != "5cb84bc0af3f87b81ccb65ba244be185c35536be5cf510fd9880da1361b1de94":
        raise ValueError("repaired candidate hash mismatch")
    if causal["pairs"] != 18 or causal["truthful_successes"] != 14:
        raise ValueError("accumulated causal evidence does not match the release claim")
    if development["status"] != "EXPLORATORY_LOCKED":
        raise ValueError("OpenFlexure development evidence status changed")
    if evolution["status"] != "REJECTED":
        raise ValueError("drift-evolution evidence no longer demonstrates fail-closed promotion")
    return {
        "repair": repair,
        "causal": causal,
        "development": development,
        "evolution": evolution,
        "method": method,
        "initial_skill": initial,
        "final_skill": final,
        "source_sha256": source_sha256,
    }


class DemoState:
    """Thread-safe presentation and artifact state."""

    def __init__(self, artifact_path: Path, static_evidence: dict[str, Any]) -> None:
        self.lock = threading.Lock()
        self.artifact_path = artifact_path
        self.sequence = 0
        self.running = False
        self.complete = False
        self.failed = False
        self.view: dict[str, Any] = {
            "chapter": "0 / 8",
            "mode": "intro",
            "eyebrow": "PROPRIO · SIMULATION-VALIDATED PRE-DEPLOYMENT QUALIFICATION",
            "headline": "Can a model acquire an instrument skill — without promoting its own mistakes?",
            "lead": "One evidence-bound OpenFlexure acquisition trace. Live simulator executions; captured model repair; independent promotion authority.",
            "status": "READY",
            "tone": "neutral",
            "progress": 0,
            "camera": False,
            "camera_url": "",
            "code": "",
            "diff_old": "",
            "diff_new": "",
            "checks": [],
            "events": [],
            "metrics": [],
            "footnote": "Simulation qualifies pre-deployment behavior. Real hardware remains a separate gate.",
            "button": True,
        }
        self.artifact: dict[str, Any] = {
            "schema_version": "proprio.flagship_demo.v0.1",
            "claim": (
                "DSV4 used simulator feedback to repair an executable OpenFlexure skill; "
                "Proprio independently admitted the repaired candidate and rejected a later "
                "drift-evolution proposal that failed locked validation."
            ),
            "claim_boundary": {
                "candidate_qualification": "DEMONSTRATED",
                "broad_feedback_repair_mechanism": "ESTABLISHED_RETROSPECTIVELY",
                "single_protocol_openflexure_30_trial_claim": "NOT_ESTABLISHED",
                "cross_family_frozen_method_generalization": "NOT_ESTABLISHED",
                "real_hardware_qualification": "NOT_PERFORMED",
            },
            "bindings": static_evidence,
            "logical_events": [],
            "fresh_runs": [],
            "final_status": "PENDING",
        }
        self._write()

    def _write(self) -> None:
        write_canonical_json(self.artifact_path, self.artifact)

    def update(self, **values: Any) -> None:
        with self.lock:
            self.sequence += 1
            self.view.update(values)
            self.view["sequence"] = self.sequence
            self.artifact["logical_events"].append(
                {
                    "sequence": self.sequence,
                    "chapter": self.view["chapter"],
                    "mode": self.view["mode"],
                    "status": self.view["status"],
                    "headline": self.view["headline"],
                }
            )
            self._write()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.view)

    def add_run(self, label: str, gate: HardGateResult) -> None:
        with self.lock:
            payload = gate.model_dump(mode="json")
            payload["label"] = label
            self.artifact["fresh_runs"].append(payload)
            self._write()

    def finish(self, status: str) -> None:
        with self.lock:
            self.complete = status == "COMPLETE"
            self.failed = not self.complete
            self.running = False
            self.artifact["final_status"] = status
            self._write()


class ObservedController(AdaptiveMicroscopyController):
    """Controller that mirrors real skill operations into the presentation state."""

    def __init__(self, *args: Any, state: DemoState, label: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.state = state
        self.label = label
        self.ops: list[dict[str, str]] = []

    def _show(self, operation: str, detail: str, state: str = "running") -> None:
        if state == "running":
            for item in self.ops:
                if item["state"] == "running":
                    item["state"] = "passed"
        self.ops.append({"operation": operation, "detail": detail, "state": state})
        self.state.update(events=list(self.ops), status=operation.upper(), tone="live")

    def reset(self) -> None:
        self._show("reset", f"Prepare sample · move to z={self.start_z}")
        super().reset()

    def full_auto_calibrate(self) -> None:
        self._show("calibrate", "Camera calibration before autofocus")
        super().full_auto_calibrate()

    def fast_autofocus(self, dz_steps: int) -> dict[str, float]:
        self._show("autofocus", f"Centered {dz_steps:,}-step sweep · native MJPEG live")
        result = super().fast_autofocus(dz_steps)
        self._show("readback", f"Independent stage readback z={result['position_z']:.0f}")
        return result

    def settle(self) -> None:
        self._show("settle", "Wait for post-motion camera frame")
        super().settle()

    def capture_focus_series(self, repeats: int) -> dict[str, float]:
        self._show("measure", f"Acquire {repeats} fresh qualification frames")
        result = super().capture_focus_series(repeats)
        self._show("uncertainty", f"Repeated-measurement spread {result['relative_spread']:.4f}")
        return result

    def release(self) -> None:
        self._show("release", "Clear buffers and close instrument resources")
        super().release()
        for item in self.ops:
            if item["state"] == "running":
                item["state"] = "passed"
        self.state.update(events=list(self.ops))


class DemoOrchestrator:
    def __init__(
        self,
        *,
        state: DemoState,
        evidence: dict[str, Any],
        simulator_url: str,
        pace: float,
    ) -> None:
        self.state = state
        self.evidence = evidence
        self.simulator_url = simulator_url.rstrip("/")
        self.pace = pace

    def pause(self, seconds: float) -> None:
        time.sleep(max(0.05, seconds * self.pace))

    def stage(self, **values: Any) -> None:
        self.state.update(button=False, **values)

    def run_gate(self, label: str, source: str, start_z: int) -> HardGateResult:
        controller = ObservedController(
            AdaptiveOpenFlexureBackend(self.simulator_url),
            start_z=start_z,
            measurement_noise_level=2.0,
            stage_bias_steps=0,
            state=self.state,
            label=label,
        )
        gate = evaluate_adaptive_microscopy_skill(
            source,
            scenario=SimulationScenario.REPAIR,
            controller=controller,
        )
        self.state.add_run(label, gate)
        checks = [
            {
                "name": check.check_id,
                "passed": check.passed,
                "evidence": _compact_evidence(check.evidence),
            }
            for check in gate.checks
        ]
        self.state.update(
            checks=checks,
            status=gate.verdict,
            tone="pass" if gate.verdict == "ADMIT" else "fail",
            events=[
                *controller.ops,
                {
                    "operation": "external gate",
                    "detail": f"{sum(c.passed for c in gate.checks)}/{len(gate.checks)} checks passed",
                    "state": "passed" if gate.verdict == "ADMIT" else "failed",
                },
            ],
        )
        return gate

    def execute(self) -> None:
        try:
            self._execute()
        except Exception as exc:
            self.stage(
                chapter="STOP",
                mode="final",
                headline="Fail closed: the demonstration did not clear its evidence contract.",
                lead=f"{type(exc).__name__}: {exc}",
                status="STOPPED",
                tone="fail",
                progress=100,
                camera=False,
                metrics=[],
                checks=[],
                events=[],
                footnote="No retry or substituted condition was used.",
            )
            self.state.finish("FAILED")

    def _execute(self) -> None:
        repair = self.evidence["repair"]
        submission = repair["submission"]
        causal = self.evidence["causal"]
        development = self.evidence["development"]
        evolution = self.evidence["evolution"]
        camera_url = f"{self.simulator_url}/api/v3/camera/mjpeg_stream"

        self.stage(
            chapter="1 / 8",
            mode="source",
            eyebrow="UNFAMILIAR INSTRUMENT SOURCE · PINNED OPENFLEXURE REVISION",
            headline="The model receives operating constraints — not verifier thresholds.",
            lead="OpenFlexure camera, stage, and autofocus documentation are compiled into a bounded skill contract.",
            status="SOURCE LOCKED",
            tone="neutral",
            progress=8,
            camera=False,
            metrics=[
                {"label": "safe sweep", "value": "1,000–8,000 steps"},
                {"label": "focus reference", "value": "z = 0 ± 100"},
                {"label": "budget", "value": "8.3 s"},
                {"label": "source SHA", "value": self.evidence["source_sha256"][:12]},
            ],
            code="controller.reset()\ncontroller.full_auto_calibrate()\ncontroller.fast_autofocus(dz_steps)\ncontroller.capture_focus_series(3)\ncontroller.release()",
            checks=[],
            events=[],
            footnote="Verifier implementation and admission thresholds are withheld from the source bundle.",
        )
        self.pause(8)

        self.stage(
            chapter="2 / 8",
            mode="code",
            eyebrow="CAPTURED DSV4 CASSETTE · deepseek/deepseek-v4-flash-20260423",
            headline="DSV4 drafts an executable skill.",
            lead="The first candidate is syntactically valid and follows the instrument procedure. It has not been promoted.",
            status="CANDIDATE",
            tone="neutral",
            progress=18,
            camera=False,
            code=self.evidence["initial_skill"],
            metrics=[
                {"label": "candidate", "value": _sha256_text(self.evidence["initial_skill"])[:12]},
                {"label": "model role", "value": "propose"},
                {"label": "promotion", "value": "not authorized"},
            ],
            checks=[],
            events=[
                {"operation": "read sources", "detail": "Pinned source bundle", "state": "passed"},
                {
                    "operation": "draft skill",
                    "detail": "Runnable bounded Python",
                    "state": "passed",
                },
                {
                    "operation": "self-judgment",
                    "detail": "Not promotion authority",
                    "state": "pending",
                },
            ],
            footnote="Historical model content is replayed from the checked-in cassette; execution below is fresh.",
        )
        self.pause(8)

        self.stage(
            chapter="3 / 8",
            mode="gate",
            eyebrow="FRESH EXTERNAL SIMULATOR EXECUTION · HIDDEN FAILURE CONDITION",
            headline="The plausible draft misses the physical focus plane.",
            lead="Start z = −3,500. A 4,000-step centered sweep cannot reach the calibrated reference at z = 0.",
            status="EXECUTING",
            tone="live",
            progress=28,
            camera=True,
            camera_url=camera_url,
            code="",
            metrics=[
                {"label": "start z", "value": "−3,500"},
                {"label": "candidate sweep", "value": "4,000"},
                {"label": "required plane", "value": "0"},
            ],
            checks=[],
            events=[],
            footnote="The candidate runs. Only the independent execution and physics checks can promote it.",
        )
        initial_gate = self.run_gate("fresh-initial-failure", self.evidence["initial_skill"], -3500)
        if initial_gate.verdict != "REJECT":
            raise RuntimeError(f"initial candidate unexpectedly returned {initial_gate.verdict}")
        self.stage(
            chapter="3 / 8",
            mode="gate",
            headline="REJECT — procedural success was not physical validity.",
            lead="The code completed and released resources, but four physics-grounded autofocus checks failed.",
            status="REJECT",
            tone="fail",
            progress=38,
            camera=True,
            camera_url=camera_url,
            metrics=[
                {"label": "observed z", "value": _observed_z(initial_gate)},
                {
                    "label": "failed checks",
                    "value": str(sum(not c.passed for c in initial_gate.checks)),
                },
                {"label": "promotion", "value": "blocked"},
            ],
            footnote="A runnable skill is not a qualified instrument skill.",
        )
        self.pause(9)

        self.stage(
            chapter="4 / 8",
            mode="repair",
            eyebrow="CAPTURED DSV4 REPAIR · FEEDBACK REFERENCES PRESERVED",
            headline="DSV4 diagnoses the failed coverage and changes one parameter.",
            lead=submission["diagnosis"],
            status="SELF-JUDGMENT: ACCEPT",
            tone="warn",
            progress=48,
            camera=False,
            diff_old="controller.fast_autofocus(4000)",
            diff_new="controller.fast_autofocus(8000)",
            code="",
            checks=[
                {"name": ref.split(":")[-1], "passed": False, "evidence": "cited by DSV4"}
                for ref in submission["evidence_refs"]
            ],
            events=[
                {
                    "operation": "inspect feedback",
                    "detail": "4 grounded failure references",
                    "state": "passed",
                },
                {
                    "operation": "causal diagnosis",
                    "detail": "Sweep omitted z = 0",
                    "state": "passed",
                },
                {"operation": "repair", "detail": "4,000 → 8,000 steps", "state": "passed"},
                {
                    "operation": "self-judgment",
                    "detail": "ACCEPT · non-authoritative",
                    "state": "pending",
                },
            ],
            metrics=[
                {"label": "before coverage", "value": "−5,500…−1,500"},
                {"label": "after coverage", "value": "−7,500…500"},
                {"label": "budget", "value": "8.3 / 8.3 s"},
            ],
            footnote="The model can recommend promotion. It cannot execute promotion.",
        )
        self.pause(12)

        self.stage(
            chapter="5 / 8",
            mode="gate",
            eyebrow="FRESH QUALIFICATION · SAME FAILURE CONDITION",
            headline="The repaired skill must earn admission from scratch.",
            lead="Same simulator family. Same start z = −3,500. The external gate re-runs every execution and physical check.",
            status="EXECUTING",
            tone="live",
            progress=58,
            camera=True,
            camera_url=camera_url,
            checks=[],
            events=[],
            metrics=[
                {"label": "start z", "value": "−3,500"},
                {"label": "repaired sweep", "value": "8,000"},
                {"label": "promotion authority", "value": "Proprio"},
            ],
            footnote="No model judgment is used in the hard-gate verdict.",
        )
        repair_gate = self.run_gate("fresh-repaired-visible", self.evidence["final_skill"], -3500)
        if repair_gate.verdict != "ADMIT":
            raise RuntimeError(f"repaired candidate returned {repair_gate.verdict}")
        self.stage(
            chapter="5 / 8",
            mode="gate",
            headline="ADMIT — execution and physical qualification both passed.",
            lead="The repaired candidate covered the calibrated reference, selected the peak, repeated measurement, met the acquisition budget, and released resources.",
            status="ADMIT",
            tone="pass",
            progress=68,
            camera=True,
            camera_url=camera_url,
            metrics=[
                {"label": "observed z", "value": _observed_z(repair_gate)},
                {
                    "label": "checks",
                    "value": f"{sum(c.passed for c in repair_gate.checks)}/{len(repair_gate.checks)}",
                },
                {"label": "candidate", "value": repair_gate.skill_sha256[:12]},
            ],
            footnote="Candidate-level simulation admission is demonstrated; it is not hardware qualification.",
        )
        self.pause(8)

        sealed_runs: list[HardGateResult] = []
        for index, (label, start_z) in enumerate(
            (("sealed-history", 600), ("sealed-extreme", -3400)), 1
        ):
            self.stage(
                chapter="6 / 8",
                mode="gate",
                eyebrow=f"FRESH SEALED EXECUTION {index} / 2 · NO REPAIR FEEDBACK",
                headline="The selected candidate is replayed on a locked condition.",
                lead=f"{label.replace('-', ' ').title()} · start z = {start_z:+,}. Feedback is prohibited after selection.",
                status="EXECUTING",
                tone="live",
                progress=70 + index * 5,
                camera=True,
                camera_url=camera_url,
                checks=[],
                events=[],
                metrics=[
                    {"label": "condition", "value": label},
                    {"label": "start z", "value": f"{start_z:+,}"},
                    {"label": "feedback", "value": "sealed"},
                ],
                footnote="A failed sealed execution would stop the demo; no condition replacement is allowed.",
            )
            gate = self.run_gate(f"fresh-{label}", self.evidence["final_skill"], start_z)
            sealed_runs.append(gate)
            if gate.verdict != "ADMIT":
                raise RuntimeError(f"{label} returned {gate.verdict}")
            self.pause(4)

        self.stage(
            chapter="7 / 8",
            mode="evidence",
            eyebrow="RELEASE EVIDENCE · CLAIMS SEPARATED BY STRENGTH",
            headline="Simulator feedback caused repair; generalization remains an open claim.",
            lead=causal["broad_mechanism_claim_text"],
            status="MECHANISM ESTABLISHED",
            tone="pass",
            progress=88,
            camera=False,
            code="",
            diff_old="",
            diff_new="",
            checks=[],
            events=[
                {
                    "operation": "frozen confirmatory",
                    "detail": "6 / 6 truthful · 0 / 6 no-feedback",
                    "state": "passed",
                },
                {
                    "operation": "diagnostic cohort",
                    "detail": "5 / 8 truthful · 0 / 8 no-feedback",
                    "state": "passed",
                },
                {
                    "operation": "OpenFlexure pilot",
                    "detail": "3 / 4 truthful · 0 / 4 no-feedback",
                    "state": "passed",
                },
            ],
            metrics=[
                {"label": "paired units", "value": str(causal["pairs"])},
                {
                    "label": "truthful feedback",
                    "value": f"{causal['truthful_successes']} / {causal['pairs']}",
                },
                {
                    "label": "no feedback",
                    "value": f"{causal['none_successes']} / {causal['pairs']}",
                },
                {"label": "exact p", "value": f"{causal['mcnemar']['one_sided_exact_p']:.6f}"},
            ],
            footnote=(
                f"OpenFlexure 30-trial claim: {development['confirmatory_status']}. "
                "Frozen-method cross-family generalization: not established."
            ),
        )
        self.pause(12)

        self.stage(
            chapter="8 / 8",
            mode="drift",
            eyebrow="SIMULATED DEPLOYMENT DRIFT · CAPTURED EVOLUTION PROPOSAL",
            headline="A later model-authored evolution proposal is rejected — and cannot replace its parent.",
            lead="Drift was detected and the agent inspected feedback, but the proposal failed locked validation and independent review.",
            status="PROMOTION REFUSED",
            tone="fail",
            progress=95,
            camera=False,
            code="",
            diff_old="",
            diff_new="",
            checks=[
                {
                    "name": "drift-detected",
                    "passed": evolution["drift_detected"],
                    "evidence": "simulated condition changed",
                },
                {
                    "name": "feedback-inspected",
                    "passed": evolution["feedback_inspected_before_repair"],
                    "evidence": "before proposal",
                },
                {
                    "name": "historical-replay",
                    "passed": evolution["historical_replay_complete"],
                    "evidence": "required for promotion",
                },
                {
                    "name": "locked-validation",
                    "passed": evolution["locked_validation_verdict"] == "PASS",
                    "evidence": evolution["locked_validation_verdict"],
                },
                {
                    "name": "independent-review",
                    "passed": evolution["independent_reviewer_verdict"] == "ACCEPT",
                    "evidence": evolution["independent_reviewer_verdict"],
                },
            ],
            events=[
                {
                    "operation": "detect drift",
                    "detail": "Changed-condition failure observed",
                    "state": "passed",
                },
                {
                    "operation": "stage proposal",
                    "detail": evolution["proposal_skill_sha256"][:12],
                    "state": "passed",
                },
                {
                    "operation": "locked replay",
                    "detail": f"{evolution['locked_validation_cases']} cases · FAIL",
                    "state": "failed",
                },
                {
                    "operation": "promote",
                    "detail": "BLOCKED · parent remains active",
                    "state": "failed",
                },
            ],
            metrics=[
                {"label": "parent", "value": evolution["parent_skill_sha256"][:12]},
                {"label": "proposal", "value": evolution["proposal_skill_sha256"][:12]},
                {"label": "proposal status", "value": evolution["status"]},
                {"label": "parent immutable", "value": str(evolution["parent_immutable"]).lower()},
            ],
            footnote="This proves fail-closed evolution staging, not successful adaptation to drift.",
        )
        self.pause(12)

        self.stage(
            chapter="COMPLETE",
            mode="final",
            eyebrow="PROPRIO · VERIFIED IN SIMULATION",
            headline="The model acquired and repaired the skill. The model never controlled promotion.",
            lead="Source → draft → simulator failure → evidence-grounded repair → independent admission → sealed replay → drift rejection.",
            status="DEMO COMPLETE",
            tone="pass",
            progress=100,
            camera=False,
            code="",
            diff_old="controller.fast_autofocus(4000)",
            diff_new="controller.fast_autofocus(8000)",
            checks=[],
            events=[
                {"operation": "draft", "detail": "DSV4 produced runnable skill", "state": "passed"},
                {
                    "operation": "repair",
                    "detail": "Causally used simulator feedback",
                    "state": "passed",
                },
                {
                    "operation": "qualify",
                    "detail": "Independent physical gate admitted",
                    "state": "passed",
                },
                {
                    "operation": "evolve",
                    "detail": "Invalid proposal could not promote",
                    "state": "passed",
                },
            ],
            metrics=[
                {"label": "fresh initial", "value": initial_gate.verdict},
                {"label": "fresh repaired", "value": repair_gate.verdict},
                {
                    "label": "fresh sealed",
                    "value": f"{sum(g.verdict == 'ADMIT' for g in sealed_runs)} / 2",
                },
                {"label": "hardware gate", "value": "required"},
            ],
            footnote="Strongest supported claim: reproducible simulation-validated pre-deployment qualification. Real-hardware qualification is separate and required.",
        )
        self.state.finish("COMPLETE")


def _observed_z(gate: HardGateResult) -> str:
    for check in gate.checks:
        if check.check_id == "calibrated-focus-reference":
            return f"{float(check.evidence['observed_z']):+,.0f}"
    return "unavailable"


def _compact_evidence(evidence: dict[str, Any]) -> str:
    preferred = (
        "observed_z",
        "reference_z",
        "observed",
        "minimum",
        "maximum_seconds",
        "observed_seconds",
        "error",
    )
    pairs = [f"{key}={evidence[key]}" for key in preferred if key in evidence]
    return " · ".join(pairs[:3]) or "recorded"


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Proprio · OpenFlexure skill acquisition</title>
<style>
:root{--ink:#111410;--paper:#f4f0e6;--panel:#1a1f19;--line:#3a4038;--muted:#9ba495;--acid:#c9ff4f;--red:#ff6b5f;--amber:#ffcb66;--blue:#78d7ff}*{box-sizing:border-box}body{margin:0;background:var(--ink);color:var(--paper);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow:hidden}.shell{width:100vw;height:100vh;padding:30px 34px 28px;display:grid;grid-template-rows:82px 1fr 46px;gap:18px;background:radial-gradient(circle at 70% 20%,#263125 0,transparent 35%),var(--ink)}header{display:flex;align-items:flex-start;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:18px}.brand{display:flex;gap:20px;align-items:center}.mark{font-size:28px;font-weight:800;letter-spacing:-1.4px}.divider{width:1px;height:34px;background:var(--line)}.subbrand{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:1.4px;color:var(--muted);text-transform:uppercase;line-height:1.45}.statusrow{display:flex;gap:10px;align-items:center}.pill{border:1px solid var(--line);border-radius:999px;padding:9px 14px;font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:1.2px}.pill.live{border-color:var(--blue);color:var(--blue)}.pill.pass{border-color:var(--acid);color:var(--acid)}.pill.fail{border-color:var(--red);color:var(--red)}.pill.warn{border-color:var(--amber);color:var(--amber)}main{display:grid;grid-template-columns:1.4fr .82fr;gap:18px;min-height:0}.hero,.rail{background:rgba(26,31,25,.94);border:1px solid var(--line);border-radius:18px;overflow:hidden}.hero{display:grid;grid-template-rows:auto 1fr}.heroTop{padding:30px 34px 22px;border-bottom:1px solid var(--line)}.eyebrow{font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:1.5px;color:var(--acid);text-transform:uppercase;margin-bottom:16px}.headline{font-size:38px;line-height:1.06;letter-spacing:-1.5px;font-weight:720;max-width:1060px}.lead{margin-top:14px;color:#c5ccbf;font-size:17px;line-height:1.48;max-width:1050px}.content{min-height:0;padding:24px 34px 28px;display:grid;grid-template-rows:minmax(0,1fr) auto;gap:18px}#visual{min-height:0;overflow:hidden}.cameraWrap{height:100%;min-height:0;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#090b09;position:relative}.cameraWrap img{width:100%;height:100%;object-fit:contain;background:#090b09}.cameraLabel{position:absolute;left:14px;top:14px;background:rgba(10,12,10,.84);border:1px solid var(--line);padding:8px 10px;border-radius:7px;font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:1.1px}.code{height:100%;overflow:hidden;border:1px solid var(--line);border-radius:14px;background:#0b0e0b;padding:22px 24px;white-space:pre-wrap;font:14px/1.58 ui-monospace,SFMono-Regular,Menlo,monospace;color:#dce6d6}.diff{display:grid;grid-template-columns:1fr 1fr;gap:14px}.diffBox{border:1px solid var(--line);border-radius:14px;padding:22px;background:#0b0e0b;font:15px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.diffBox.old{border-color:#713d37;color:#ff9d94}.diffBox.new{border-color:#57722f;color:var(--acid)}.diffTag{font-size:10px;letter-spacing:1.4px;margin-bottom:14px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.metric{background:#222820;border:1px solid var(--line);border-radius:10px;padding:13px 14px;min-width:0}.metric label{display:block;color:var(--muted);font:9px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:1px;text-transform:uppercase;margin-bottom:7px}.metric b{display:block;font:700 15px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.rail{display:grid;grid-template-rows:auto 1fr 1fr;min-height:0}.railHead{padding:22px 24px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between}.chapter{font:700 12px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:1.2px}.authority{color:var(--muted);font:10px ui-monospace,SFMono-Regular,Menlo,monospace}.section{min-height:0;padding:18px 22px;border-bottom:1px solid var(--line);overflow:hidden}.section h3{font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);letter-spacing:1.4px;text-transform:uppercase;margin:0 0 13px}.list{display:flex;flex-direction:column;gap:8px}.item{display:grid;grid-template-columns:12px 1fr;gap:10px;align-items:start;padding:8px 0;border-bottom:1px solid #2b302a}.dot{width:8px;height:8px;margin-top:5px;border-radius:50%;background:#596156}.dot.passed{background:var(--acid)}.dot.failed{background:var(--red)}.dot.running{background:var(--blue);box-shadow:0 0 0 5px rgba(120,215,255,.12)}.dot.pending{background:var(--amber)}.item strong{display:block;font-size:12px;line-height:1.2}.item span{display:block;color:var(--muted);font:10px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;margin-top:3px}.empty{color:#697066;font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.start{height:100%;display:flex;align-items:center;justify-content:center}.start button{cursor:pointer;border:0;border-radius:10px;background:var(--acid);color:var(--ink);font-weight:800;font-size:15px;padding:17px 24px}.start button:hover{filter:brightness(1.08)}footer{display:grid;grid-template-columns:1fr 1.3fr;align-items:center;gap:20px}.progress{height:4px;background:#272c25;border-radius:99px;overflow:hidden}.bar{height:100%;background:var(--acid);transition:width .5s ease}.footnote{text-align:right;color:var(--muted);font:10px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}.claimLine{height:100%;display:flex;align-items:center;font-size:21px;line-height:1.45;color:#dbe1d6;max-width:1000px}.mode-evidence .claimLine,.mode-final .claimLine,.mode-drift .claimLine{font-size:25px}.hidden{display:none!important}
</style></head><body><div class="shell"><header><div class="brand"><div class="mark">PROPRIO</div><div class="divider"></div><div class="subbrand">Instrument operation<br>and observability</div></div><div class="statusrow"><span class="pill">SIMULATION ONLY</span><span id="status" class="pill">READY</span></div></header><main><section id="hero" class="hero"><div class="heroTop"><div id="eyebrow" class="eyebrow"></div><div id="headline" class="headline"></div><div id="lead" class="lead"></div></div><div class="content"><div id="visual"></div><div id="metrics" class="metrics"></div></div></section><aside class="rail"><div class="railHead"><span id="chapter" class="chapter"></span><span class="authority">MODEL PROPOSES · GATE DECIDES</span></div><div class="section"><h3>Operation trace</h3><div id="events" class="list"></div></div><div class="section"><h3>Independent checks</h3><div id="checks" class="list"></div></div></aside></main><footer><div class="progress"><div id="bar" class="bar"></div></div><div id="footnote" class="footnote"></div></footer></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function items(target,rows,checks=false){const el=document.getElementById(target);if(!rows?.length){el.innerHTML='<div class="empty">No records at this stage.</div>';return}const ordered=checks?[...rows].sort((a,b)=>Number(a.passed)-Number(b.passed)):rows.slice(-6);el.innerHTML=ordered.slice(0,6).map(x=>{const state=checks?(x.passed?'passed':'failed'):(x.state||'pending');const title=checks?x.name:x.operation;const detail=checks?x.evidence:x.detail;return `<div class="item"><i class="dot ${state}"></i><div><strong>${esc(title)}</strong><span>${esc(detail)}</span></div></div>`}).join('')}
function render(s){window.scrollTo(0,0);document.getElementById('eyebrow').textContent=s.eyebrow;document.getElementById('headline').textContent=s.headline;document.getElementById('lead').textContent=s.lead;document.getElementById('chapter').textContent=s.chapter;document.getElementById('footnote').textContent=s.footnote;document.getElementById('bar').style.width=s.progress+'%';const st=document.getElementById('status');st.textContent=s.status;st.className='pill '+(s.tone||'');const hero=document.getElementById('hero');hero.className='hero mode-'+s.mode;let v='';if(s.button){v='<div class="start"><button id="begin">RUN EVIDENCE-BOUND DEMO</button></div>'}else if(s.camera){v=`<div class="cameraWrap"><img src="${esc(s.camera_url)}" alt="Live OpenFlexure simulator stream"><div class="cameraLabel">NATIVE OPENFLEXURE MJPEG · LIVE</div></div>`}else if(s.diff_old||s.diff_new){v=`<div class="diff"><div class="diffBox old"><div class="diffTag">− INITIAL</div>${esc(s.diff_old)}</div><div class="diffBox new"><div class="diffTag">+ REPAIRED</div>${esc(s.diff_new)}</div></div>`}else if(s.code){v=`<div class="code">${esc(s.code)}</div>`}else{v=`<div class="claimLine">${esc(s.lead)}</div>`}document.getElementById('visual').innerHTML=v;if(s.button)document.getElementById('begin').onclick=()=>fetch('/start',{method:'POST'});document.getElementById('metrics').innerHTML=(s.metrics||[]).map(m=>`<div class="metric"><label>${esc(m.label)}</label><b title="${esc(m.value)}">${esc(m.value)}</b></div>`).join('');items('events',s.events);items('checks',s.checks,true)}
let seq=-1;async function poll(){try{const r=await fetch('/state.json',{cache:'no-store'});const s=await r.json();if(s.sequence!==seq){seq=s.sequence;render(s)}}catch(e){}setTimeout(poll,250)}poll();
</script></body></html>"""

# Mirrors the public Dynamical Systems identity in
# dynamical-systems-landing/src/app/globals.css.  Keep this surface light-only,
# slate-blue as the single UI accent, and Source Sans 3 as the primary face.
BRAND_CSS = r"""
:root {
  --ink: #fafaf8;
  --paper: #1a1a1a;
  --panel: #ffffff;
  --line: #e5e5e3;
  --muted: #5a5a5a;
  --acid: #3d5a80;
  --red: #b23a2e;
  --amber: #3d5a80;
  --blue: #3d5a80;
  --secondary: #f0f0ee;
}
body {
  background: var(--ink);
  color: var(--paper);
  font-family: "Source Sans 3", "Helvetica Neue", sans-serif;
  font-kerning: normal;
  -webkit-font-smoothing: antialiased;
}
.shell {
  padding: 24px 32px 22px;
  grid-template-rows: 70px minmax(0, 1fr) 38px;
  gap: 14px;
  background: var(--ink);
}
header {
  align-items: center;
  padding-bottom: 14px;
  border-color: var(--line);
}
.brand { gap: 14px; }
.mark {
  color: var(--paper);
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.035em;
  text-transform: uppercase;
}
.divider { height: 28px; background: var(--line); }
.subbrand,
.pill,
.eyebrow,
.cameraLabel,
.code,
.diffBox,
.metric label,
.metric b,
.chapter,
.authority,
.section h3,
.item span,
.empty,
.footnote {
  font-family: "JetBrains Mono", ui-monospace, monospace;
}
.subbrand {
  color: var(--muted);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.09em;
  line-height: 1.35;
}
.pill {
  padding: 7px 11px;
  border-color: var(--line);
  border-radius: 5px;
  color: var(--muted);
  background: var(--panel);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
}
.pill.live,
.pill.pass,
.pill.warn { border-color: #8fa0b6; color: var(--acid); }
.pill.fail { border-color: #d9a8a3; color: var(--red); }
main {
  grid-template-columns: minmax(0, 1.52fr) minmax(390px, 0.68fr);
  gap: 14px;
}
.hero,
.rail {
  background: var(--panel);
  border-color: var(--line);
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(26, 26, 26, 0.025);
}
.heroTop {
  padding: 22px 32px 18px;
  border-color: var(--line);
}
.eyebrow {
  margin-bottom: 13px;
  color: var(--acid);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.11em;
}
.headline {
  max-width: 1000px;
  color: var(--paper);
  font-size: 34px;
  font-weight: 600;
  line-height: 1.04;
  letter-spacing: -0.035em;
  text-wrap: balance;
}
.lead {
  max-width: 980px;
  margin-top: 12px;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.42;
}
.content { padding: 22px 32px 26px; gap: 14px; }
.cameraWrap {
  border-color: #d8d8d5;
  border-radius: 6px;
  background: #111111;
}
.cameraLabel {
  top: 12px;
  left: 12px;
  padding: 7px 9px;
  border-color: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  color: #fafaf8;
  background: rgba(26, 26, 26, 0.88);
  font-size: 9px;
  font-weight: 500;
}
.code {
  padding: 22px 24px;
  border-color: var(--line);
  border-radius: 6px;
  color: var(--paper);
  background: #f5f5f3;
  font-size: 13px;
  line-height: 1.55;
}
.diff { gap: 12px; }
.diffBox {
  padding: 20px;
  border-radius: 6px;
  color: var(--paper);
  background: #f8f8f6;
  font-size: 14px;
}
.diffBox.old { border-color: #dfb9b5; color: var(--red); }
.diffBox.new { border-color: #aeb9c8; color: var(--acid); }
.diffTag { font-size: 9px; letter-spacing: 0.1em; }
.metrics { gap: 8px; }
.metric {
  padding: 11px 12px;
  border-color: var(--line);
  border-radius: 5px;
  background: var(--secondary);
}
.metric label {
  margin-bottom: 5px;
  color: var(--muted);
  font-size: 8px;
  letter-spacing: 0.08em;
}
.metric b { color: var(--paper); font-size: 13px; font-weight: 600; }
.railHead { padding: 18px 20px; border-color: var(--line); }
.chapter { color: var(--paper); font-size: 10px; letter-spacing: 0.09em; }
.authority { color: var(--muted); font-size: 8px; letter-spacing: 0.05em; }
.section { padding: 16px 20px; border-color: var(--line); }
.section h3 {
  margin-bottom: 10px;
  color: var(--muted);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.09em;
}
.list { gap: 4px; }
.item {
  gap: 9px;
  padding: 7px 0;
  border-color: #eeeeec;
}
.item strong { color: var(--paper); font-size: 12px; font-weight: 600; }
.item span { color: var(--muted); font-size: 9px; line-height: 1.3; }
.dot { width: 7px; height: 7px; background: #b5b5b2; }
.dot.passed { background: var(--acid); }
.dot.failed { background: var(--red); }
.dot.running {
  background: var(--acid);
  box-shadow: 0 0 0 4px rgba(61, 90, 128, 0.12);
}
.dot.pending { background: #9aa9bc; }
.empty { color: #8a8a87; font-size: 9px; }
.start button {
  padding: 13px 22px;
  border-radius: 999px;
  color: #fafaf8;
  background: var(--acid);
  box-shadow: 0 1px 2px rgba(26, 26, 26, 0.08);
  font-family: "Source Sans 3", "Helvetica Neue", sans-serif;
  font-size: 14px;
  font-weight: 600;
}
.start button:hover { background: #324d70; filter: none; }
footer { gap: 18px; }
.progress { height: 3px; background: #e8e8e6; }
.bar { background: var(--acid); }
.footnote { color: var(--muted); font-size: 8px; line-height: 1.35; }
.claimLine {
  max-width: 920px;
  color: var(--paper);
  font-size: 20px;
  line-height: 1.42;
}
.mode-evidence .claimLine,
.mode-final .claimLine,
.mode-drift .claimLine { font-size: 23px; }
@media (max-width: 1100px) {
  body { overflow: auto; }
  .shell {
    height: auto;
    min-height: 100vh;
    grid-template-rows: auto auto auto;
  }
  main { grid-template-columns: 1fr; }
  .hero { min-height: 720px; }
  .rail { min-height: 620px; }
}
@media (max-width: 700px) {
  .shell { padding: 16px; }
  header { align-items: flex-start; gap: 14px; }
  .brand { align-items: flex-start; }
  .statusrow { flex-direction: column; align-items: flex-end; }
  .heroTop,
  .content { padding: 22px; }
  .headline { font-size: 31px; }
  .lead { font-size: 15px; }
  .metrics { grid-template-columns: repeat(2, 1fr); }
  .diff { grid-template-columns: 1fr; }
  .railHead { gap: 12px; }
  .authority { text-align: right; }
  footer { grid-template-columns: 1fr; }
  .footnote { text-align: left; }
}
"""

HTML = HTML.replace("</head>", f"<style>{BRAND_CSS}</style></head>")
HTML = HTML.replace(
    '<div class="mark">PROPRIO</div><div class="divider"></div>'
    '<div class="subbrand">Instrument operation<br>and observability</div>',
    '<div class="mark">PROPRIO</div><div class="divider"></div>'
    '<div class="subbrand">Dynamical Systems<br>qualification record</div>',
)
HTML = HTML.replace("RUN EVIDENCE-BOUND DEMO", "START TRACE")


def make_handler(state: DemoState, orchestrator: DemoOrchestrator) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send(
            self, payload: bytes, media_type: str, status: HTTPStatus = HTTPStatus.OK
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._send(HTML.encode(), "text/html; charset=utf-8")
            elif path == "/state.json":
                self._send(json.dumps(state.snapshot()).encode(), "application/json")
            elif path == "/artifact.json":
                self._send(state.artifact_path.read_bytes(), "application/json")
            elif path == "/health":
                self._send(b'{"status":"ok"}', "application/json")
            elif path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            else:
                self._send(b"not found", "text/plain", HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/start":
                self._send(b"not found", "text/plain", HTTPStatus.NOT_FOUND)
                return
            with state.lock:
                if state.running or state.complete:
                    self._send(b'{"status":"already_started"}', "application/json")
                    return
                state.running = True
            threading.Thread(target=orchestrator.execute, daemon=True).start()
            self._send(b'{"status":"started"}', "application/json", HTTPStatus.ACCEPTED)

    return Handler


def static_bindings(
    evidence: dict[str, Any], *, simulator_url: str, simulator_entropy: str
) -> dict[str, Any]:
    method = evidence["method"]
    method_sha = (
        method.get("method_sha256") or method.get("freeze_sha256") or file_sha256(METHOD_PATH)
    )
    return {
        "model_requested": "deepseek/deepseek-v4-flash",
        "model_resolved": "deepseek/deepseek-v4-flash-20260423",
        "provider": "GMICloud",
        "source": {"path": str(SOURCE_PATH.relative_to(ROOT)), "sha256": evidence["source_sha256"]},
        "captured_repair": {
            "path": str(REPAIR_PATH.relative_to(ROOT)),
            "sha256": file_sha256(REPAIR_PATH),
        },
        "accumulated_causal_evidence": {
            "path": str(CAUSAL_PATH.relative_to(ROOT)),
            "sha256": file_sha256(CAUSAL_PATH),
        },
        "drift_evolution": {
            "path": str(EVOLUTION_PATH.relative_to(ROOT)),
            "sha256": file_sha256(EVOLUTION_PATH),
        },
        "method_freeze": {"path": str(METHOD_PATH.relative_to(ROOT)), "sha256": method_sha},
        "simulator": {
            "name": "OpenFlexure microscope server",
            "revision": OPENFLEXURE_REVISION,
            "url": simulator_url,
            "rng_entropy": simulator_entropy,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--simulator-url", default="http://127.0.0.1:5122")
    parser.add_argument("--simulator-entropy", default="unavailable")
    parser.add_argument("--pace", type=float, default=1.0)
    parser.add_argument(
        "--artifact",
        type=Path,
        default=ROOT / "artifacts" / "demo" / "proprio-openflexure-flagship.json",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    evidence = load_demo_evidence()
    state = DemoState(
        args.artifact,
        static_bindings(
            evidence,
            simulator_url=args.simulator_url,
            simulator_entropy=args.simulator_entropy,
        ),
    )
    orchestrator = DemoOrchestrator(
        state=state,
        evidence=evidence,
        simulator_url=args.simulator_url,
        pace=args.pace,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state, orchestrator))
    print(f"Proprio flagship demo: http://{args.host}:{args.port}", flush=True)
    print(f"Evidence sidecar: {args.artifact}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
