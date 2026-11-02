"""Load the benchmark inputs.

Layout under the data directory ($IDEATASTE_DATA, default ./data), one folder per area:

    areas/<area>/corpus.parquet          papers published through 2025 (U): what LLM agents search and cite
    areas/<area>/corpus_embeddings.npy   their all-MiniLM-L6-v2 vectors, in corpus order
    areas/<area>/reference.parquet       papers published in 2026 (H): citations and idea schemas
    areas/<area>/slot_weights.json       weight of each idea-schema slot
    areas/<area>/landscape.json          2025 task/method tags (LANDSCAPE method only)
"""

import json
import os
from functools import cache
from pathlib import Path

import pyarrow.parquet as pq

from ideataste.catalog import AREAS


def data_dir():
    return Path(os.environ.get("IDEATASTE_DATA", "data")).resolve()


def area_path(area, name):
    if area not in AREAS:
        raise ValueError(f"unknown area {area!r}; expected one of {AREAS}")
    path = data_dir() / "areas" / area / name
    if not path.exists() and name != "corpus_embeddings.npy":
        raise FileNotFoundError(f"{path} not found; download the data (README) or set IDEATASTE_DATA")
    return path


@cache
def load_corpus(area):
    """Corpus U in its released order; this order fixes retrieval tie-breaking."""
    return pq.read_table(area_path(area, "corpus.parquet")).to_pylist()


@cache
def load_reference(area):
    """Human reference H: 2026 papers with `citations` (ids in U) and the five schema slots."""
    return pq.read_table(area_path(area, "reference.parquet")).to_pylist()


@cache
def load_slot_weights(area):
    return json.loads(area_path(area, "slot_weights.json").read_text())["weights"]


@cache
def load_landscape(area):
    return json.loads(area_path(area, "landscape.json").read_text())
