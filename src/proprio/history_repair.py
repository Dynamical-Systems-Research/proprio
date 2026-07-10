"""Prepare regression-safe parents for simulated deployment-drift evolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from proprio.artifacts import write_canonical_json
from proprio.instrument_agent import (
    DISCLOSED_EXECUTOR_CONTRACT,
    HISTORY_REPLAY_CONTRACT,
    SKILL_ENGINEER_SYSTEM_PROMPT,
    InstrumentSkillAgent,
)
from proprio.instrument_qualification import evaluate_instrument_skill
from proprio.instrument_study import INSTRUMENT_IDS, _response_transport_evidence
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    RepairEpisode,
    SimulationScenario,
)


def _candidate_path(root: Path, instrument_id: str) -> Path:
    return root / instrument_id / "candidate.json"


def _repair_path(root: Path, instrument_id: str) -> Path:
    return root / instrument_id / "repair-truthful.json"


def run_live_history_repair(candidate_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Repair changed support while requiring a separate nominal replay."""

    output_dir.mkdir(parents=True, exist_ok=True)
    agent = InstrumentSkillAgent(
        skill_system_prompt=(
            SKILL_ENGINEER_SYSTEM_PROMPT + DISCLOSED_EXECUTOR_CONTRACT + HISTORY_REPLAY_CONTRACT
        )
    )
    write_canonical_json(output_dir / "health.json", agent.client.health())
    for instrument_id in INSTRUMENT_IDS:
        path = _repair_path(output_dir, instrument_id)
        if path.is_file():
            continue
        candidate = CandidatePackage.model_validate_json(
            _candidate_path(candidate_dir, instrument_id).read_text(encoding="utf-8")
        )
        episode = agent.repair(
            candidate,
            feedback_arm=FeedbackArm.TRUTHFUL,
            scenario=SimulationScenario.REPAIR,
            require_history=True,
            history_scenarios=(SimulationScenario.NOMINAL,),
            max_turns=14,
        )
        write_canonical_json(path, episode)
    summary = summarize_history_repair(output_dir)
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def summarize_history_repair(root: Path) -> dict[str, Any]:
    rows = []
    responses: list[dict[str, Any]] = []
    for instrument_id in INSTRUMENT_IDS:
        path = _repair_path(root, instrument_id)
        if not path.is_file():
            continue
        episode = RepairEpisode.model_validate_json(path.read_text(encoding="utf-8"))
        responses.extend(episode.raw_responses)
        history = evaluate_instrument_skill(
            instrument_id,
            episode.final_candidate.skill_py,
            scenario=SimulationScenario.NOMINAL,
        )
        rows.append(
            {
                "instrument_id": instrument_id,
                "family": episode.family,
                "target_verdict": episode.final_gate.verdict,
                "history_verdict": history.verdict,
                "qualified_parent": episode.final_gate.verdict == "ADMIT"
                and history.verdict == "ADMIT",
                "agent_status": episode.agent_status,
                "submissions": len(episode.submissions),
                "model_turns": len(episode.raw_responses),
            }
        )
    qualified = sum(row["qualified_parent"] for row in rows)
    claim_gates = {
        "complete_capture": "PASS" if len(rows) == len(INSTRUMENT_IDS) else "FAIL",
        "qualified_parent_archive": ("PASS" if rows and qualified == len(rows) else "FAIL"),
    }
    result = {
        "schema_version": "proprio.history_repair.v0.1",
        "instrument_count": len(rows),
        "qualified_parents": qualified,
        "rows": rows,
        "transport_evidence": _response_transport_evidence(responses),
        "claim_gates": claim_gates,
    }
    result["verdict"] = "PASS" if all(value == "PASS" for value in claim_gates.values()) else "FAIL"
    return result
