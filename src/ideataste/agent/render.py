"""Render the LLM agent's state into the user message of each step.

The message is ordered from most to least stable so that a provider's prompt cache can reuse its prefix: profile, pinned papers, append-only history, latest full search results, workspace, then the step directive. Past history is never rewritten.
"""

from ideataste.agent import prompts

RESULT_EVENTS = ("search", "tag_papers")  # events that carry [CAND] results
SUMMARY_REMINDER_CHARS = 60_000  # suggest <summary> when the history grows past this
NO_DRAFT_NOTICE_STEPS = 5  # note a missing draft when this few steps remain
_ACTION_TAGS = ("plan", "search", "read_papers", "draft", "summary", "proposal")
_SOURCE_DISPLAY = {"arXiv (Cornell University)": "arXiv", "bioRxiv (Cold Spring Harbor Laboratory)": "bioRxiv", "medRxiv (Cold Spring Harbor Laboratory)": "medRxiv"}


def format_cards(results, shown=None, titles_only=False):
    """[CAND] cards for (paper, score) results.

    shown: {display_id: "title" | "full"} across one rendering, so a paper already shown at least as fully is replaced by "(shown above)".
    """
    lines = []
    for paper, _score in results:
        paper_id = paper.get("display_id", paper["id"])
        previous = shown.get(paper_id) if shown is not None else None
        if previous == "full" or (previous == "title" and titles_only):
            lines.append(f"[CAND] {paper_id}  (shown above)")
            continue
        if titles_only:
            if shown is not None:
                shown[paper_id] = "title"
            lines.append(f"[CAND] {paper_id}\n  year: {paper.get('publication_year')}\n  title: {paper.get('title')}")
            continue
        if shown is not None:
            shown[paper_id] = "full"
        abstract = (paper.get("abstract") or "").strip() or "(unknown — no abstract in this corpus)"
        source = paper.get("source_name") or "(unknown)"
        source = _SOURCE_DISPLAY.get(source, source)
        authors = [a for a in (paper.get("author_names") or []) if a]
        authors = (", ".join(authors[:8]) + (f" (+{len(authors) - 8} more)" if len(authors) > 8 else "")) if authors else "(unknown)"
        institutions = list(dict.fromkeys(i for i in (paper.get("institution_names") or []) if i))
        institutions = "; ".join(institutions[:5]) if institutions else "(unknown)"
        lines.append(f"[CAND] {paper_id}\n  year: {paper.get('publication_year')}\n  title: {paper.get('title')}\n  source: {source}\n  authors: {authors}\n  institutions: {institutions}\n  abstract: {abstract}")
    return "\n".join(lines)


def neutralize_tags(text):
    """<search> -> [search], so the agent's own notes can never read as executed actions."""
    if not text:
        return text
    for action in _ACTION_TAGS:
        text = text.replace(f"<{action}>", f"[{action}]").replace(f"</{action}>", f"[/{action}]")
    return text


def render_working_set(state, capacity):
    """Pinned papers in the order they were first pinned; the count goes last so pinning a new paper only appends."""
    pinned = state["working_set"]
    if not pinned:
        return ""
    return "<working_set>\n" + format_cards([(paper, 0.0) for paper in pinned.values()]) + f"\n({len(pinned)} of {capacity} cards pinned)\n</working_set>"


def render_history(state, compress_results):
    """One entry per step, in order. With compress_results, search results appear as title-only lines here and in full only in the latest-results block."""
    blocks = []
    if state["summary"]:
        blocks.append(f"(earlier steps condensed by you into these notes)\n<summary>\n{neutralize_tags(state['summary'])}\n</summary>")
    shown = {}
    for step, event in enumerate(state["events"], start=1):
        kind = event["kind"]
        if kind in ("plan", "draft"):
            blocks.append(f"step {step}  <{kind}> (rewritten — current version in your workspace below) </{kind}>")
            continue
        blocks.append(f"step {step}  <{kind}> {event.get('query')} </{kind}>")
        body = event.get("text") or event.get("note") or format_cards(event.get("results") or [], shown, titles_only=compress_results and kind in RESULT_EVENTS)
        if event.get("receipt"):
            body = f"{event['receipt']}\n{body}"
        blocks.append(f"<information>\n{body}\n</information>")
    return "\n".join(blocks) if blocks else "(no steps yet — this is your first step)"


def render_latest_results(state):
    """Full cards of the most recent search, replaced by the next search."""
    events = [e for e in state["events"] if e["kind"] in RESULT_EVENTS and e.get("results")]
    if not events:
        return ""
    latest = events[-1]
    return f"(from your search: {latest.get('query')})\n" + format_cards(latest["results"], {})


def render_workspace(state):
    blocks = []
    if state["plan"]:
        blocks.append(f"<plan>\n{neutralize_tags(state['plan'])}\n</plan>")
    if state["draft"]:
        blocks.append(f"<draft>\n{neutralize_tags(state['draft'])}\n</draft>")
    for key in ("draft_feedback", "format_feedback"):
        if state[key]:
            blocks.append(f"<feedback> {state[key]} </feedback>")
    return "\n".join(blocks) if blocks else "(empty — you have not written a plan or draft yet)"


def render_turn(profile, state, steps_left, working_set_capacity):
    """The user message of one step."""
    n_result_events = sum(1 for e in state["events"] if e["kind"] in RESULT_EVENTS)
    compress = n_result_events > 1  # only the latest search keeps full cards
    history = render_history(state, compress)
    pinned = render_working_set(state, working_set_capacity)
    latest = render_latest_results(state) if compress else ""
    if steps_left <= 1:
        directive, reminder = prompts.LAST_STEP_DIRECTIVE, ""
    else:
        directive = f"Steps remaining: {steps_left}. Choose your next action (ONE action only)."
        reminder = prompts.SUMMARY_REMINDER if len(history) > SUMMARY_REMINDER_CHARS else ""
        if steps_left <= NO_DRAFT_NOTICE_STEPS and not state["draft"]:
            reminder = prompts.NO_DRAFT_NOTICE + reminder
    return f"Your researcher profile:\n{profile}\n\n" + (f"Your pinned papers:\n{pinned}\n\n" if pinned else "") + f"Your history:\n{history}\n\n" + (f"Latest search results (full cards):\n{latest}\n\n" if latest else "") + f"Your workspace:\n{render_workspace(state)}\n\n" + f"{directive}{reminder}"
