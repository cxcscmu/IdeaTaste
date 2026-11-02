"""Names shared by every part of IdeaTaste: areas, methods, schema slots, models."""

from functools import cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent / "configs"

AREAS = ("ml_systems", "code_generation", "world_models", "auto_research")
METHODS = ("free", "topic", "landscape", "frontier")

# The five slots of an idea schema, in the order the judge reads them.
SLOTS = ("contribution_type", "problem", "motivation", "proposed_approach", "research_plan")


@cache
def area_config(area):
    """{name, definition} of one research area."""
    if area not in AREAS:
        raise ValueError(f"unknown area {area!r}; expected one of {AREAS}")
    return yaml.safe_load((CONFIG_DIR / "areas" / f"{area}.yaml").read_text())


@cache
def model_configs():
    """Every model entry of configs/models.yaml, keyed by model name."""
    return yaml.safe_load((CONFIG_DIR / "models.yaml").read_text())["models"]


def model_config(name):
    configs = model_configs()
    if name not in configs:
        raise ValueError(f"unknown model {name!r}; add it to {CONFIG_DIR / 'models.yaml'}")
    return {"name": name, **configs[name]}


def models_with_role(role):
    """Model names with `role` (agent, judge or extractor), in configs/models.yaml order."""
    return tuple(name for name, cfg in model_configs().items() if cfg["role"] == role)
