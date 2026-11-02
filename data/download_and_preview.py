"""Download the IdeaTaste benchmark inputs from Hugging Face into data/areas/, then preview them.

    python data/download_and_preview.py                      # every area
    python data/download_and_preview.py --area world_models --n 3

An area whose five files are already in data/areas/<area>/ is not downloaded again, only previewed.
"""

import argparse
import json
import textwrap
from collections import Counter
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from huggingface_hub import snapshot_download

REPO_ID = "cx-cmu/IdeaTaste"
DATA_DIR = Path(__file__).resolve().parent
AREAS = ("ml_systems", "code_generation", "world_models", "auto_research")
FILES = ("corpus.parquet", "corpus_embeddings.npy", "reference.parquet", "slot_weights.json", "landscape.json")
SLOTS = ("contribution_type", "problem", "motivation", "proposed_approach", "research_plan")


def download(areas):
    """Fetch the files of every area that is not complete locally; returns the areas downloaded."""
    missing = [area for area in areas if not all((DATA_DIR / "areas" / area / name).exists() for name in FILES)]
    if missing:
        print(f"downloading {', '.join(missing)} from https://huggingface.co/datasets/{REPO_ID} ...")
        snapshot_download(REPO_ID, repo_type="dataset", local_dir=DATA_DIR, allow_patterns=[f"areas/{area}/*" for area in missing])
    return missing


def short(value, width=100):
    return textwrap.shorten(str(value), width, placeholder=" …")


def section(title):
    print(f"\n  {title}")


def preview_corpus(folder, n):
    table = pq.read_table(folder / "corpus.parquet")
    years = Counter(table.column("publication_year").to_pylist())
    section(f"corpus.parquet: {table.num_rows:,} papers published {min(years)}–{max(years)}, columns {table.column_names}")
    for paper in table.slice(table.num_rows - n).to_pylist():
        print(f"    [{paper['publication_year']}] {short(paper['title'], 90)}")
        print(f"        {short(paper['abstract'] or '(no abstract)')}")
        print(f"        topics: {', '.join(paper['topic_names'] or [])}")
    embeddings = np.load(folder / "corpus_embeddings.npy", mmap_mode="r")
    section(f"corpus_embeddings.npy: {embeddings.shape[0]:,} x {embeddings.shape[1]} float32 vectors, one per corpus row")


def preview_reference(folder, n):
    papers = pq.read_table(folder / "reference.parquet").to_pylist()
    citations = [len(paper["citations"]) for paper in papers]
    section(f"reference.parquet: {len(papers):,} papers from 2026, {np.mean(citations):.1f} corpus citations each on average")
    for paper in papers[:n]:
        print(f"    {short(paper['title'], 90)}  ({len(paper['citations'])} citations)")
        for slot in SLOTS:
            value = paper[slot]["primary"] if slot == "contribution_type" else paper[slot]
            print(f"        {slot:18s} {short(value, 90)}")


def preview_weights(folder):
    weights = json.loads((folder / "slot_weights.json").read_text())["weights"]
    section("slot_weights.json: " + ", ".join(f"{slot} {weight:.2f}" for slot, weight in weights.items()))


def preview_landscape(folder, n):
    landscape = json.loads((folder / "landscape.json").read_text())
    papers = landscape["papers"]
    section(f"landscape.json: {len(landscape['task_tags'])} task tags and {len(landscape['method_tags'])} method tags over {len(papers):,} papers from 2025")
    for axis in ("tasks", "methods"):
        top = Counter(tag for paper in papers for tag in paper[axis]).most_common(n)
        print(f"    most common {axis}: " + "; ".join(f"{tag} ({count / len(papers):.1%})" for tag, count in top))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--area", choices=AREAS, action="append", help="area to download and preview (default: all)")
    parser.add_argument("--n", type=int, default=2, help="example rows per file")
    args = parser.parse_args()
    areas = args.area or AREAS
    download(areas)
    for area in areas:
        folder = DATA_DIR / "areas" / area
        print(f"\n=== {area} ===")
        preview_corpus(folder, args.n)
        preview_reference(folder, args.n)
        preview_weights(folder)
        preview_landscape(folder, args.n)


if __name__ == "__main__":
    main()
