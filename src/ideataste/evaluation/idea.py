"""Level 2, idea formulation: idea matching and idea diversity (paper Sec. 3.2.2).

Both work on judge verdicts: rows that hold one boolean per schema slot for a pair of documents. A slot counts as matched only if the judge said so and the two sides do not both read "None" (see `judge.slot_verdicts`).
"""

from collections import defaultdict

from ideataste.catalog import SLOTS


def _matched_slots(rows, query_key):
    """{query document: set of slots matched by at least one of its retrieved candidates}."""
    matched = defaultdict(set)
    for row in rows:
        for slot in SLOTS:
            if row[slot]:
                matched[row[query_key]].add(slot)
    return matched


def slot_score(slots, weights):
    """s(d, Y): the weighted fraction of the slots of d matched within Y."""
    return sum(weights[slot] for slot in slots) / sum(weights[slot] for slot in SLOTS)


def match_idea(match_rows, weights, reference_ids):
    """M_idea: mean over 2026 papers of the weighted fraction of their slots covered by the five proposals retrieved for them (Eq. 3). Papers without verdicts score 0."""
    matched = _matched_slots(match_rows, "paper_id")
    return sum(slot_score(matched[paper_id], weights) for paper_id in reference_ids) / len(reference_ids)


def diversity_idea(pair_rows, weights, proposal_ids):
    """D_idea: one minus the mean weighted fraction of a proposal's slots shared by some peer. Peers are the proposals it retrieves plus those that retrieve it, so every unordered neighbour pair counts for both sides (Eq. 3)."""
    shared = defaultdict(set)
    for row in pair_rows:
        for slot in SLOTS:
            if row[slot]:
                shared[row["a"]].add(slot)
                shared[row["b"]].add(slot)
    overlap = sum(slot_score(shared[proposal_id], weights) for proposal_id in proposal_ids)
    return 1 - overlap / len(proposal_ids)
