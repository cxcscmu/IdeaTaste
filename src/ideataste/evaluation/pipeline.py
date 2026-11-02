"""Score a new population end to end: extract schemas, retrieve candidates, judge, score.

    proposals (title, abstract, citations)
      -> idea schema per proposal                (extractor model)
      -> 5 nearest proposals per 2026 paper       (match pairs)
         5 nearest other proposals per proposal   (diversity pairs)
      -> slot verdicts per pair                   (judge model)
      -> match_cite, match_idea, diversity_cite, diversity_idea

Every model call is checkpointed in `out_dir`, so an interrupted run resumes.
"""

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ideataste.catalog import SLOTS
from ideataste.data import load_reference, load_slot_weights
from ideataste.evaluation.citation import citation_threshold, diversity_cite, match_cite
from ideataste.evaluation.idea import diversity_idea, match_idea
from ideataste.evaluation.judge import judge_pair, pair_id, slot_verdicts
from ideataste.evaluation.schema import extract_schema
from ideataste.jsonl import cached_map
from ideataste.retrieval import HybridRetriever

TOP_K = 5


def _query_text(document):
    return f"{document.get('title') or ''}. {document.get('abstract') or ''}"


def nearest(retriever, document, k=TOP_K, exclude=None):
    """Ids of the k documents nearest to `document` by title and abstract."""
    hits = [paper["id"] for paper, _ in retriever.search(_query_text(document), k + (exclude is not None))]
    return [i for i in hits if i != exclude][:k]


def candidate_pairs(reference, proposals, encoder=None):
    """Match pairs (paper, proposal, rank) and unordered diversity pairs (a, b)."""
    index = HybridRetriever([{"id": p["proposal_id"], "title": p["title"], "abstract": p["abstract"]} for p in proposals], encoder=encoder)
    match = [(paper["id"], proposal_id, rank) for paper in reference for rank, proposal_id in enumerate(nearest(index, paper), start=1)]
    diversity = sorted({tuple(sorted((p["proposal_id"], other))) for p in proposals for other in nearest(index, p, exclude=p["proposal_id"])})
    return match, diversity


def evaluate_population(area, proposals, out_dir, extractor, judge, concurrency=8, encoder=None):
    """proposals: [{proposal_id, title, abstract, citations: [{id, ...}]}] -> the four metrics. Writes schemas.jsonl, verdicts.jsonl, {match,diversity}.parquet and scores.json."""
    out_dir = Path(out_dir)
    reference = load_reference(area)
    weights = load_slot_weights(area)

    schemas = cached_map(proposals, key=lambda p: p["proposal_id"], function=lambda p: extract_schema(extractor, p["abstract"], tag=p["proposal_id"]), path=out_dir / "schemas.jsonl", concurrency=concurrency)
    scored = [p for p in proposals if schemas.get(p["proposal_id"], {}).get("extraction_ok")]
    schema_of = {**{paper["id"]: {slot: paper[slot] for slot in SLOTS} for paper in reference}, **{p["proposal_id"]: schemas[p["proposal_id"]] for p in scored}}

    match, diversity = candidate_pairs(reference, scored, encoder)
    jobs = [pair_id(proposal_id, paper_id) for paper_id, proposal_id, _ in match] + [pair_id(a, b) for a, b in diversity]
    verdicts = cached_map(sorted(set(jobs)), key=lambda pair: pair, function=lambda pair: judge_pair(judge, pair, *(schema_of[i] for i in pair.split("=>"))), path=out_dir / "verdicts.jsonl", concurrency=concurrency)

    def slots(a, b):
        verdict = verdicts.get(pair_id(a, b))
        return slot_verdicts(verdict, schema_of[a], schema_of[b]) if verdict else dict.fromkeys(SLOTS, False)

    match_rows = [{"paper_id": paper_id, "proposal_id": proposal_id, "rank": rank, **slots(proposal_id, paper_id)} for paper_id, proposal_id, rank in match]
    diversity_rows = [{"a": a, "b": b, **slots(a, b)} for a, b in diversity]
    pq.write_table(pa.Table.from_pylist(match_rows), out_dir / "match.parquet")
    pq.write_table(pa.Table.from_pylist(diversity_rows), out_dir / "diversity.parquet")

    reference_sets = [frozenset(paper["citations"]) for paper in reference]
    proposal_sets = [frozenset(c["id"] for c in p["citations"]) for p in proposals]
    scores = {
        "match_cite": match_cite(reference_sets, proposal_sets),
        "match_idea": match_idea(match_rows, weights, [paper["id"] for paper in reference]),
        "diversity_cite": diversity_cite(proposal_sets, citation_threshold(reference_sets)),
        "diversity_idea": diversity_idea(diversity_rows, weights, [p["proposal_id"] for p in proposals]),
        "n_proposals": len(proposals),
        "n_with_schema": len(scored),
        "n_pairs_judged": len(verdicts),
        "n_pairs": len(set(jobs)),
    }
    (out_dir / "scores.json").write_text(json.dumps(scores, indent=2) + "\n")
    return scores
