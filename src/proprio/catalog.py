"""Validation for release skill packages and their evidence links."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillFrontmatter(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str
    id: str | None = None
    version: str | None = None


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
    status: Literal["reference", "simulation_qualified"]
    hardware_qualification_required: Literal[True]
    verification: SkillVerification


class SkillCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["proprio.skill_catalog.v0.1"]
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
    unsupported = set(metadata) - {"name", "description", "id", "version"}
    if unsupported:
        raise ValueError(f"unsupported SKILL.md frontmatter fields: {sorted(unsupported)}")
    return SkillFrontmatter.model_validate(metadata)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_catalog(root: Path) -> SkillCatalog:
    catalog = SkillCatalog.model_validate_json((root / "catalog.json").read_text(encoding="utf-8"))
    for entry in catalog.skills:
        skill_path = root / entry.path
        parse_skill_markdown(skill_path.read_text(encoding="utf-8"))
        if _sha256(skill_path) != entry.verification.skill_sha256:
            raise ValueError(f"skill hash mismatch: {entry.id}")
        if entry.code_path is not None:
            code_path = root / entry.code_path
            if not code_path.is_file():
                raise ValueError(f"missing skill code: {entry.code_path}")
            if _sha256(code_path) != entry.verification.code_sha256:
                raise ValueError(f"skill code hash mismatch: {entry.id}")
        artifact = root / entry.verification.artifact
        data = json.loads(artifact.read_text(encoding="utf-8"))
        if data.get("verdict") != entry.verification.artifact_verdict:
            raise ValueError(f"verification artifact did not pass: {entry.id}")
    return catalog
