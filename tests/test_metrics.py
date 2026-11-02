"""The four metrics on small hand-checked examples (paper Eq. 1-3)."""

import math

import pytest

from ideataste.catalog import SLOTS
from ideataste.data import load_slot_weights
from ideataste.evaluation.citation import citation_threshold, diversity_cite, match_cite
from ideataste.evaluation.idea import diversity_idea, match_idea
from ideataste.evaluation.judge import slot_verdicts

PAPERS = [frozenset("ab"), frozenset("cd")]
PROPOSALS = [frozenset("ab"), frozenset("ax")]


def test_match_cite():
    # proposal->paper best Jaccard: 1, 1/3; paper->proposal: 1, 0
    p, r = (1 + 1 / 3) / 2, (1 + 0) / 2
    assert match_cite(PAPERS, PROPOSALS) == pytest.approx(2 * p * r / (p + r))


def test_diversity_cite():
    tau = citation_threshold(PAPERS)  # 2 citations per paper
    assert diversity_cite(PROPOSALS, tau) == pytest.approx(1.0 * 3 / 4)  # Q = 1, S = |{a,b,x}| / 4


def row(**hits):
    return {slot: hits.get(slot, False) for slot in SLOTS}


def test_idea_metrics():
    weights = dict.fromkeys(SLOTS, 1.0)
    match = [{"paper_id": "h1", **row(problem=True)}, {"paper_id": "h1", **row(motivation=True)}]
    assert match_idea(match, weights, ["h1", "h2"]) == pytest.approx((2 / 5 + 0) / 2)
    pairs = [{"a": "p1", "b": "p2", **row(problem=True)}]
    assert diversity_idea(pairs, weights, ["p1", "p2", "p3"]) == pytest.approx(1 - (1 / 5 + 1 / 5 + 0) / 3)


def test_two_empty_slots_are_not_a_match():
    schema = {slot: "None" for slot in SLOTS}
    verdict = {slot: True for slot in SLOTS}
    assert not any(slot_verdicts(verdict, schema, schema).values())


def test_released_weights():
    weights = load_slot_weights("auto_research")
    assert set(weights) == set(SLOTS)
    assert all(w > 0 and math.isfinite(w) for w in weights.values())
