---
license: mit
pretty_name: IdeaTaste
configs:
- config_name: corpus
  data_files:
  - split: ml_systems
    path: areas/ml_systems/corpus.parquet
  - split: code_generation
    path: areas/code_generation/corpus.parquet
  - split: world_models
    path: areas/world_models/corpus.parquet
  - split: auto_research
    path: areas/auto_research/corpus.parquet
- config_name: reference
  data_files:
  - split: ml_systems
    path: areas/ml_systems/reference.parquet
  - split: code_generation
    path: areas/code_generation/reference.parquet
  - split: world_models
    path: areas/world_models/reference.parquet
  - split: auto_research
    path: areas/auto_research/reference.parquet
---

# IdeaTaste

[Paper](https://arxiv.org/abs/2611.03424) · [Homepage](https://cxcscmu.github.io/IdeaTaste) · [Code](https://github.com/cxcscmu/IdeaTaste)


**Do LLMs share the research taste of human researchers?** LLM agents read a literature corpus frozen at 2025 and write research proposals; those proposals are then scored against the papers the same communities published in 2026. Proposals and papers are compared both on the literature they cite and on the ideas they state, giving four metrics: citation matching, idea matching, citation diversity and idea diversity.

Four research areas, each with a literature corpus and a human reference: 263K papers published through 2025 and 11.6K published in January–August 2026, about 530 MB.

## Quick start

With the code, which downloads the files into `data/areas/` (skipping areas already there) and prints a preview of each:

```bash
git clone https://github.com/cxcscmu/IdeaTaste && cd IdeaTaste
pip install -e .
python data/download_and_preview.py
```

The data alone:

```bash
huggingface-cli download cx-cmu/IdeaTaste --repo-type dataset --local-dir data
```

```python
from datasets import load_dataset
reference = load_dataset("cx-cmu/IdeaTaste", "reference", split="auto_research")
```

## Areas

Each area is a literature corpus U of papers published through 2025, which LLM agents search and cite, and a human reference H of papers published January–August 2026, which their proposals are compared with.

| Area | Corpus U | Reference H |
|---|---:|---:|
| `ml_systems` (machine learning systems) | 88,184 | 5,188 |
| `code_generation` | 94,674 | 3,375 |
| `world_models` | 50,271 | 1,867 |
| `auto_research` | 30,264 | 1,136 |

## Files in `areas/<area>/`

Paper ids are OpenAlex work URLs (`https://openalex.org/W…`) or Semantic Scholar ids (`S2:…`).

| File | Contents |
|---|---|
| `corpus.parquet` | **Corpus U**. Columns: `id`, `title`, `abstract`, `publication_year`, `source_name`, `author_names`, `institution_names` (shown to LLM agents), and `topic_names` (used to allocate TOPIC and FRONTIER topics). The row order fixes search tie-breaking. |
| `corpus_embeddings.npy` | all-MiniLM-L6-v2 vectors of `title. abstract[:1200]`, one float32 row per corpus row. |
| `reference.parquet` | **Reference H**. Columns: `id`, `title`, `abstract`, `citations` (cited ids in U), and the five idea-schema slots `contribution_type` (`{primary, secondary}`), `problem`, `motivation`, `proposed_approach`, `research_plan`. A slot the abstract does not state reads `"None"`. |
| `slot_weights.json` | `w_i = -log2 p_i` per slot, where `p_i` is the share of 2026 papers whose slot i is matched by one of the 5 other 2026 papers retrieved for it. |
| `landscape.json` | LANDSCAPE only. `task_tags` and `method_tags` (2025 tag names), and `papers`: the tags of each 2025 paper (`id`, `date`, `tasks`, `methods`). |

## Sources and licence

Released under the MIT license. Metadata comes from OpenAlex (CC0) and Semantic Scholar. Abstracts remain under their publishers' copyright and are provided for research use.

## Citation

```bibtex
@article{zhong2026ideataste,
  title   = {IdeaTaste: Do LLMs Share the Research Taste of Human Researchers?},
  author  = {Zhong, Shanshan and Xu, Chen and Ning, Jingjie and Liu, Zhengzhong and Kumar, Aviral and Xiong, Chenyan},
  journal = {arXiv preprint arXiv:2611.03424},
  year    = {2026}
}
```
