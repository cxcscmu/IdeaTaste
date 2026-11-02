"""Parse model replies: which action a reply takes, and what a proposal says and cites."""

import re

PAPER_ID_RE = re.compile(r"\bD[0-9a-f]{12}\b")  # anonymised corpus ids, see display_id
YEAR_FILTER_RE = re.compile(r"\|\s*years?\s*[:=]?\s*(\d{4})(?:\s*[-–—~]\s*(\d{4}))?\s*$", re.IGNORECASE)
_REFERENCES_HEADING_RE = re.compile(r"^\s*#{0,4}\s*\**\s*References\s*\**\s*:?\s*$", re.IGNORECASE)
_REFERENCE_NUMBER_RE = re.compile(r"^\s*\[?(\d+)[\].):]")
_ROLE_RE = re.compile(r"role\s*:\s*([a-zA-Z_]+)", re.IGNORECASE)
_INLINE_NUMBERS_RE = re.compile(r"\[(\d[\d,;\s\-–—]*)\]")
_RANGE_RE = re.compile(r"^(\d+)\s*[-–—]\s*(\d+)$")
# "**Abstract**: ..." or an "## Abstract" heading followed by a paragraph.
_ABSTRACT_RE = re.compile(r"(?:\*\*Abstract\*\*\s*:?|^\s{0,3}#{1,6}\s*\**\s*Abstract\s*:?\s*\**\s*$)\s*(.+?)(?:\n\s*\n|\n\s{0,3}#{1,6}\s|\Z)", re.DOTALL | re.IGNORECASE | re.MULTILINE)


# ------------------------------------------------------------------ proposals
def parse_proposal(markdown):
    """Proposal markdown -> (title, abstract, body, references).

    references: [{"n", "id", "role", "rationale"}], one per line of the References section that carries a paper id. body: everything before References. abstract: the "**Abstract**:" paragraph, else the first paragraph after the title.
    """
    lines = (markdown or "").strip().splitlines()
    title = None
    for line in lines:
        text = line.strip()
        if text:
            title = text.lstrip("#").strip() if text.startswith("#") else text[:150]
            break

    body_lines, references, in_references = [], [], False
    for line in lines:
        if _REFERENCES_HEADING_RE.match(line):
            in_references = True
            continue
        if not in_references:
            body_lines.append(line)
            continue
        id_match = PAPER_ID_RE.search(line)
        if not id_match:
            continue
        number_match = _REFERENCE_NUMBER_RE.match(line)
        rest = line[id_match.end() :].lstrip(" `*]|—-:")
        role_match = _ROLE_RE.search(rest)
        rationale = rest[role_match.end() :].lstrip(" |—-:") if role_match else rest
        references.append({"n": int(number_match.group(1)) if number_match else len(references) + 1, "id": id_match.group(0), "role": role_match.group(1).lower() if role_match else None, "rationale": rationale.strip() or None})
    body = "\n".join(body_lines).strip()

    abstract_match = _ABSTRACT_RE.search(body)
    if abstract_match:
        abstract = abstract_match.group(1).strip()
    else:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and not p.strip().startswith("#")]
        abstract = paragraphs[0] if paragraphs else ""
    return title, abstract, body, references


def _proposal_shape(text):
    """(starts with a title and has an abstract or References, number of cited ids): tells a real proposal from the format template or a prose mention."""
    text = (text or "").strip()
    looks = text.startswith("#") and (_ABSTRACT_RE.search(text) is not None or any(_REFERENCES_HEADING_RE.match(line) for line in text.splitlines()))
    return looks, len(PAPER_ID_RE.findall(text)) if looks else 0


def inline_citation_numbers(body):
    """Citation numbers used in the prose, accepting [3], [3,4], [3; 4] and [3-5]."""
    numbers = set()
    for group in _INLINE_NUMBERS_RE.findall(body or ""):
        for part in re.split(r"[,;]", group):
            part = part.strip()
            span = _RANGE_RE.match(part)
            if span:
                low, high = int(span.group(1)), int(span.group(2))
                if low <= high <= low + 50:
                    numbers.update(str(x) for x in range(low, high + 1))
            elif part.isdigit():
                numbers.add(part)
    return numbers


def citation_check(body, references, retrieved):
    """Deterministic citation audit -> (issues, message or None).

    Flags ids never retrieved, one paper under several numbers, inline numbers with no References entry, and entries never cited inline.
    """
    number_of, duplicates, unknown = {}, {}, []
    for reference in references:
        paper_id, number = reference["id"], str(reference["n"])
        if paper_id not in retrieved:
            unknown.append(paper_id)
        if paper_id in number_of and number_of[paper_id] != number:
            duplicates.setdefault(paper_id, [number_of[paper_id]]).append(number)
        else:
            number_of.setdefault(paper_id, number)
    entry_numbers = {str(reference["n"]) for reference in references}
    inline_numbers = inline_citation_numbers(body)
    issues = {"unknown_ids": sorted(set(unknown)), "duplicate_ids": dict(duplicates), "inline_without_entry": sorted(inline_numbers - entry_numbers, key=int), "entry_never_cited": sorted(entry_numbers - inline_numbers, key=int)}
    parts = []
    if issues["unknown_ids"]:
        parts.append("id(s) never retrieved (will be DROPPED): " + ", ".join(issues["unknown_ids"]))
    if issues["duplicate_ids"]:
        parts.append("same document listed under several numbers: " + "; ".join(f"{k} as [" + "], [".join(v) + "]" for k, v in issues["duplicate_ids"].items()) + " — keep ONE number per document")
    if issues["inline_without_entry"]:
        parts.append("inline citation(s) with no References entry: [" + "], [".join(issues["inline_without_entry"]) + "]")
    if issues["entry_never_cited"]:
        parts.append("References entry/entries never cited inline: [" + "], [".join(issues["entry_never_cited"]) + "]")
    return issues, ("Citation check — " + "; ".join(parts) + ".") if parts else None


# --------------------------------------------------------------------- actions
def _tag_strength(reply, action, position):
    """How much an `<action>` occurrence looks like an opened block rather than a mention in prose: bit 4 = starts a line, bit 2 = followed by a newline or the end, bit 1 = a closing tag follows. 0 means prose."""
    tag_end = position + len(action) + 2
    line_start = reply.rfind("\n", 0, position) + 1
    strength = 0
    if reply[line_start:position].strip() == "":
        strength |= 4
    if reply[tag_end : tag_end + 1] in ("\n", ""):
        strength |= 2
    if reply.find(f"</{action}>", tag_end) >= 0:
        strength |= 1
    return strength


def _block(reply, action, position, actions):
    """(content, text after the block, closed?) of the `<action>` block at `position`: up to the last closing tag, else up to the next action tag."""
    start = position + len(action) + 2
    end = reply.rfind(f"</{action}>")
    if end > start:
        return reply[start:end], reply[end + len(action) + 3 :], True
    following = min((p for p in (reply.find(f"<{a}>", start) for a in actions) if p >= 0), default=-1)
    if following >= 0:
        return reply[start:following], reply[following:], False
    return reply[start:], "", False


def _pick_action(reply, actions):
    """(action, position) of the occurrence that most looks like a real block; ties go to the earliest. Among several <proposal> blocks, prefer the one shaped like a final proposal with the most references."""
    found = []
    for action in actions:
        start = 0
        while (position := reply.find(f"<{action}>", start)) >= 0:
            start = position + 1
            strength = _tag_strength(reply, action, position)
            # "<proposal> is final ..." on one line without the proposal shape is prose.
            if strength and action == "proposal" and not strength & 2 and not _proposal_shape(_block(reply, action, position, actions)[0])[0]:
                strength = 0
            if strength:
                found.append((strength, position, action))
    if not found:
        return None, len(reply) + 1
    strength, position, action = min(found, key=lambda f: (-f[0], f[1]))
    same = [f for f in found if f[2] == action]
    if action == "proposal" and len(same) > 1:
        strength, position, action = max(same, key=lambda f: (_proposal_shape(_block(reply, f[2], f[1], actions)[0]), f[0], -f[1]))
    return action, position


def parse_action(reply, actions):
    """Model reply -> (action, content, note).

    Executes one action per reply. `note` reports format problems the agent should hear about (unclosed tag, extra actions ignored, untagged final proposal accepted). Returns (None, None, None) when no action can be read.
    """
    reply = reply or ""
    action, position = _pick_action(reply, actions)
    if action:
        content, tail, closed = _block(reply, action, position, actions)
        notes = [] if closed else [f"your <{action}> block was not closed with </{action}>"]
        extra = [a for a in actions if f"<{a}>" in tail]
        if extra and action != "summary":  # a summary may quote other tags
            notes.append(f"your response contained multiple action tags; only the first (<{action}>) was executed, <{extra[0]}> was ignored")
        return action, content.strip(), "; ".join(notes) if notes else None
    if _proposal_shape(reply)[0]:
        return ("proposal", reply.strip(), "your response had no action tag; it matched the final-report shape and was accepted as <proposal> — always wrap actions in their tags")
    return None, None, None
