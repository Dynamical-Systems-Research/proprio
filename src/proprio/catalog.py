"""Validation for release skill packages and their evidence links."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillFrontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str


class SkillVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact: str
    artifact_verdict: Literal["PASS"]
    skill_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verifier_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class SkillCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    instrument: str
    path: str
    code_path: str | None = None
    status: Literal["reference", "simulation_qualified", "simulation_staged"]
    hardware_qualification_required: Literal[True]
    verification: SkillVerification


class SkillCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["proprio.skill_catalog.v0.2"]
    skills: tuple[SkillCatalogEntry, ...]

    @model_validator(mode="after")
    def unique_ids(self) -> SkillCatalog:
        ids = [entry.id for entry in self.skills]
        if len(ids) != len(set(ids)):
            raise ValueError("skill IDs must be unique")
        return self


def parse_skill_markdown(text: str) -> SkillFrontmatter:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError("SKILL.md requires closed YAML frontmatter")
    payload, body = text[4:].split("\n---\n", 1)
    if not body.strip():
        raise ValueError("SKILL.md requires an instruction body")
    metadata = yaml.safe_load(payload)
    if not isinstance(metadata, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    unsupported = set(metadata) - {"name", "description"}
    if unsupported:
        raise ValueError(f"unsupported SKILL.md frontmatter fields: {sorted(unsupported)}")
    return SkillFrontmatter.model_validate(metadata)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_catalog(root: Path) -> SkillCatalog:
    catalog = SkillCatalog.model_validate_json((root / "catalog.json").read_text(encoding="utf-8"))
    package_names = {path.name for path in (root / "skills").iterdir() if path.is_dir()}
    catalog_names = {Path(entry.path).parent.name for entry in catalog.skills}
    if package_names != catalog_names:
        raise ValueError(
            f"catalog/package mismatch: missing={sorted(package_names - catalog_names)}, "
            f"stale={sorted(catalog_names - package_names)}"
        )
    for entry in catalog.skills:
        skill_path = root / entry.path
        metadata = parse_skill_markdown(skill_path.read_text(encoding="utf-8"))
        package = skill_path.parent
        if metadata.name != package.name or metadata.name != entry.id:
            raise ValueError(f"skill name, directory, and catalog ID differ: {entry.id}")
        if _sha256(skill_path) != entry.verification.skill_sha256:
            raise ValueError(f"skill hash mismatch: {entry.id}")
        if entry.code_path is not None:
            code_path = root / entry.code_path
            if not code_path.is_file():
                raise ValueError(f"missing skill code: {entry.code_path}")
            if code_path.parent.parent != package or code_path.parent.name != "scripts":
                raise ValueError(f"skill code is outside its scripts directory: {entry.id}")
            if _sha256(code_path) != entry.verification.code_sha256:
                raise ValueError(f"skill code hash mismatch: {entry.id}")
        agent_path = package / "agents/openai.yaml"
        if not agent_path.is_file():
            raise ValueError(f"missing agents/openai.yaml: {entry.id}")
        agent = yaml.safe_load(agent_path.read_text(encoding="utf-8"))
        interface = agent.get("interface", {}) if isinstance(agent, dict) else {}
        required = {"display_name", "short_description", "default_prompt"}
        if set(interface) != required:
            raise ValueError(f"invalid agents/openai.yaml interface: {entry.id}")
        if f"${entry.id}" not in interface["default_prompt"]:
            raise ValueError(f"default prompt does not invoke ${entry.id}")
        if not 25 <= len(interface["short_description"]) <= 64:
            raise ValueError(f"short description length is invalid: {entry.id}")
        artifact = root / entry.verification.artifact
        if artifact.parent != package / "references":
            raise ValueError(f"verification artifact is outside package references: {entry.id}")
        data = json.loads(artifact.read_text(encoding="utf-8"))
        if data.get("verdict") != entry.verification.artifact_verdict:
            raise ValueError(f"verification artifact did not pass: {entry.id}")
        if data.get("skill_sha256") != entry.verification.skill_sha256:
            raise ValueError(f"verification record has stale skill hash: {entry.id}")
        if data.get("code_sha256") != entry.verification.code_sha256:
            raise ValueError(f"verification record has stale code hash: {entry.id}")
        if data.get("source_sha256") != entry.verification.source_sha256:
            raise ValueError(f"verification record has stale source hash: {entry.id}")
        if data.get("verifier_sha256") != entry.verification.verifier_sha256:
            raise ValueError(f"verification record has stale verifier hash: {entry.id}")
    return catalog
