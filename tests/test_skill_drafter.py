from __future__ import annotations

from pathlib import Path

from proprio.skill_drafter import (
    SKILL_DRAFTER_SYSTEM_PROMPT,
    SkillDraft,
    SkillMarkdownDraft,
    _compile_skill_markdown,
    _normalize_skill_code,
    load_cassette,
    run_skill_admission,
    write_cassette,
)
from proprio.skill_gate import evaluate_skill

ROOT = Path(__file__).resolve().parents[1]

CORRECT = """
def run(controller):
    controller.identify()
    controller.reset()
    controller.set_current_limit(0.002)
    controller.set_measurement_range(0.01)
    controller.set_voltage(1.0)
    controller.enable_output()
    current = controller.measure_current()
    controller.disable_output()
    return {"current_a": current}
"""

LEGACY = """
def run(controller):
    controller.identify()
    controller.reset()
    controller.set_current_limit(0.0002)
    controller.set_measurement_range(0.0001)
    controller.set_voltage(1.0)
    controller.enable_output()
    current = controller.measure_current()
    controller.disable_output()
    return {"current_a": current}
"""


def _draft(variant: str, code: str) -> SkillDraft:
    return SkillDraft(
        variant=variant,
        model="dsv4",
        source_sha256="a" * 64,
        skill_md=f"---\nname: {variant}\ndescription: fixture\n---\n\n# Run\n\nExecute safely.\n",
        skill_py=code,
        self_judgment={"verdict": "ACCEPT", "basis": ["matches sources"]},
        raw_response={"preserved_assistant_message": {"reasoning_content": None}},
    )


def test_cassette_round_trip_and_offline_gate(tmp_path) -> None:
    cassettes = tmp_path / "cassettes"
    write_cassette(_draft("correct", CORRECT), cassettes / "correct.json")
    write_cassette(_draft("legacy", LEGACY), cassettes / "legacy.json")
    assert load_cassette(cassettes / "correct.json").model == "dsv4"
    summary = run_skill_admission(cassettes, tmp_path / "output")
    assert summary["verdict"] == "PASS"
    assert summary["admit_proof"]
    assert summary["reject_proof"]


def test_fixture_code_expectations_remain_load_bearing() -> None:
    assert evaluate_skill(CORRECT).verdict == "ADMIT"
    assert evaluate_skill(LEGACY).verdict == "REJECT"


def test_dsv4_drafter_prompt_has_source_and_preflight_contracts() -> None:
    assert "Authority and precedence" in SKILL_DRAFTER_SYSTEM_PROMPT
    assert "Treat the supplied sources as complete" in SKILL_DRAFTER_SYSTEM_PROMPT
    assert "private preflight" in SKILL_DRAFTER_SYSTEM_PROMPT
    assert "independent physical checks own admission" in SKILL_DRAFTER_SYSTEM_PROMPT


def test_model_authored_skill_fields_compile_to_valid_markdown() -> None:
    compiled = _compile_skill_markdown(
        SkillMarkdownDraft(
            name="keithley-current",
            description="Measure current safely.",
            body="# Keithley current\n\n1. Reset the instrument.",
        )
    )
    assert compiled.startswith(
        '---\nname: keithley-current\ndescription: "Measure current safely."'
    )
    assert "\n---\n\n# Keithley current" in compiled
    assert _normalize_skill_code("def run(controller):\n    return {}") == (
        "def run(controller):\n    return {}\n"
    )


def test_checked_in_dsv4_cassettes_close_admit_and_reject(tmp_path) -> None:
    summary = run_skill_admission(ROOT / "cassettes/dsv4", tmp_path)
    assert summary["verdict"] == "PASS"
    assert summary["cases"]["correct"]["self_judgment"]["verdict"] == "ACCEPT"
    assert summary["cases"]["legacy"]["self_judgment"]["verdict"] == "ACCEPT"
    for variant in ("correct", "legacy"):
        draft = load_cassette(ROOT / f"cassettes/dsv4/{variant}.json")
        assert "reasoning_content" in draft.raw_response["preserved_assistant_message"]


def test_failed_live_schema_attempts_remain_first_class_evidence(tmp_path) -> None:
    for name in ("schema-invalid-2026-07-09", "missing-description-2026-07-09"):
        attempt = ROOT / f"cassettes/dsv4/attempts/{name}"
        summary = run_skill_admission(attempt, tmp_path / name)
        assert summary["verdict"] == "FAIL"
        assert "skill-md-schema" in summary["cases"]["correct"]["failed_checks"]
