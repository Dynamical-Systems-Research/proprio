from __future__ import annotations

from proprio.agent_smoke import DEFAULT_PARENT_EPISODES, load_smoke_parent
from proprio.generalization_instruments import GENERALIZATION_INSTRUMENTS
from proprio.instrument_types import CandidatePackage


def test_default_parent_episodes_cover_every_generalization_instrument() -> None:
    assert set(DEFAULT_PARENT_EPISODES) == set(GENERALIZATION_INSTRUMENTS)
    for path in DEFAULT_PARENT_EPISODES.values():
        assert path.is_file()


def test_smoke_parents_load_as_candidate_packages() -> None:
    for instrument_id in DEFAULT_PARENT_EPISODES:
        parent = load_smoke_parent(instrument_id)
        assert isinstance(parent, CandidatePackage)
        assert parent.instrument_id == instrument_id
        assert parent.skill_py
