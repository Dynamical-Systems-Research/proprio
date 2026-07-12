"""Release-evidence manifest generation and verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from proprio.artifacts import file_sha256, write_canonical_json


def build_evidence_manifest(root: Path, output: Path) -> dict[str, Any]:
    excluded = output.resolve()
    artifacts = []
    evidence_roots = (
        root / "artifacts/evidence",
        root / "cassettes/cross-family",
        root / "cassettes/skill-admission",
    )
    for evidence_root in evidence_roots:
        for path in sorted(item for item in evidence_root.rglob("*") if item.is_file()):
            if path.resolve() == excluded:
                continue
            relative = path.relative_to(root)
            artifacts.append(
                {
                    "path": str(relative),
                    "sha256": file_sha256(path),
                    "bytes": path.stat().st_size,
                }
            )
    manifest = {
        "schema_version": "proprio.evidence_manifest.v0.4",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "verdict": "PASS" if artifacts else "FAIL",
    }
    write_canonical_json(output, manifest)
    return manifest


def verify_evidence_manifest(root: Path, manifest: dict[str, Any]) -> list[str]:
    errors = []
    for artifact in manifest["artifacts"]:
        path = root / artifact["path"]
        if not path.is_file():
            errors.append(f"missing: {artifact['path']}")
        elif file_sha256(path) != artifact["sha256"]:
            errors.append(f"hash mismatch: {artifact['path']}")
    return errors
