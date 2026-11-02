"""Slot-level idea judge (paper Appendix C.3, Figure "judge prompt").

Each pair is judged once. Which document is shown as A is drawn from a hash of the pair id and a fixed seed: random across pairs, reproducible on a rerun.
"""

import hashlib
import random

from ideataste.catalog import SLOTS
from ideataste.evaluation.schema import NOT_STATED, schema_text, slot_text
from ideataste.llm import parse_json

JUDGE_SYSTEM = """You judge whether two research idea schemas describe the SAME core idea. Each schema has these 5 fields: contribution_type, problem, motivation, proposed_approach, research_plan. Judge in two stages and report both.
STAGE 1 (per field): for each field in turn, decide whether A and B are substantially the same ON THAT FIELD ALONE, as if the other fields were hidden from you.
If a field has no corresponding content in A or B (including when both are missing or use the placeholder 'None'), its per-field verdict must be false.
STAGE 2 (whole idea): same_idea is true only if the two schemas address substantially the same problem AND propose substantially the same approach. This is your own judgement on the full schema, NOT a vote or an average over stage 1 — agreeing on problem, motivation, contribution_type alone is not enough.
In both stages: different wording, naming, or level of detail does not matter; merely sharing a topic, task, dataset, or a general technique family does NOT count as the same.
Reply JSON only: {"fields": {"contribution_type": true/false, "problem": true/false, "motivation": true/false, "proposed_approach": true/false, "research_plan": true/false}, "same_idea": true/false, "reason": "<one sentence>"}."""

SEED = 0
_TRUE, _FALSE = {"true", "yes", "same", "1"}, {"false", "no", "different", "0"}


def pair_id(a_id, b_id):
    return f"{a_id}=>{b_id}"


def shows_a_first(pair, seed=SEED):
    """True if the first document of `pair` is shown as schema A."""
    digest = hashlib.sha256(f"{seed}:{pair}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big")).choice(("fwd", "rev")) == "fwd"


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return _as_bool(value.get("same", value.get("same_idea")))
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        return True if text in _TRUE else False if text in _FALSE else None
    return None


def judge_pair(client, pair, schema_a, schema_b):
    """-> {"same_idea": bool, slot: bool|None ...}; raises ValueError on an unusable reply."""
    first, second = (schema_a, schema_b) if shows_a_first(pair) else (schema_b, schema_a)
    reply, _meta = client.chat(JUDGE_SYSTEM, f"SCHEMA A:\n{schema_text(first)}\n\nSCHEMA B:\n{schema_text(second)}", json_mode=True, tag=f"judge/{pair}")
    verdict = parse_json(reply)
    same = _as_bool(verdict.get("same_idea")) if isinstance(verdict, dict) else None
    if same is None:
        raise ValueError(f"judge reply without a boolean same_idea: {reply[:200]!r}")
    fields = verdict.get("fields") if isinstance(verdict.get("fields"), dict) else {}
    return {"same_idea": same, **{slot: _as_bool(fields.get(slot)) for slot in SLOTS}}


def slot_verdicts(verdict, schema_a, schema_b):
    """Slot matches as scored: the judge must say yes, and the two sides must not both be the "None" placeholder (two empty slots are not the same idea)."""
    return {slot: bool(verdict.get(slot)) and not (slot_text(schema_a, slot).strip() == NOT_STATED == slot_text(schema_b, slot).strip()) for slot in SLOTS}
