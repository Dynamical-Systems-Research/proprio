"""Source loading for diagnostic instrument skill episodes."""

from __future__ import annotations

import hashlib
from pathlib import Path

from proprio.reference_instruments import INSTRUMENTS

ROOT = Path(__file__).resolve().parents[2]


def _source_root() -> Path:
    checkout = ROOT / "sources" / "instruments"
    return checkout if checkout.is_dir() else Path(__file__).with_name("sources") / "instruments"


def source_path(instrument_id: str) -> Path:
    if instrument_id not in INSTRUMENTS:
        raise KeyError(instrument_id)
    return _source_root() / instrument_id / "source.md"


def load_instrument_source(instrument_id: str) -> tuple[str, str]:
    text = source_path(instrument_id).read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()
