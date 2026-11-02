"""FRONTIER: TOPIC run in rounds, where each round can search and read the proposals and research traces of earlier rounds (paper Sec. 3.3 and Appendix D.2)."""

import json
import random
import re
import unicodedata
from collections import Counter

from ideataste.agent import prompts
from ideataste.agent.episode import Tool
from ideataste.methods.base import Method
from ideataste.methods.free_topic import assign_topics, topic_agent, topic_prior

N_ROUNDS = 2
SEED = 0
TRACE_ACTIONS = ("plan", "search", "read_papers", "draft", "summary")
TRACE_CHARS, PROPOSAL_CHARS = 1200, 12000


def _words(text):
    return set(re.findall(r"\w+", " ".join(unicodedata.normalize("NFKC", text).casefold().split())))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def split_into_rounds(topics, n_rounds=N_ROUNDS, seed=SEED):
    """Spread the TOPIC allocation over rounds of near-equal size, balancing each topic across rounds, then shuffle every round. Same random draws as the paper's runs."""
    total = len(topics)
    sizes = sorted([total - total // n_rounds * (n_rounds - 1)] + [total // n_rounds] * (n_rounds - 1), reverse=True)
    rng = random.Random(seed)
    rng.sample(range(total), total // 5)  # an unused draw kept for identical rounds
    rounds, counts = [[] for _ in sizes], [Counter() for _ in sizes]
    for i, topic in enumerate(topics):
        open_rounds = [r for r in range(n_rounds) if len(rounds[r]) < sizes[r]]
        rng.shuffle(open_rounds)
        r = min(open_rounds, key=lambda r: (counts[r][topic], len(rounds[r])))
        rounds[r].append({**topic_agent(i, topic, prefix="frontier"), "round": r})
        counts[r][topic] += 1
    for agents in rounds:
        rng.shuffle(agents)
    return rounds


class PeerHistory:
    """Read-only record of completed rounds: one summary row and one research path per LLM agent. Peer work is unvalidated and cannot be cited."""

    def __init__(self):
        self.rows, self.paths = [], {}

    def publish(self, agents, records, trajectories):
        for agent in agents:
            record, trajectory = records[agent["agent_id"]], trajectories[agent["agent_id"]]
            proposal = record.get("proposal") or {}
            record_id = f"r{agent['round']}/{agent['agent_id']}"
            self.rows.append(
                {
                    "record_id": record_id,
                    "round": agent["round"],
                    "agent_id": agent["agent_id"],
                    "topic": agent["topic"],
                    "question": proposal.get("title") or "",
                    "title": (proposal.get("title") or "")[:500],
                    "abstract": (proposal.get("abstract") or "")[:3000],
                    "status": "incomplete" if record["failed"] else "proposal_completed",
                    "scientifically_validated": False,
                }
            )
            markdown = proposal.get("markdown") or ""
            self.paths[record_id] = {
                "record_id": record_id,
                "round": agent["round"],
                "trajectory": [{"step": s["step"], "action": s["action"], "content": s["text"][:TRACE_CHARS], "truncated": len(s["text"]) > TRACE_CHARS} for s in trajectory if s["action"] in TRACE_ACTIONS],
                "queries": record.get("queries", []),
                "proposal": markdown[:PROPOSAL_CHARS],
                "proposal_truncated": len(markdown) > PROPOSAL_CHARS,
                "citations": record.get("citations", []),
                "source_ids": record.get("retrieved_ids", []),
                "scientifically_validated": False,
            }


class _PeerTool(Tool):
    """Peer tools take a JSON object and answer in JSON; errors are reported, not raised."""

    def __init__(self, history, agent, seen):
        self.history, self.agent, self.seen = history, agent, seen

    def run(self, episode, content):
        try:
            request = json.loads(content)
            if not isinstance(request, dict):
                raise ValueError("action payload must be a JSON object")
            result = self.answer(request)
        except (ValueError, TypeError) as error:
            result = {"error": str(error), "recorded": False}
        return {"kind": self.name, "query": content, "text": _json(result)}


class SearchHistory(_PeerTool):
    name = "search_history"

    def answer(self, request):
        query, scope, limit = request.get("query"), request.get("scope", "topic"), request.get("limit", 5)
        if not (isinstance(query, str) and query.strip()) or len(query) > 500 or scope not in ("topic", "all"):
            raise ValueError("query required (<=500 characters); scope must be topic or all")
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("limit must be an integer from 1 to 10")
        terms = _words(query)
        ranked = []
        for row in self.history.rows:
            if row["agent_id"] == self.agent["agent_id"]:
                continue
            if scope == "topic" and row["topic"] != self.agent["topic"]:
                continue
            score = len(terms & _words(" ".join(str(row.get(k) or "") for k in ("question", "title", "abstract", "topic"))))
            if query.strip() == "*" or score:
                ranked.append((score, row))
        ranked.sort(key=lambda pair: (-pair[0], -pair[1]["round"], pair[1]["record_id"]))
        rows = [row for _, row in ranked[:limit]]
        self.seen.update({row["record_id"]: row for row in rows})
        return {"records": rows, "matched": len(ranked), "note": "Generated peer work only; no validated results. No match is not proof of novelty."}


class ReadHistory(_PeerTool):
    name = "read_history"

    def answer(self, request):
        ids = request.get("record_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or any(not isinstance(i, str) or i not in self.seen for i in ids):
            raise ValueError("read 1-3 record_ids returned by search_history in this episode")
        return {"records": [{"record": self.seen[i], "research": self.history.paths.get(i), "note": "Observed actions, not verified lessons."} for i in dict.fromkeys(ids)]}


class Frontier(Method):
    name = "frontier"
    no_action_feedback = prompts.FRONTIER_NO_ACTION_FEEDBACK

    def __init__(self, area, corpus):
        super().__init__(area, corpus)
        self.history = PeerHistory()

    def population(self, n):
        return split_into_rounds(assign_topics(topic_prior(self.corpus), n))

    def system_prompt(self):
        return super().system_prompt() + prompts.FRONTIER_ACTIONS

    def tools(self, agent):
        seen = {}  # records this agent has found, the only ones it may read
        return (SearchHistory(self.history, agent, seen), ReadHistory(self.history, agent, seen))

    def finish_round(self, agents, records, trajectories):
        self.history.publish(agents, records, trajectories)
