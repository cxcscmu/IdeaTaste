"""Hybrid sparse + dense retrieval over titles and abstracts (paper Appendix C.3).

BM25 (k1=1.5, b=0.75) and all-MiniLM-L6-v2 cosine similarity each rank the documents; the top 200 of each are fused with reciprocal rank fusion, 1/(60 + rank). The same index serves the LLM agent's <search> and the candidate retrieval of the idea metrics.
"""

import hashlib
import math
import re
import threading
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

DENSE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RRF_K = 60
FUSE_DEPTH = 200
DENSE_ABSTRACT_CHARS = 1200

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset("a an and are as at be by for from has have in is it its of on or that the this to was we with which their our these those can using based new approach paper method results propose proposed show study".split())


def display_id(paper_id):
    """The anonymous id an LLM agent sees for a corpus paper."""
    return "D" + hashlib.sha1(paper_id.encode()).hexdigest()[:12]


def tokenize(text):
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS and len(t) > 1]


class BM25:
    def __init__(self, texts, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        tokens = [tokenize(text) for text in texts]
        self.lengths = [len(t) for t in tokens]
        self.mean_length = sum(self.lengths) / len(self.lengths) if tokens else 0.0
        self.term_counts = [Counter(t) for t in tokens]
        document_frequency = defaultdict(int)
        for doc_tokens in tokens:
            for term in set(doc_tokens):
                document_frequency[term] += 1
        n = len(tokens)
        self.idf = {term: math.log((n - df + 0.5) / (df + 0.5) + 1.0) for term, df in document_frequency.items()}

    def rank(self, query):
        """[(document index, score)] by descending score, ties by index."""
        scores = defaultdict(float)
        for term in tokenize(query):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, counts in enumerate(self.term_counts):
                tf = counts.get(term)
                if tf:
                    norm = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.mean_length)
                    scores[i] += idf * tf * (self.k1 + 1) / norm
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


class Encoder:
    """Thread-safe sentence encoder, loaded once."""

    _lock = threading.Lock()
    _models = {}

    def __init__(self, name=DENSE_MODEL):
        self.name = name

    def encode(self, texts, batch_size=256):
        with self._lock:
            if self.name not in self._models:
                import torch
                from sentence_transformers import SentenceTransformer

                device = "cuda" if torch.cuda.is_available() else "cpu"
                self._models[self.name] = SentenceTransformer(self.name, device=device)
            return self._models[self.name].encode(texts, batch_size=batch_size, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)


def _dense_text(paper):
    return f"{paper.get('title') or ''}. {(paper.get('abstract') or '')[:DENSE_ABSTRACT_CHARS]}"


class HybridRetriever:
    """search(query, top_k, year_range) -> [(paper, fused score)].

    The year filter is applied after fusion, as in the paper's runs, so a filtered search can return fewer than top_k papers. `cache_path` (.npy) stores the corpus embeddings across runs.
    """

    def __init__(self, papers, encoder=None, cache_path=None):
        self.papers = list(papers)
        self.by_id = {paper["id"]: paper for paper in self.papers}
        self.encoder = encoder or Encoder()
        self.bm25 = BM25([f"{p.get('title') or ''} {p.get('abstract') or ''}" for p in self.papers])
        self.embeddings = self._embed_corpus(cache_path)

    def _embed_corpus(self, cache_path):
        if cache_path and Path(cache_path).exists():
            cached = np.load(cache_path)
            if len(cached) == len(self.papers):
                return cached
        embeddings = self.encoder.encode([_dense_text(p) for p in self.papers])
        if cache_path:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            np.save(cache_path, embeddings)
        return embeddings

    def _dense_rank(self, query):
        similarity = self.embeddings @ self.encoder.encode([query])[0]
        order = np.argsort(-similarity)[:FUSE_DEPTH]
        return [(int(i), float(similarity[i])) for i in order]

    def rank(self, query):
        """[(document index, fused score)] by descending score, ties by index."""
        fused = {}
        for channel in (self.bm25.rank(query)[:FUSE_DEPTH], self._dense_rank(query)):
            for rank, (i, _score) in enumerate(channel):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
        return sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))

    def search(self, query, top_k, year_range=None):
        results = []
        for i, score in self.rank(query):
            year = self.papers[i].get("publication_year")
            if year_range and (year is None or not year_range[0] <= year <= year_range[1]):
                continue
            results.append((self.papers[i], score))
            if len(results) >= top_k:
                break
        return results

    def papers_by_id(self, ids):
        """Corpus papers for `ids`, in the given order, skipping unknown ids."""
        return [self.by_id[i] for i in ids if i in self.by_id]
