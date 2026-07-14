"""Learn-from-sources front end for instrument skills."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from proprio.artifacts import write_bytes, write_canonical_json
from proprio.catalog import parse_skill_markdown
from proprio.policy import OpenAICompatibleClient, _extract_json
from proprio.skill_gate import evaluate_skill

SKILL_DRAFTER_SYSTEM_PROMPT = """You are the deterministic compiler for a scientific
instrument skill.

Authority and precedence:
1. The driver contract is authoritative for allowed controller methods, call order, and
   return shape.
2. The fixture worksheet is authoritative for numerical settings in this draft.
3. The response contract below is authoritative for serialization.

Treat the supplied sources as complete. Do not infer or repair facts from outside them. Your
self-judgment assesses source fidelity only; it cannot admit the skill. Simulator execution and
independent physical checks own admission.

Before emitting the answer, perform a private preflight:
- output is one JSON object with exactly skill_md, skill_py, and self_judgment;
- skill_md contains exactly name, description, and body; name is lowercase-hyphenated,
  description is one line, and body begins with a Markdown heading and has executable
  instructions;
- skill_py defines exactly run(controller), has no imports, uses only source-declared methods,
  sets compliance and range before enabling output, disables output before return, and returns
  current_a;
- every numerical setting exactly matches the fixture worksheet;
- self_judgment is ACCEPT exactly when the package is faithful to the supplied sources.

Emit JSON only. Do not use Markdown fences or add commentary outside the JSON object."""

REFERENCE_SKILLS = {
    "correct": {
        "name": "keithley-2450-measure-current",
        "description": "Measure current through a 1 kOhm load with the registered settings.",
        "code": """def run(controller):
    controller.reset()
    controller.set_current_limit(0.002)
    controller.set_measurement_range(0.01)
    controller.set_voltage(1.0)
    controller.enable_output()
    current_a = controller.measure_current()
    controller.disable_output()
    return {'current_a': current_a}
""",
    },
    "wrong-range": {
        "name": "keithley-2450-wrong-range-control",
        "description": "Negative control using the stale range and compliance settings.",
        "code": """def run(controller):
    controller.reset()
    controller.set_current_limit(200e-6)
    controller.set_measurement_range(100e-6)
    controller.set_voltage(1.000)
    controller.enable_output()
    current_a = controller.measure_current()
    controller.disable_output()
    return {'current_a': current_a}
""",
    },
}


class SkillDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "proprio.skill_draft.v0.1"
    variant: str
    model: str
    source_sha256: str
    skill_md: str
    skill_py: str
    self_judgment: dict[str, Any]
    raw_response: dict[str, Any]


class SkillMarkdownDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(min_length=1)
    body: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_markdown(self) -> SkillMarkdownDraft:
        if "\n" in self.description:
            raise ValueError("description must be one line")
        if not self.body.lstrip().startswith("#"):
            raise ValueError("body must begin with a Markdown heading")
        return self


def _compile_skill_markdown(draft: SkillMarkdownDraft) -> str:
    description = json.dumps(draft.description, ensure_ascii=False)
    return f"---\nname: {draft.name}\ndescription: {description}\n---\n\n{draft.body.strip()}\n"


def _normalize_skill_code(source: str) -> str:
    return source.rstrip() + "\n"


def _source_bundle(variant: str) -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2] / "sources" / "keithley-2450"
    contract = (root / "driver-contract.md").read_text(encoding="utf-8")
    if variant == "correct":
        fixture_path = "fixture-correct.md"
        source_name = fixture_path
    elif variant == "wrong-range":
        fixture_path = "fixture-wrong-range.md"
        source_name = fixture_path
    elif variant == "legacy":
        fixture_path = "fixture-wrong-range.md"
        source_name = "fixture-legacy.md"
    else:
        raise ValueError(f"unsupported source variant: {variant}")
    fixture = (root / fixture_path).read_text(encoding="utf-8")
    text = f"# SOURCE: driver-contract.md\n{contract}\n# SOURCE: {source_name}\n{fixture}"
    return text, hashlib.sha256(text.encode()).hexdigest()


def _prompt(source_text: str, variant: str) -> str:
    return f"""Draft one reusable Keithley 2450 instrument skill from the supplied sources.

Variant identifier: {variant}

Return JSON only, with exactly these keys:
- skill_md: object with exactly three string keys: name, description, and body. name MUST be
  lowercase words separated by hyphens. description MUST be one line. body MUST begin with a
  Markdown heading and contain executable workflow instructions. Do not emit YAML delimiters;
  the host compiles these model-authored fields into SKILL.md deterministically.
- skill_py: Python source defining exactly `run(controller)`, with no imports and only
  controller methods named in the source.
- self_judgment: object with verdict (`ACCEPT` or `REJECT`) and basis (array of strings).

Use the fixture's explicit compliance and range values; do not substitute autorange.
Self-judge against the supplied sources only. If the code faithfully follows them and is
internally consistent, return ACCEPT. The downstream simulator and physics verifier, not this
self-judgment, own admission.

SOURCES BEGIN
{source_text}
SOURCES END
"""


class SkillDrafter:
    def __init__(self, client: OpenAICompatibleClient | None = None) -> None:
        self.client = client or OpenAICompatibleClient()

    def draft(self, variant: str) -> SkillDraft:
        if variant not in {"correct", "wrong-range"}:
            raise ValueError("variant must be correct or wrong-range")
        source_text, source_hash = _source_bundle(variant)
        prompt = _prompt(source_text, variant)
        response = self.client.create_chat_completion(
            model=self.client.model,
            messages=[
                {
                    "role": "system",
                    "content": SKILL_DRAFTER_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=8192,
        )
        message = response.choices[0].message
        parsed = _extract_json(message.content or "")
        required = {"skill_md", "skill_py", "self_judgment"}
        if set(parsed) != required:
            raise ValueError(f"model draft keys must be {sorted(required)}")
        if not isinstance(parsed["self_judgment"], dict):
            raise ValueError("self_judgment must be an object")
        markdown = SkillMarkdownDraft.model_validate(parsed["skill_md"])
        raw = response.model_dump(mode="json")
        message_payload = message.model_dump(mode="json")
        for field in ("reasoning", "reasoning_details", "reasoning_content"):
            value = getattr(message, field, None)
            if value is not None:
                message_payload[field] = value
        raw["preserved_assistant_message"] = message_payload
        raw["request"] = {
            "variant": variant,
            "source_sha256": source_hash,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        }
        return SkillDraft(
            variant=variant,
            model=self.client.model,
            source_sha256=source_hash,
            skill_md=_compile_skill_markdown(markdown),
            skill_py=_normalize_skill_code(str(parsed["skill_py"])),
            self_judgment=parsed["self_judgment"],
            raw_response=raw,
        )


def write_cassette(draft: SkillDraft, path: Path) -> None:
    write_canonical_json(path, draft)


def load_cassette(path: Path) -> SkillDraft:
    return SkillDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))


def recompile_cassette(path: Path) -> SkillDraft:
    """Rebuild compiled package fields from the untouched raw model response."""

    draft = load_cassette(path)
    content = draft.raw_response["preserved_assistant_message"]["content"]
    parsed = _extract_json(content)
    markdown = SkillMarkdownDraft.model_validate(parsed["skill_md"])
    rebuilt = draft.model_copy(
        update={
            "skill_md": _compile_skill_markdown(markdown),
            "skill_py": _normalize_skill_code(str(parsed["skill_py"])),
        }
    )
    write_cassette(rebuilt, path)
    return rebuilt


def draft_skill_cassettes(cassette_dir: Path) -> dict[str, Any]:
    drafter = SkillDrafter()
    health = drafter.client.health()
    results = []
    for variant in ("correct", "wrong-range"):
        draft = drafter.draft(variant)
        write_cassette(draft, cassette_dir / f"{variant}.json")
        results.append(
            {
                "variant": variant,
                "source_sha256": draft.source_sha256,
                "self_judgment": draft.self_judgment,
                "skill_sha256": hashlib.sha256(draft.skill_py.encode()).hexdigest(),
            }
        )
    return {"health": health, "drafts": results}


def reference_skill_drafts() -> tuple[SkillDraft, ...]:
    """Build compact deterministic controls without shipping model transcripts."""

    drafts = []
    for variant, fixture in REFERENCE_SKILLS.items():
        _, source_hash = _source_bundle(variant)
        markdown = _compile_skill_markdown(
            SkillMarkdownDraft(
                name=fixture["name"],
                description=fixture["description"],
                body=(
                    f"# {fixture['name']}\n\n"
                    "Execute the bounded procedure. Simulator execution and independent "
                    "physical checks own admission."
                ),
            )
        )
        drafts.append(
            SkillDraft(
                variant=variant,
                model="reference-fixture",
                source_sha256=source_hash,
                skill_md=markdown,
                skill_py=fixture["code"],
                self_judgment={
                    "verdict": "ACCEPT",
                    "basis": ["The candidate matches its supplied fixture source."],
                },
                raw_response={},
            )
        )
    return tuple(drafts)


def run_reference_skill_admission(output_dir: Path) -> dict[str, Any]:
    """Replay the bundled positive and negative controls through the real admission gate."""

    with tempfile.TemporaryDirectory(prefix="proprio-skill-admission-") as directory:
        cassette_dir = Path(directory)
        for draft in reference_skill_drafts():
            write_cassette(draft, cassette_dir / f"{draft.variant}.json")
        return run_skill_admission(cassette_dir, output_dir)


def run_skill_admission(cassette_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases: dict[str, Any] = {}
    cases_to_cassettes = {
        "correct": ("correct.json", {"correct"}),
        "wrong-range": ("wrong-range.json", {"wrong-range", "legacy"}),
    }
    for case_name, (cassette_name, allowed_variants) in cases_to_cassettes.items():
        draft = load_cassette(cassette_dir / cassette_name)
        if draft.variant not in allowed_variants:
            raise ValueError(f"cassette variant mismatch: {case_name}")
        _, expected_source_sha256 = _source_bundle(draft.variant)
        if draft.source_sha256 != expected_source_sha256:
            raise ValueError(f"cassette source mismatch: {case_name}")
        variant_dir = output_dir / case_name
        write_bytes(variant_dir / "SKILL.md", draft.skill_md.encode(), "text/markdown")
        write_bytes(variant_dir / "skill.py", draft.skill_py.encode(), "text/x-python")
        skill_md_error = None
        try:
            parse_skill_markdown(draft.skill_md)
        except Exception as exc:
            skill_md_error = f"{type(exc).__name__}: {exc}"
        admission = evaluate_skill(draft.skill_py)
        package_admitted = admission.verdict == "ADMIT" and skill_md_error is None
        admission_payload = admission.as_dict()
        admission_payload["skill_md_schema"] = {
            "status": "succeeded" if skill_md_error is None else "failed",
            "error": skill_md_error,
        }
        admission_payload["code_verdict"] = admission.verdict
        admission_payload["verdict"] = "ADMIT" if package_admitted else "REJECT"
        write_canonical_json(variant_dir / "admission.json", admission_payload)
        cases[case_name] = {
            "model": draft.model,
            "source_sha256": draft.source_sha256,
            "cassette_variant": draft.variant,
            "self_judgment": draft.self_judgment,
            "admission": admission_payload["verdict"],
            "failed_checks": [
                check["check_id"] for check in admission.checks if check["status"].value == "failed"
            ]
            + (["skill-md-schema"] if skill_md_error is not None else []),
            "verified_skill_sha256": admission.skill_sha256,
            "verifier_sha256": admission.verifier_sha256,
        }
    correct_self_accept = str(cases["correct"]["self_judgment"].get("verdict", "")).upper() == (
        "ACCEPT"
    )
    wrong_self_accept = str(cases["wrong-range"]["self_judgment"].get("verdict", "")).upper() == (
        "ACCEPT"
    )
    source_provenance = {"mode": "provided-cassettes"}
    if all(case["model"] == "reference-fixture" for case in cases.values()):
        source_provenance = {
            "mode": "bundled-reference-fixtures",
            "claim": "Deterministic positive and negative controls; no model transcript included.",
        }
    elif cases["wrong-range"]["cassette_variant"] == "legacy":
        source_provenance["wrong-range"] = (
            "The model cassette preserves its original `legacy` variant and logical source name; "
            "the public case name describes the injected fault."
        )
    summary = {
        "schema_version": "proprio.skill_admission.v0.4",
        "source_provenance": source_provenance,
        "cases": cases,
        "admit_proof": correct_self_accept and cases["correct"]["admission"] == "ADMIT",
        "reject_proof": wrong_self_accept and cases["wrong-range"]["admission"] == "REJECT",
    }
    summary["verdict"] = "PASS" if summary["admit_proof"] and summary["reject_proof"] else "FAIL"
    write_canonical_json(output_dir / "summary.json", summary)
    return summary
