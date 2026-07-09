"""Content-addressed artifact writing."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from proprio.schema import ArtifactRef, canonical_json


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_sha256(path: Path) -> str:
    return file_sha256(path)


def jsonable(value: Any) -> Any:
    """Convert event-model payloads to lossless JSON-compatible values."""

    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): jsonable(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [jsonable(child) for child in value]
    return value


def write_bytes(path: Path, payload: bytes, media_type: str) -> ArtifactRef:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return ArtifactRef(
        path=str(path),
        sha256=hashlib.sha256(payload).hexdigest(),
        media_type=media_type,
        bytes=len(payload),
    )


def write_canonical_json(path: Path, value: Any) -> ArtifactRef:
    return write_bytes(path, canonical_json(value) + b"\n", "application/json")


def write_jsonl(path: Path, rows: Iterable[Any]) -> ArtifactRef:
    payload = b"".join(
        json.dumps(
            jsonable(row),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
        for row in rows
    )
    return write_bytes(path, payload, "application/x-ndjson")


def write_npy(path: Path, array: np.ndarray) -> ArtifactRef:
    buffer = io.BytesIO()
    np.save(buffer, np.asarray(array), allow_pickle=False)
    return write_bytes(path, buffer.getvalue(), "application/x-npy")
