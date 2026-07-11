from __future__ import annotations

from pathlib import Path

from proprio.adaptive_search import DebugSuiteResult, FixturePreflightReport, SearchReport
from proprio.generalization_instruments import load_generalization_source
from proprio.generalization_study import (
    _one_sided_exact_p,
    run_live_generalization_panel,
    run_live_generalization_session,
    summarize_generalization_panel,
)
from proprio.instrument_types import CandidatePackage


def test_session_seals_before_locked_qualification(monkeypatch, tmp_path: Path) -> None:
    instrument_id = "helao-gamry-cv"
    _, source_hash = load_generalization_source(instrument_id)
    candidate = CandidatePackage(
        instrument_id=instrument_id,
        skill_md=("---\nname: helao-gamry-cv\ndescription: Test procedure.\n---\n\nRun test.\n"),
        skill_py="def run(controller):\n    return {}\n",
        self_judgment={"verdict": "ACCEPT", "basis": []},
        source_sha256=source_hash,
        prompt_sha256="prompt",
        model="test-model",
        raw_response={},
    )
    suite = DebugSuiteResult(
        instrument_id=instrument_id,
        candidate_sha256="candidate",
        conditions=(),
        verdict="ADMIT",
    )
    search = SearchReport(
        instrument_id=instrument_id,
        entries=(),
        repairs=(),
        selected=candidate,
        selected_suite=suite,
        initial_width=6,
        survivor_count=3,
        repair_rounds=6,
        model_candidates_generated=6,
        verdict="CANDIDATE",
    )

    monkeypatch.setattr(
        "proprio.generalization_study.verify_generalization_method",
        lambda _path: {"verdict": "PASS"},
    )
    monkeypatch.setattr(
        "proprio.generalization_study._read_json",
        lambda _path: {"method_sha256": "method"},
    )
    monkeypatch.setattr(
        "proprio.generalization_study.run_generalization_preflight",
        lambda _instrument_id: FixturePreflightReport(cases=(), verdict="PASS"),
    )
    monkeypatch.setattr(
        "proprio.generalization_study.run_archive_search", lambda *args, **kwargs: search
    )

    def locked_after_seal(*args, **kwargs):
        assert (tmp_path / "selection-seal.json").is_file()
        return suite

    monkeypatch.setattr("proprio.generalization_study.evaluate_debug_suite", locked_after_seal)
    monkeypatch.setattr(
        "proprio.generalization_study._run_evolution_proposal",
        lambda *args, **kwargs: {"status": "STAGED"},
    )
    monkeypatch.setattr(
        "proprio.generalization_study._transport_evidence",
        lambda _path: {"verdict": "PASS"},
    )
    summary = run_live_generalization_session(
        instrument_id,
        session_index=0,
        output_dir=tmp_path,
        freeze_path=tmp_path / "freeze.json",
        panel_manifest_sha256="panel",
    )
    assert summary["final_decision"] == "ADMIT"
    assert summary["candidate_variants"] == 6
    assert summary["panel_manifest_sha256"] == "panel"
    assert (tmp_path / "locked-qualification.json").is_file()
    assert (tmp_path / "session-manifest.json").is_file()


def test_panel_summary_requires_each_family_to_clear_every_gate(tmp_path: Path) -> None:
    assert _one_sided_exact_p(6, 0) == 0.015625
    for instrument_id in (
        "north-pipette-calibration",
        "helao-gamry-cv",
        "clslab-light-spectrometer",
    ):
        for index in range(30):
            path = tmp_path / instrument_id / f"session-{index:03d}" / "summary.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "{"
                '"final_decision":"ADMIT",'
                '"locked_verdict":"PASS",'
                '"selected_visible_verdict":"ADMIT",'
                '"provenance_valid":true,'
                '"protocol_valid":true,'
                '"truthful_repair_qualified":true,'
                '"truthful_repair_regressed":false,'
                '"no_feedback_repair_qualified":false,'
                '"evolution_status":"STAGED"'
                "}",
                encoding="utf-8",
            )
    summary = summarize_generalization_panel(tmp_path, sessions_per_family=30)
    assert summary["verdict"] == "PASS"
    assert all(family["verdict"] == "PASS" for family in summary["families"])


def test_panel_summary_excludes_protocol_invalid_scientific_success(tmp_path: Path) -> None:
    for instrument_id in (
        "north-pipette-calibration",
        "helao-gamry-cv",
        "clslab-light-spectrometer",
    ):
        for index in range(30):
            path = tmp_path / instrument_id / f"session-{index:03d}" / "summary.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            protocol_valid = not (instrument_id == "helao-gamry-cv" and index == 0)
            path.write_text(
                "{"
                '"final_decision":"ADMIT",'
                '"locked_verdict":"PASS",'
                '"selected_visible_verdict":"ADMIT",'
                '"provenance_valid":true,'
                f'"protocol_valid":{str(protocol_valid).lower()},'
                '"truthful_repair_qualified":true,'
                '"truthful_repair_regressed":false,'
                '"no_feedback_repair_qualified":false,'
                '"evolution_status":"STAGED"'
                "}",
                encoding="utf-8",
            )
    summary = summarize_generalization_panel(tmp_path, sessions_per_family=30)
    helao = next(row for row in summary["families"] if row["instrument_id"] == "helao-gamry-cv")
    assert helao["protocol_valid_sessions"] == 29
    assert helao["claim_gates"]["transport_integrity"] == "FAIL"
    assert helao["verdict"] == "FAIL"


def test_binding_runner_rejects_nonregistered_panel_size(tmp_path: Path) -> None:
    try:
        run_live_generalization_panel(tmp_path, sessions_per_family=1)
    except ValueError as exc:
        assert "exactly 30" in str(exc)
    else:
        raise AssertionError("nonregistered binding panel size was accepted")
