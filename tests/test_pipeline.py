"""End to end with a mock model: every method generates, then the population is scored."""

import hashlib
import json
import re
import numpy as np
import pytest

from ideataste.catalog import METHODS
from ideataste.data import load_reference
from ideataste.evaluation.pipeline import evaluate_population
from ideataste.population import run_population
from ideataste.retrieval import HybridRetriever, display_id


class HashEncoder:
    """Deterministic stand-in for the sentence encoder (no model download)."""

    def encode(self, texts, batch_size=256):
        vectors = np.array([np.frombuffer(hashlib.sha256(t.encode()).digest(), dtype=np.uint8)[:16] for t in texts], dtype=np.float32) - 128
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


class MockModel:
    """Searches once, then submits a proposal citing the first two papers it saw; answers extraction and judge prompts with fixed JSON."""

    def chat(self, system, user, json_mode=False, tag=None):
        if "schema extractor" in system:
            return json.dumps({"schema": {"contribution_type": {"primary": "method", "secondary": []}, "problem": "p", "motivation": "m", "proposed_approach": "a", "research_plan": "None"}}), {}
        if "SCHEMA A" in user:
            same = int(hashlib.sha256(user.encode()).hexdigest(), 16) % 2 == 0
            return json.dumps({"fields": {"contribution_type": True, "problem": same, "motivation": False, "proposed_approach": same, "research_plan": True}, "same_idea": same, "reason": "mock"}), {}
        if "Steps remaining: 20." in user:
            return "<search> ai scientist hypothesis generation </search>", {}
        ids = list(dict.fromkeys(re.findall(r"\[CAND\] (D[0-9a-f]{12})", user)))[:2]
        references = "\n".join(f"[{n}] {i} | role: baseline | mock" for n, i in enumerate(ids, start=1))
        return (f"<proposal>\n# Mock proposal {tag}\n\n**Abstract**: An idea built on [1] and [2].\n\n## Related work\nSee [1], [2].\n\n## References\n{references}\n</proposal>"), {}


@pytest.fixture(scope="module")
def corpus():
    """A small stand-in corpus: 60 sample papers, all from 2025, on two topics."""
    return [{"id": p["id"], "title": p["title"], "abstract": p["abstract"], "publication_year": 2025, "topic_names": ["Topic Modeling", "Multi-Agent Systems"], "display_id": display_id(p["id"])} for p in load_reference("auto_research")[:60]]


@pytest.mark.parametrize("method", METHODS)
def test_method_generates_and_scores(method, corpus, tmp_path):
    retriever = HybridRetriever(corpus, encoder=HashEncoder())
    records = run_population(method, "auto_research", 4, tmp_path / "run", MockModel(), retriever=retriever, corpus=corpus, concurrency=2)
    assert len(records) == 4 and not any(r["failed"] for r in records)
    assert all(len(r["citations"]) == 2 for r in records)
    if method == "frontier":
        assert sorted({r["round"] for r in records}) == [1, 2]
    # Resuming the same run calls nothing and returns the same records.
    again = run_population(method, "auto_research", 4, tmp_path / "run", None, retriever=retriever, corpus=corpus)
    assert [r["agent_id"] for r in again] == [r["agent_id"] for r in records]

    proposals = [{"proposal_id": r["agent_id"], "title": r["proposal"]["title"], "abstract": r["proposal"]["abstract"], "citations": r["citations"]} for r in records]
    scores = evaluate_population("auto_research", proposals, tmp_path / "eval", MockModel(), MockModel(), concurrency=2, encoder=HashEncoder())
    for metric in ("match_cite", "match_idea", "diversity_cite", "diversity_idea"):
        assert 0.0 <= scores[metric] <= 1.0
    assert scores["n_with_schema"] == 4
