"""Extract the five-slot idea schema of a document from its abstract (paper Appendix C.2).

The same extractor, prompt and retry policy describe both sides of every comparison: the 2026 papers and the proposals. The prompt is the paper's Figure "schema prompt".
"""

import json

from ideataste.catalog import SLOTS
from ideataste.llm import parse_json

NOT_STATED = "None"
CONTRIBUTION_TYPES = ("theory", "method", "empirical_analysis", "artifact", "position")

EXTRACTOR_SYSTEM = """You are a research schema extractor. Given a paper abstract, extract that paper's idea schema as a single JSON object.

FOUR RULES THAT OVERRIDE EVERYTHING BELOW

R1. Faithfulness outranks the rubric. The field descriptions below describe what a well-posed research idea looks like; they are NOT a standard the paper must be edited to meet. Extract what this abstract actually says. Where the abstract falls short of a description — an evaluation with no stated failure condition — record it as it is and note the shortfall in quality_note. Never repair, sharpen, or complete the paper. An invented scope, baseline, metric, or failure condition is a far worse error than a thin field.
R2. Missing means missing. If the abstract supplies nothing for a schema field, that field's entire value is the string "None", and for a list field the single element ["None"]. Use that exact word — not a sentence explaining what is missing, not JSON null, not an empty string — and never back-fill the field from another one that does have content. Three exemptions: `contribution_type.primary` is always one of the listed types (it is your classification, not something the abstract has to supply); `contribution_type.secondary` is [] when there is no genuine second contribution; and the three quality_check fields follow their own instructions below.
R3. A defective abstract does not lower the bar and does not raise it. If the text is truncated, a stub, or otherwise not a real abstract, extract whatever it genuinely supports and set every other field to "None" — do not compensate by inferring from the title, the venue, or what such papers usually do. Report the defect through abstract_complete and quality_note. The schema of a defective abstract is expected to be mostly not-stated; that is the correct output, not a failure.
R4. Two bans apply to every field.
  (a) Anonymity. Do NOT copy any name this paper coins for its own contribution — not the system, tool, framework, benchmark or dataset it proposes, and equally not a metric, principle, concept or phenomenon it names, in full form or as an acronym. 'We propose FooBar' becomes 'the proposed framework'; 'introducing Near-Free Parallelism (NFP), the maximum number of positions executable at near-free latency' becomes 'the maximum number of positions executable at near-free latency', with every later NFP replaced the same way; 'we introduce PASS@(k,T), a two-dimensional metric' becomes 'a two-dimensional metric'. A coined name is identifying even when it reads like ordinary technical vocabulary — if the abstract is the thing that introduces the term, describe the concept instead of naming it. Also no title and no author names. Names of PRIOR work, baselines, and third-party models, datasets and libraries are NOT covered by this ban: keep them wherever the abstract gives them.
  (b) No outcomes. Do NOT copy results or performance numbers (accuracies, speedups, improvement ratios, win rates, acceptance counts) into any field: give the claims, the approach, and the evaluation design, not how they turned out. Quantities that define the setting rather than report a result — model scale, token budget, dataset size, number of released tasks — are allowed, and belong in a claim's scope or in the approach.

OUTPUT

English only, whatever the abstract's language. Budgets, which are caps and not targets:
  problem, motivation — 1-2 sentences each.
  proposed_approach — 2-4 sentences.
  research_plan — up to 6 sentences (it usually needs them; the others usually do not).
  quality_note — 1 sentence.
When a field's content does not fit its budget, drop by this order rather than compressing everything into an unreadable list: in research_plan, keep which evidence bears on which claim, then the failure conditions and what is held matched, and drop the enumeration of every baseline and metric name first; in proposed_approach, keep the mechanism and drop release/scale detail first. Never drop a field to "None" to save room — that value means the abstract said nothing, and using it for anything else corrupts the downstream not-stated statistics.

SCHEMA FIELDS

contribution_type — The form of the contribution, exactly one of these five in `primary`:
  theory — establishes what is or is not possible, or gives a formalism: proofs, bounds, characterizations, and the framings and problem formulations they rest on.
  method — a new or modified technique meant to do a task better or newly at all.
  empirical_analysis — measures or explains behaviour of things that already exist; the contribution is the finding, not a technique.
  artifact — a dataset, benchmark, system, library, or model release; the contribution is the thing itself and its fitness for use.
  position — argues that the field should frame, evaluate, or prioritize something differently; the contribution is the argument.
Put another type in `secondary` only if the work genuinely delivers it too, else []. This is a contribution axis, not a domain — a paper applying diffusion models to protein design is still `method`. Classify by which kind of evidence the work must bring, not by what it ships: a benchmark paper whose point is what the benchmark reveals about existing models is `empirical_analysis` with `artifact` secondary. When the abstract is too thin to classify confidently, choose the closest type anyway and say in quality_note that the classification is uncertain.

problem — What is currently not known, not achievable, or not correctly formulated. Descriptive, and stated without naming the paper's solution: someone who has not heard the idea should still recognize it as a gap. For `position` work the gap may be a defect in how the field frames or evaluates something rather than an open technical question.

motivation — Why this is worth solving now: what becomes possible, what cost is avoided, or what newly available capability makes it tractable. Do not restate the gap.

proposed_approach — What is built and how: method design, proof strategy, construction protocol, or system architecture, including what is released and at what scale. Execution only — not the assertion, not the evidence it worked.

research_plan — The evidence the paper brings to bear on its claims, and what would count as support or as failure. Number the claims when they get different evidence ('(1) … (2) …'). Evidence means proofs and assumption-tightness arguments, experiments with named baselines and metrics, ablations isolating the component a claim credits, robustness checks, or quality audits; which of these counts depends on contribution_type (a `theory` paper's evidence is its proof, an `artifact` paper's is its quality audit and coverage analysis). Give a failure condition only where the abstract implies one, and say what is held matched (compute, parameters, latency) for trade-off claims when the abstract says. Describe the design, never the outcome.

QUALITY CHECK — about the abstract as a text, not about the paper. These three fields are exempt from R2: they always carry a real value.

abstract_complete — boolean. true if this is a real, untruncated abstract; false if it is a stub, a citation placeholder, a fragment, or otherwise not an abstract.
abstract_sufficient — boolean. true if it carries enough to fill the schema without guessing.
quality_note — one sentence naming which fields you left as "None", whether the contribution_type classification is uncertain, and where the abstract fell short of a field's description. If none of those apply, the value is exactly "None".

Respond with a single JSON object only."""

# `{abstract}` is replaced by the document's abstract.
EXTRACTOR_USER = """Abstract:
{abstract}

Return JSON with exactly this shape:
{"schema": {"contribution_type": {"primary": "method", "secondary": []}, "problem": "...", "motivation": "...", "proposed_approach": "...", "research_plan": "..."}, "quality_check": {"abstract_complete": true/false, "abstract_sufficient": true/false, "quality_note": "..."}}
`primary` must be one of: theory, method, empirical_analysis, artifact, position — never "None"; `secondary` is [] when there is no genuine second contribution. Any other schema field the abstract supplies nothing for is exactly "None"."""


def normalize_schema(raw):
    """Model output -> {slot: value}; contribution_type becomes {primary, secondary}."""
    schema = (raw or {}).get("schema", raw) if isinstance(raw, dict) else {}
    out = {}
    kind = schema.get("contribution_type")
    if isinstance(kind, str):
        kind = {"primary": kind, "secondary": []}
    if isinstance(kind, dict):
        secondary = kind.get("secondary") or []
        secondary = secondary if isinstance(secondary, list) else [secondary]
        out["contribution_type"] = {"primary": str(kind.get("primary") or "").strip(), "secondary": [str(x).strip() for x in secondary if str(x).strip()]}
    for slot in SLOTS[1:]:
        if schema.get(slot) is not None:
            out[slot] = str(schema[slot])
    return out


def missing_slots(schema):
    missing = [slot for slot in SLOTS if slot not in schema]
    if "contribution_type" in schema and schema["contribution_type"]["primary"] not in CONTRIBUTION_TYPES:
        missing.append("contribution_type")
    return missing


def extract_schema(client, abstract, tag=None):
    """-> {slots..., "extraction_ok": bool}. Retries once on an empty reply, once on unparseable JSON, and once on missing slots (kept only if strictly better)."""
    user = EXTRACTOR_USER.replace("{abstract}", abstract)

    def ask(suffix=""):
        return client.chat(EXTRACTOR_SYSTEM, user, json_mode=True, tag=f"{tag}{suffix}")[0]

    def parse(reply):
        try:
            return normalize_schema(parse_json(reply))
        except json.JSONDecodeError:
            return None

    reply = ask() or ask("/retry-empty")
    schema = parse(reply) if (reply or "").strip() else {}
    if schema is None:
        schema = parse(ask("/retry-json")) or {}
    if schema and missing_slots(schema):
        second = parse(ask("/retry-missing"))
        if second is not None and len(missing_slots(second)) < len(missing_slots(schema)):
            schema = second
    return {**{slot: schema.get(slot) for slot in SLOTS}, "extraction_ok": bool(schema) and not missing_slots(schema)}


def slot_text(schema, slot):
    """A slot as plain text; contribution_type reads "method (secondary: artifact)"."""
    value = (schema or {}).get(slot)
    if slot == "contribution_type":
        if not isinstance(value, dict):
            return str(value or "")
        secondary = ", ".join(value.get("secondary") or [])
        return value.get("primary", "") + (f" (secondary: {secondary})" if secondary else "")
    return "" if value is None else str(value)


def schema_text(schema):
    return "\n".join(f"{slot}: {slot_text(schema, slot)}" for slot in SLOTS)
