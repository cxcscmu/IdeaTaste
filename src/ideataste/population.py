"""Run a population: one method, one model, one area, n LLM agents.

Outputs in `out_dir`:
    proposals.jsonl      one record per LLM agent (written as each one finishes)
    trajectories.jsonl   the step-by-step trace of each LLM agent
    llm_calls.jsonl      every model call, verbatim

Re-running the same command resumes: finished LLM agents are kept. An LLM agent whose episode fails (no accepted proposal, or a crashed model call) is attempted again once.
"""

import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ideataste.agent.episode import Episode, Settings
from ideataste.data import area_path, load_corpus
from ideataste.jsonl import JsonlLog
from ideataste.methods import METHOD_CLASSES
from ideataste.retrieval import HybridRetriever, display_id

MAX_ATTEMPTS = 2


def load_agent_corpus(area):
    """Corpus papers as the LLM agent sees them, with their anonymous ids."""
    return [{**paper, "display_id": display_id(paper["id"])} for paper in load_corpus(area)]


def make_retriever(area, corpus):
    return HybridRetriever(corpus, cache_path=area_path(area, "corpus_embeddings.npy"))


def run_agent(method, system_prompt, agent, client, retriever, settings, round_number=1):
    """-> (record, trajectory) for one LLM agent, retrying a failed episode once."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        episode = Episode(client=client, retriever=retriever, system_prompt=system_prompt, profile=agent["profile"], tools=method.tools(agent), settings=settings, no_action_feedback=method.no_action_feedback, log_tag=f"{method.name}/{agent['agent_id']}/attempt{attempt}")
        try:
            record = episode.run()
        except Exception as error:  # noqa: BLE001 - recorded in the output, then retried
            record = {"failed": True, "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()[-2000:]}
        if not record["failed"] or attempt == MAX_ATTEMPTS:
            record = {"agent_id": agent["agent_id"], "round": round_number, "topic": agent.get("topic"), "profile": agent["profile"], "attempts": attempt, **record}
            return record, episode.trajectory


def run_population(method_name, area, n, out_dir, client, *, retriever=None, corpus=None, settings=None, concurrency=8):
    """Generate n proposals with `method_name` in `area`; returns the records."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus = corpus if corpus is not None else load_agent_corpus(area)
    retriever = retriever or make_retriever(area, corpus)
    settings = settings or Settings()
    method = METHOD_CLASSES[method_name](area, corpus)
    system_prompt = method.system_prompt()
    proposals, trajectories = JsonlLog(out_dir / "proposals.jsonl"), JsonlLog(out_dir / "trajectories.jsonl")
    done = {row["agent_id"]: row for row in proposals.read()}
    done_steps = {row["agent_id"]: row["steps"] for row in trajectories.read()}

    def work(agent, round_number):
        record, trajectory = run_agent(method, system_prompt, agent, client, retriever, settings, round_number)
        trajectories.append({"agent_id": agent["agent_id"], "steps": trajectory})
        proposals.append(record)  # written last: a record implies its trajectory
        done_steps[agent["agent_id"]] = trajectory
        return record

    all_records = []
    for index, agents in enumerate(method.population(n), start=1):
        todo = [agent for agent in agents if agent["agent_id"] not in done]
        print(f"[{method_name}/{area}] round {index}: {len(agents) - len(todo)} done, {len(todo)} to run", flush=True)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            fresh = list(pool.map(work, todo, [index] * len(todo)))
        records = {**{a["agent_id"]: done[a["agent_id"]] for a in agents if a["agent_id"] in done}, **{r["agent_id"]: r for r in fresh}}
        method.finish_round(agents, records, {a["agent_id"]: done_steps[a["agent_id"]] for a in agents})
        all_records.extend(records[a["agent_id"]] for a in agents)
    n_failed = sum(r["failed"] for r in all_records)
    print(f"[{method_name}/{area}] {len(all_records) - n_failed} proposals, {n_failed} failed -> {out_dir}", flush=True)
    return all_records
