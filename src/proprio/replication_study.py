"""Independent-sample replication study for the frozen confirmatory method."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from proprio.artifacts import write_canonical_json
from proprio.confirmatory_instruments import CONFIRMATORY_INSTRUMENTS
from proprio.confirmatory_qualification import (
    CONFIRMATORY_FAMILIES,
    evaluate_confirmatory_skill,
    load_confirmatory_source,
)
from proprio.confirmatory_validation import (
    evaluate_confirmatory_validation,
    seal_confirmatory_candidate,
)
from proprio.instrument_agent import (
    DISCLOSED_EXECUTOR_CONTRACT,
    HISTORY_REPLAY_CONTRACT,
    SKILL_ENGINEER_SYSTEM_PROMPT,
    InstrumentSkillAgent,
)
from proprio.instrument_study import _repair_protocol_evidence, _response_transport_evidence
from proprio.instrument_types import (
    CandidatePackage,
    FeedbackArm,
    RepairEpisode,
    SimulationScenario,
)
from proprio.microscopy import (
    FAMILY as MICROSCOPY_FAMILY,
)
from proprio.microscopy import (
    INSTRUMENT_ID as MICROSCOPY_INSTRUMENT_ID,
)
from proprio.microscopy import (
    evaluate_live_microscopy_skill,
    load_microscopy_source,
)
from proprio.policy import DSV4Client
from proprio.schema import canonical_json

PREREGISTRATION = Path(__file__).with_name("data") / "expanded-confirmatory-preregistration.yaml"
INSTRUMENT_IDS = (*tuple(sorted(CONFIRMATORY_INSTRUMENTS)), MICROSCOPY_INSTRUMENT_ID)
FAMILIES = {**CONFIRMATORY_FAMILIES, MICROSCOPY_INSTRUMENT_ID: MICROSCOPY_FAMILY}


def load_expanded_source(instrument_id: str) -> tuple[str, str]:
    if instrument_id == MICROSCOPY_INSTRUMENT_ID:
        return load_microscopy_source(instrument_id)
    return load_confirmatory_source(instrument_id)


def evaluate_expanded_skill(
    instrument_id: str,
    source: str,
    *,
    scenario: SimulationScenario = SimulationScenario.NOMINAL,
    condition: dict[str, float] | None = None,
    microscopy_base_url: str = "http://127.0.0.1:5100",
) -> Any:
    if instrument_id == MICROSCOPY_INSTRUMENT_ID:
        return evaluate_live_microscopy_skill(
            instrument_id,
            source,
            scenario=scenario,
            condition=condition,
            base_url=microscopy_base_url,
        )
    return evaluate_confirmatory_skill(
        instrument_id,
        source,
        scenario=scenario,
        condition=condition,
    )


def microscopy_locked_conditions(count: int) -> tuple[dict[str, Any], ...]:
    rows = []
    for index in range(count):
        digest = hashlib.sha256(f"microscope-lock:240719:{index}".encode()).hexdigest()
        fraction = int(digest[:12], 16) / float(0xFFFFFFFFFFFF)
        start_z = 1100.0 + 300.0 * fraction
        rows.append(
            {
                "condition_id": f"microscope_{digest[:16]}",
                "index": index,
                "start_z": round(start_z, 6),
            }
        )
    return tuple(rows)


def evaluate_replication_validation(
    candidate: CandidatePackage,
    *,
    microscopy_base_url: str,
    microscopy_case_count: int,
) -> dict[str, Any]:
    if candidate.instrument_id != MICROSCOPY_INSTRUMENT_ID:
        report = evaluate_confirmatory_validation(
            candidate,
            seal_confirmatory_candidate(candidate),
        )
        return report.model_dump(mode="json")
    conditions = microscopy_locked_conditions(microscopy_case_count)
    cases = []
    for condition in conditions:
        gate = evaluate_live_microscopy_skill(
            candidate.instrument_id,
            candidate.skill_py,
            scenario=SimulationScenario.REPAIR,
            condition={"start_z": condition["start_z"]},
            base_url=microscopy_base_url,
        )
        cases.append({**condition, "gate": gate.model_dump(mode="json")})
    suite_sha256 = hashlib.sha256(canonical_json(conditions)).hexdigest()
    passed = sum(case["gate"]["verdict"] == "ADMIT" for case in cases)
    return {
        "schema_version": "proprio.microscopy_locked_validation.v0.1",
        "instrument_id": candidate.instrument_id,
        "candidate_sha256": hashlib.sha256(candidate.skill_py.encode()).hexdigest(),
        "suite_sha256": suite_sha256,
        "cases": cases,
        "passed_cases": passed,
        "verdict": "PASS" if passed == len(cases) else "FAIL",
    }


def _wilson(successes: int, count: int) -> list[float]:
    if count == 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    rate = successes / count
    denominator = 1.0 + z * z / count
    center = (rate + z * z / (2.0 * count)) / denominator
    half = z * math.sqrt(rate * (1.0 - rate) / count + z * z / (4.0 * count * count))
    return [max(0.0, center - half / denominator), min(1.0, center + half / denominator)]


def initial_execution_succeeded(gate: dict[str, Any]) -> bool:
    """Separate code execution from downstream measurement-validity admission."""

    checks = {str(check["check_id"]): bool(check["passed"]) for check in gate.get("checks", [])}
    return (
        checks.get("static-safety") is True
        and checks.get("runtime-completed") is True
        and gate.get("runtime_error") is None
        and gate.get("status") != "unavailable"
    )


def replication_seed(instrument_id: str, replicate: int, *, seed_base: int) -> int:
    """Derive a stable panel-global seed even when a run is sharded by instrument."""

    if instrument_id not in INSTRUMENT_IDS:
        raise KeyError(instrument_id)
    return seed_base + INSTRUMENT_IDS.index(instrument_id) * 100 + int(replicate)


def select_replication_ids(
    replicate_ids: tuple[int, ...] | None,
    *,
    count: int,
) -> tuple[int, ...]:
    selected = replicate_ids or tuple(range(count))
    if len(set(selected)) != len(selected) or any(
        replicate < 0 or replicate >= count for replicate in selected
    ):
        raise ValueError("replicate IDs must be unique and inside the frozen replication panel")
    return selected


def _paths(root: Path, instrument_id: str, replicate: int) -> tuple[Path, Path, Path, Path]:
    directory = root / instrument_id / f"replicate-{replicate:02d}"
    return (
        directory / "candidate.json",
        directory / "initial-nominal.json",
        directory / "repair.json",
        directory / "validation.json",
    )


def run_live_replication_study(
    output_dir: Path,
    *,
    instrument_ids: tuple[str, ...] = INSTRUMENT_IDS,
    replicate_ids: tuple[int, ...] | None = None,
    microscopy_base_url: str = "http://127.0.0.1:5100",
) -> dict[str, Any]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    config = prereg["replication"]
    output_dir.mkdir(parents=True, exist_ok=True)
    client = DSV4Client()
    write_canonical_json(output_dir / "health.json", client.health())
    acquisition_prompt = SKILL_ENGINEER_SYSTEM_PROMPT + DISCLOSED_EXECUTOR_CONTRACT
    evolution_prompt = acquisition_prompt + HISTORY_REPLAY_CONTRACT
    selected_replicates = select_replication_ids(
        replicate_ids,
        count=config["independent_generations_per_instrument"],
    )

    def evaluator(instrument_id: str, source: str, **kwargs: Any) -> Any:
        return evaluate_expanded_skill(
            instrument_id,
            source,
            microscopy_base_url=microscopy_base_url,
            **kwargs,
        )

    for instrument_id in instrument_ids:
        if instrument_id not in INSTRUMENT_IDS:
            raise KeyError(instrument_id)
        for replicate in selected_replicates:
            candidate_path, initial_path, repair_path, validation_path = _paths(
                output_dir, instrument_id, replicate
            )
            seed = replication_seed(
                instrument_id,
                replicate,
                seed_base=config["seed_base"],
            )
            draft_agent = InstrumentSkillAgent(
                client=client,
                skill_system_prompt=acquisition_prompt,
                source_loader=load_expanded_source,
                evaluator=evaluator,
                families=FAMILIES,
                sampling_temperature=config["temperature"],
                sampling_top_p=config["top_p"],
                sampling_seed=seed,
            )
            repair_agent = InstrumentSkillAgent(
                client=client,
                skill_system_prompt=evolution_prompt,
                source_loader=load_expanded_source,
                evaluator=evaluator,
                families=FAMILIES,
                sampling_temperature=config["temperature"],
                sampling_top_p=config["top_p"],
                sampling_seed=seed,
            )
            if candidate_path.is_file():
                candidate = CandidatePackage.model_validate_json(
                    candidate_path.read_text(encoding="utf-8")
                )
            else:
                candidate = draft_agent.draft(instrument_id)
                write_canonical_json(candidate_path, candidate)
            if not initial_path.is_file():
                initial_gate = evaluator(
                    instrument_id,
                    candidate.skill_py,
                    scenario=SimulationScenario.NOMINAL,
                )
                write_canonical_json(initial_path, initial_gate)
            if repair_path.is_file():
                episode = RepairEpisode.model_validate_json(repair_path.read_text(encoding="utf-8"))
            else:
                episode = repair_agent.repair(
                    candidate,
                    feedback_arm=FeedbackArm.TRUTHFUL,
                    scenario=SimulationScenario.REPAIR,
                    require_history=True,
                    history_scenarios=(SimulationScenario.NOMINAL,),
                    max_turns=config["max_model_turns"],
                )
                write_canonical_json(repair_path, episode)
            if not validation_path.is_file():
                validation = evaluate_replication_validation(
                    episode.final_candidate,
                    microscopy_base_url=microscopy_base_url,
                    microscopy_case_count=config["microscopy_locked_cases_per_candidate"],
                )
                write_canonical_json(validation_path, validation)
    summary = summarize_replication_study(output_dir, instrument_ids=instrument_ids)
    write_canonical_json(output_dir / "summary.json", summary)
    return summary


def summarize_replication_study(
    root: Path,
    *,
    instrument_ids: tuple[str, ...] = INSTRUMENT_IDS,
) -> dict[str, Any]:
    prereg = yaml.safe_load(PREREGISTRATION.read_text(encoding="utf-8"))
    config = prereg["replication"]
    metrics = prereg["metrics"]
    rows: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    for instrument_id in instrument_ids:
        for replicate in range(config["independent_generations_per_instrument"]):
            candidate_path, initial_path, repair_path, validation_path = _paths(
                root, instrument_id, replicate
            )
            if not all(
                path.is_file()
                for path in (candidate_path, initial_path, repair_path, validation_path)
            ):
                continue
            candidate = CandidatePackage.model_validate_json(candidate_path.read_text())
            initial = json.loads(initial_path.read_text())
            episode = RepairEpisode.model_validate_json(repair_path.read_text())
            validation = json.loads(validation_path.read_text())
            protocol = _repair_protocol_evidence(episode)
            target_passed = episode.final_gate.verdict == "ADMIT"
            history_event = next(
                (
                    event
                    for event in reversed(episode.tool_events)
                    if event["name"] == "run_history"
                ),
                None,
            )
            history_passed = bool(history_event and history_event["result"].get("all_admit"))
            locked_passed = validation["verdict"] == "PASS"
            provenance_complete = (
                protocol["feedback_inspected_before_repair"]
                and protocol["repair_evidence_grounded"]
                and protocol["replayed_after_repair"]
            )
            qualified = (
                episode.agent_status == "CANDIDATE"
                and target_passed
                and history_passed
                and locked_passed
                and provenance_complete
            )
            responses.extend(candidate.raw_response.get("responses", []))
            responses.extend(episode.raw_responses)
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "family": FAMILIES[instrument_id],
                    "replicate": replicate,
                    "initial_executable": initial_execution_succeeded(initial),
                    "initial_measurement_valid": initial["verdict"] == "ADMIT",
                    "target_passed": target_passed,
                    "history_passed": history_passed,
                    "locked_passed": locked_passed,
                    "provenance_complete": provenance_complete,
                    "qualified": qualified,
                    "initial_skill_sha256": hashlib.sha256(candidate.skill_py.encode()).hexdigest(),
                    "final_skill_sha256": hashlib.sha256(
                        episode.final_candidate.skill_py.encode()
                    ).hexdigest(),
                    "agent_status": episode.agent_status,
                    "seed": replication_seed(
                        instrument_id,
                        replicate,
                        seed_base=config["seed_base"],
                    ),
                }
            )

    per_instrument: dict[str, Any] = {}

    def primary_outcome(row: dict[str, Any]) -> str:
        if row["qualified"]:
            return "qualified"
        if row["agent_status"] != "CANDIDATE":
            return f"terminal_status_{str(row['agent_status']).lower()}"
        if not row["target_passed"]:
            return "target_replay_failed"
        if not row["history_passed"]:
            return "history_replay_failed"
        if not row["provenance_complete"]:
            return "provenance_incomplete"
        if not row["locked_passed"]:
            return "locked_validation_failed"
        return "unclassified_failure"

    for instrument_id in instrument_ids:
        selected = [row for row in rows if row["instrument_id"] == instrument_id]
        count = len(selected)
        initial = sum(row["initial_executable"] for row in selected)
        initially_valid = sum(row["initial_measurement_valid"] for row in selected)
        qualified = sum(row["qualified"] for row in selected)
        per_instrument[instrument_id] = {
            "family": FAMILIES[instrument_id],
            "replicates": count,
            "initial_executable": initial,
            "initial_executable_rate": initial / count if count else 0.0,
            "initial_executable_wilson_95": _wilson(initial, count),
            "initial_measurement_valid": initially_valid,
            "initial_measurement_valid_rate": initially_valid / count if count else 0.0,
            "initial_measurement_valid_wilson_95": _wilson(initially_valid, count),
            "qualified": qualified,
            "qualification_rate": qualified / count if count else 0.0,
            "qualification_wilson_95": _wilson(qualified, count),
            "initial_unique_skills": len({row["initial_skill_sha256"] for row in selected}),
            "final_unique_skills": len({row["final_skill_sha256"] for row in selected}),
            "outcomes": dict(sorted(Counter(primary_outcome(row) for row in selected).items())),
        }
    transport = _response_transport_evidence(responses)
    complete = len(rows) == len(instrument_ids) * config["independent_generations_per_instrument"]
    initial_executable = sum(row["initial_executable"] for row in rows)
    initial_measurement_valid = sum(row["initial_measurement_valid"] for row in rows)
    qualified = sum(row["qualified"] for row in rows)
    row_count = len(rows)
    gates = {
        "complete_capture": "PASS" if complete else "FAIL",
        "initial_executable_floor": "PASS"
        if per_instrument
        and all(
            item["initial_executable_rate"] >= metrics["replicated_initial_executable_rate_min"]
            for item in per_instrument.values()
        )
        else "FAIL",
        "qualification_floor": "PASS"
        if per_instrument
        and all(
            item["qualification_rate"] >= metrics["replicated_qualification_rate_min"]
            for item in per_instrument.values()
        )
        else "FAIL",
        "unsafe_promotion_prevention": "PASS"
        if not any(row["qualified"] and not row["locked_passed"] for row in rows)
        else "FAIL",
        "frozen_model_route": "PASS"
        if transport["providers"] == [prereg["model"]["provider"]]
        and transport["resolved_models"] == [prereg["model"]["resolved_revision"]]
        and transport["reasoning_state_missing"] == 0
        else "FAIL",
    }
    result = {
        "schema_version": "proprio.replication_study.v0.1",
        "instrument_count": len(instrument_ids),
        "family_count": len({FAMILIES[item] for item in instrument_ids}),
        "replicate_count": len(rows),
        "sampling": {
            "temperature": config["temperature"],
            "top_p": config["top_p"],
            "seed_base": config["seed_base"],
        },
        "overall": {
            "initial_executable": initial_executable,
            "initial_executable_rate": initial_executable / row_count if row_count else 0.0,
            "initial_executable_wilson_95": _wilson(initial_executable, row_count),
            "initial_measurement_valid": initial_measurement_valid,
            "initial_measurement_valid_rate": (
                initial_measurement_valid / row_count if row_count else 0.0
            ),
            "initial_measurement_valid_wilson_95": _wilson(initial_measurement_valid, row_count),
            "qualified": qualified,
            "qualification_rate": qualified / row_count if row_count else 0.0,
            "qualification_wilson_95": _wilson(qualified, row_count),
            "outcomes": dict(sorted(Counter(primary_outcome(row) for row in rows).items())),
        },
        "per_instrument": per_instrument,
        "transport_evidence": transport,
        "rows": rows,
        "claim_gates": gates,
    }
    result["verdict"] = "PASS" if all(value == "PASS" for value in gates.values()) else "FAIL"
    return result
