"""The LLM agent: one ReAct episode that writes one research proposal.

Every step is one model call and exactly one action. The six shared actions are methods of `Episode`; a method (landscape, frontier) adds its own actions as `Tool`s, which receive the content of their tag and return a history event.
"""

from dataclasses import dataclass, field

from ideataste.agent import prompts
from ideataste.agent.parsing import PAPER_ID_RE, YEAR_FILTER_RE, citation_check, parse_action, parse_proposal
from ideataste.agent.render import render_turn

BASE_ACTIONS = ("plan", "search", "read_papers", "draft", "summary", "proposal")


class Tool:
    """An extra action. `run(episode, content)` returns a history event: a dict with `kind` and `query`, plus `results` [(paper, score)] and `receipt`, or `text`/`note`."""

    name = ""

    def run(self, episode, content):
        raise NotImplementedError


@dataclass
class Settings:
    step_budget: int = 20
    search_top_k: int = 10
    working_set_capacity: int = 50


@dataclass
class Episode:
    client: object  # .chat(system, user, tag=...) -> (reply, meta)
    retriever: object  # .search(query, top_k, year_range) -> [(paper, score)]
    system_prompt: str
    profile: str
    tools: tuple = ()
    settings: Settings = field(default_factory=Settings)
    no_action_feedback: str = prompts.NO_ACTION_FEEDBACK
    log_tag: str = "agent"

    def __post_init__(self):
        self.tool_of = {tool.name: tool for tool in self.tools}
        self.actions = BASE_ACTIONS + tuple(self.tool_of)
        self.handler_of = {"plan": self._plan, "search": self._search, "read_papers": self._read_papers, "draft": self._draft, "summary": self._summary}
        self.state = self._fresh_state()
        self.retrieved = {}  # display_id -> paper; the only papers a proposal may cite
        self.queries = set()  # (query.lower(), year_range) already searched
        self.n_searches = 0
        self.citation_bounced = False  # a proposal with fixable citation issues is bounced once
        self.trajectory = []

    @staticmethod
    def _fresh_state(working_set=None, last_request=None, clock=0, summary=None):
        return {
            "plan": None,
            "draft": None,
            "draft_feedback": None,
            "format_feedback": None,
            "summary": summary,
            "events": [],
            "working_set": working_set if working_set is not None else {},  # pin order
            "last_request": last_request if last_request is not None else {},  # for eviction
            "clock": clock,
        }

    # ------------------------------------------------------------------ loop
    def run(self):
        """Run until a proposal is accepted or the step budget is spent -> record."""
        budget = self.settings.step_budget
        for step in range(budget):
            steps_left = budget - step
            user = render_turn(self.profile, self.state, steps_left, self.settings.working_set_capacity)
            reply, meta = self.client.chat(self.system_prompt, user, tag=f"{self.log_tag}/step{step}")
            action, content, note = parse_action(reply, self.actions)
            self.state["format_feedback"] = f"Format warning: {note}. Use exactly ONE action tag per response." if note else None
            entry = {"step": step + 1, "action": action or "invalid", "text": content or reply or "", "reasoning": (meta or {}).get("reasoning")}
            self.trajectory.append(entry)
            if action is None:
                self.state["format_feedback"] = self.no_action_feedback
            elif action in self.tool_of:
                event = self.tool_of[action].run(self, content)
                self.state["events"].append(event)
                entry.update(observation=event.get("text") or event.get("note"))
            elif action == "proposal":
                record = self._submit(content, steps_left, entry)
                if record is not None:
                    return record
            else:
                self.handler_of[action](content, entry)
        return self._record(failed=True, steps_used=budget)

    # --------------------------------------------------------------- actions
    def _plan(self, content, entry):
        self.state["plan"] = content
        self.state["events"].append({"kind": "plan"})

    def _search(self, content, entry):
        query_text = " ".join((content or "").split())[:200]
        query, year_range = query_text, None
        year_filter = YEAR_FILTER_RE.search(query_text)
        if year_filter:
            low = int(year_filter.group(1))
            high = int(year_filter.group(2) or year_filter.group(1))
            year_range = (min(low, high), max(low, high))
            query = query_text[: year_filter.start()].rstrip(" |")
        self.n_searches += 1
        key = (query.lower(), year_range)
        if key in self.queries:
            self.state["events"].append({"kind": "search", "query": query_text, "note": "duplicate — you had already run this query"})
            entry.update(note="duplicate — skipped")
            return
        self.queries.add(key)
        results = self.retriever.search(query, self.settings.search_top_k, year_range=year_range)
        self.state["events"].append(self.result_event("search", query_text, results, lambda new, old: f"({len(results)} results; {new} new, {old} already retrieved earlier)"))
        entry.update(results=[p["display_id"] for p, _ in results])

    def result_event(self, kind, query, results, receipt):
        """History event for a result list; registers the results as retrieved. `receipt(new, old)` words the receipt from how many results were not seen before."""
        n_new = sum(1 for paper, _ in results if paper["display_id"] not in self.retrieved)
        self.retrieved.update({paper["display_id"]: paper for paper, _ in results})
        return {"kind": kind, "query": query, "results": results, "receipt": receipt(n_new, len(results) - n_new)}

    def _read_papers(self, content, entry):
        """Pin retrieved papers into the working set; evict least recently requested cards beyond capacity, sparing cards requested now or cited in the draft."""
        state = self.state
        ids = list(dict.fromkeys(PAPER_ID_RE.findall(content or "")))
        pinned = state["working_set"]
        already = [i for i in ids if i in pinned]
        new = [i for i in ids if i in self.retrieved and i not in pinned]
        unknown = [i for i in ids if i not in self.retrieved]
        for paper_id in already + new:
            state["clock"] += 1
            state["last_request"][paper_id] = state["clock"]
        for paper_id in new:
            pinned[paper_id] = self.retrieved[paper_id]
        cited_in_draft = set(PAPER_ID_RE.findall(state["draft"] or ""))
        requested = set(ids)
        evicted = []
        while len(pinned) > self.settings.working_set_capacity:
            victim = min(pinned, key=lambda i: (i in requested, i in cited_in_draft, state["last_request"].get(i, 0)))
            pinned.pop(victim)
            state["last_request"].pop(victim, None)
            evicted.append(victim)
        parts = []
        if new:
            parts.append("cards added to your working set below: " + ", ".join(new))
        if already:
            parts.append("already in your working set: " + ", ".join(already))
        if evicted:
            parts.append("evicted from working set (capacity): " + ", ".join(evicted))
        note = "(" + "; ".join(parts) + ")" if parts else "(no readable ids — copy ids verbatim from [CAND] lines you have already retrieved)"
        state["events"].append({"kind": "read_papers", "query": ", ".join(ids) or "(no valid ids)", "note": note})
        if unknown:
            state["format_feedback"] = "read_papers: unknown id(s) ignored: " + ", ".join(unknown) + ". Only ids from your [CAND] history are readable."
        entry.update(note=note)

    def _draft(self, content, entry):
        self.state["draft"] = content
        self.state["events"].append({"kind": "draft"})
        _title, _abstract, body, references = parse_proposal(content)
        if references:
            _issues, message = citation_check(body, references, self.retrieved)
        else:
            unknown = sorted(set(PAPER_ID_RE.findall(content or "")) - self.retrieved.keys())
            message = ("Citation check — id(s) never retrieved (will be DROPPED): " + ", ".join(unknown) + ".") if unknown else None
        self.state["draft_feedback"] = message
        entry.update(note=message)

    def _summary(self, content, entry):
        """Replace the history, plan and draft by the agent's notes; keep pinned papers."""
        state = self.state
        self.state = self._fresh_state(state["working_set"], state["last_request"], state["clock"], summary=content)

    def _submit(self, content, steps_left, entry):
        """Accept a proposal -> record, or give feedback and return None."""
        title, abstract, body, references = parse_proposal(content)
        if not (title or "").strip(" .·。…-—*#`'\"") or not body:
            self.state["format_feedback"] = prompts.UNPARSED_PROPOSAL_FEEDBACK
            entry.update(outcome="unparsed", note=prompts.UNPARSED_PROPOSAL_FEEDBACK)
            return None
        issues, message = citation_check(body, references, self.retrieved)
        fixable = bool(issues["duplicate_ids"] or issues["inline_without_entry"])
        if message and fixable and steps_left > 1 and not self.citation_bounced:
            self.citation_bounced = True
            self.state["format_feedback"] = message + " Fix these and output the corrected <proposal> in full."
            entry.update(outcome="citation issues", note=message)
            return None
        citations, n_invalid, seen = [], 0, set()
        for reference in references:
            paper_id = reference["id"]
            if paper_id in self.retrieved and paper_id not in seen:
                seen.add(paper_id)
                citations.append({"id": self.retrieved[paper_id]["id"], "display_id": paper_id, "n": reference["n"], "role": reference["role"], "rationale": reference["rationale"]})
            else:
                n_invalid += 1
        entry.update(note=message)
        return self._record(failed=False, steps_used=len(self.trajectory), proposal={"title": title, "abstract": abstract, "markdown": content}, citations=citations, n_invalid_citations=n_invalid, citation_check=issues)

    def _record(self, failed, steps_used, **extra):
        return {
            "failed": failed,
            "proposal": None,
            "citations": [],
            "n_invalid_citations": 0,
            **extra,
            "plan": self.state["plan"],
            "n_searches": self.n_searches,
            "queries": sorted(f"{q} | years: {r[0]}-{r[1]}" if r else q for q, r in self.queries),
            "actions": [e["action"] for e in self.trajectory],
            "retrieved_ids": sorted(self.retrieved),
            "steps_used": steps_used,
        }
