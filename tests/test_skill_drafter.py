from __future__ import annotations

from proprio.skill_drafter import (
    SKILL_DRAFTER_SYSTEM_PROMPT,
    SkillDraft,
    SkillMarkdownDraft,
    _compile_skill_markdown,
    _normalize_skill_code,
    _source_bundle,
    load_cassette,
    reference_skill_drafts,
    run_reference_skill_admission,
    run_skill_admission,
    write_cassette,
)
from proprio.skill_gate import evaluate_skill

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

WRONG_RANGE = """
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
    _, source_sha256 = _source_bundle(variant)
    return SkillDraft(
        variant=variant,
        model="dsv4",
        source_sha256=source_sha256,
        skill_md=f"---\nname: {variant}\ndescription: fixture\n---\n\n# Run\n\nExecute safely.\n",
        skill_py=code,
        self_judgment={"verdict": "ACCEPT", "basis": ["matches sources"]},
        raw_response={"preserved_assistant_message": {"reasoning_content": None}},
    )


def test_cassette_round_trip_and_offline_gate(tmp_path) -> None:
    cassettes = tmp_path / "cassettes"
    write_cassette(_draft("correct", CORRECT), cassettes / "correct.json")
    write_cassette(_draft("wrong-range", WRONG_RANGE), cassettes / "wrong-range.json")
    assert load_cassette(cassettes / "correct.json").model == "dsv4"
    summary = run_skill_admission(cassettes, tmp_path / "output")
    assert summary["verdict"] == "PASS"
    assert summary["admit_proof"]
    assert summary["reject_proof"]


def test_fixture_code_expectations_remain_load_bearing() -> None:
    assert evaluate_skill(CORRECT).verdict == "ADMIT"
    assert evaluate_skill(WRONG_RANGE).verdict == "REJECT"


def test_drafter_prompt_has_source_and_preflight_contracts() -> None:
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


def test_bundled_controls_close_admit_and_reject_without_logs(tmp_path) -> None:
    summary = run_reference_skill_admission(tmp_path)
    assert summary["verdict"] == "PASS"
    assert summary["cases"]["correct"]["self_judgment"]["verdict"] == "ACCEPT"
    assert summary["cases"]["wrong-range"]["self_judgment"]["verdict"] == "ACCEPT"
    assert summary["source_provenance"]["mode"] == "bundled-reference-fixtures"
    assert all(draft.raw_response == {} for draft in reference_skill_drafts())
