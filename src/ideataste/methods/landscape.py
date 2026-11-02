"""LANDSCAPE: a free LLM agent that also sees the area's 2025 task and method tags, with their shares, and can retrieve papers by tag (paper Appendix D.2)."""

import re
import unicodedata
from collections import Counter, defaultdict

from ideataste.agent import prompts
from ideataste.agent.episode import Tool
from ideataste.data import load_landscape
from ideataste.methods.base import Method

TOP_N = 100  # tags per axis and task-method pairs listed in the prompt
DEFAULT_K, MAX_K = 20, 50


def _normalize(label):
    label = unicodedata.normalize("NFKD", (label or "").lower())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", label).split())


class TagIndex:
    """The 2025 tags of one area: tag names on two axes and the tags of each paper. A tag is identified by (axis, name)."""

    def __init__(self, area):
        landscape = load_landscape(area)
        self.task, self.method = landscape["task_tags"], landscape["method_tags"]
        self.by_label = defaultdict(list)
        for kind, labels in (("task", self.task), ("method", self.method)):
            for label in labels:
                self.by_label[_normalize(label)].append((kind, label))
        self.rows = landscape["papers"]
        self.papers_by_tag, self.papers_by_pair = defaultdict(list), defaultdict(list)
        for row in self.rows:
            key = (str(row.get("date") or ""), row["id"])
            for tag in [("task", t) for t in row["tasks"]] + [("method", m) for m in row["methods"]]:
                self.papers_by_tag[tag].append(key)
            for pair in self._pairs(row):
                self.papers_by_pair[pair].append(key)
        for index in (self.papers_by_tag, self.papers_by_pair):
            for key in index:
                index[key].sort(reverse=True)  # newest first

    @staticmethod
    def _pairs(row):
        return [(("task", t), ("method", m)) for t in row["tasks"] for m in row["methods"]]

    def resolve(self, label):
        """label -> [(axis, name)]: exact normalised match, else substring matches."""
        wanted = _normalize(label)
        if not wanted:
            return []
        if wanted in self.by_label:
            return list(self.by_label[wanted])
        return [tag for known, hits in self.by_label.items() for tag in hits if wanted in known or known in wanted][:8]

    def _papers(self, task, method):
        if task and method:
            return self.papers_by_pair.get((task, method), [])
        return self.papers_by_tag.get(task or method, [])

    def papers_for(self, task=None, method=None, k=DEFAULT_K):
        """Newest k paper ids carrying the tag, or both tags when a pair is given."""
        return list(dict.fromkeys(paper_id for _date, paper_id in self._papers(task, method)))[:k]

    def n_papers(self, task=None, method=None):
        return len({paper_id for _date, paper_id in self._papers(task, method)})

    def landscape_text(self):
        """The landscape block (paper Figure "landscape block"): the most common tags on each axis and task-method pairs, with the share of the area's 2025 papers."""
        task_counts, method_counts, pair_counts = Counter(), Counter(), Counter()
        for row in self.rows:
            task_counts.update(row["tasks"])
            method_counts.update(row["methods"])
        for row in self.rows:
            pair_counts.update((t, m) for (_, t), (_, m) in self._pairs(row))
        n = max(len(self.rows), 1)

        def listing(items):
            return "; ".join(f"{label} ({count / n:.1%})" for label, count in sorted(items, key=lambda x: (-x[1], _normalize(x[0]))))

        tasks = listing(task_counts.most_common(TOP_N))
        methods = listing(method_counts.most_common(TOP_N))
        pairs = listing([(f"{t} × {m}", c) for (t, m), c in pair_counts.most_common(TOP_N)])
        tasks_per_paper = sum(len(r["tasks"]) for r in self.rows) / n
        methods_per_paper = sum(len(r["methods"]) for r in self.rows) / n
        return prompts.LANDSCAPE_BLOCK.format(n_task_tags=len(self.task), n_method_tags=len(self.method), tasks_per_paper=tasks_per_paper, methods_per_paper=methods_per_paper, top_n=TOP_N, tasks=tasks, methods=methods, pairs=pairs)


class TagPapers(Tool):
    """<tag_papers> pair: <task> x <method> | k: n </tag_papers>, or task: / method: alone."""

    name = "tag_papers"

    def __init__(self, index):
        self.index = index

    def _requested_tags(self, request):
        fields = re.sub(r"\bk\s*:\s*\d+\s*\|?", "", request, flags=re.I).strip(" |")
        pair = re.search(r"pair\s*:\s*(.+?)\s*(?:×|\bx\b|\*|\bvs\b)\s*(.+)$", fields, re.I)
        if pair:
            return {"task": pair.group(1).strip(), "method": pair.group(2).strip()}
        wanted = {}
        for kind in ("task", "method"):
            match = re.search(rf"{kind}\s*:\s*([^|]+)", fields, re.I)
            if match:
                wanted[kind] = match.group(1).strip()
        return wanted or {"task": fields}

    def run(self, episode, content):
        request = " ".join((content or "").split())[:200]
        k_match = re.search(r"\bk\s*:\s*(\d+)", request, re.I)
        k = min(int(k_match.group(1)), MAX_K) if k_match else DEFAULT_K
        tags, unresolved = {}, []
        for kind, label in self._requested_tags(request).items():
            hits = [h for h in self.index.resolve(label) if h[0] == kind] or self.index.resolve(label)
            if hits:
                tags[hits[0][0]] = hits[0]
                continue
            last_word = label.split()[-1] if label.split() else label
            near = [name for hit_kind, name in self.index.resolve(last_word)[:3] if hit_kind == kind]
            unresolved.append(f"{kind}: {label!r} is not in the listed {kind} tags" + (f" (closest listed: {', '.join(near)})" if near else ""))
        if unresolved:
            note = "; ".join(unresolved) + ". Only tags listed in the RESEARCH LANDSCAPE are accepted — copy the name verbatim from there."
            return {"kind": self.name, "query": request, "note": note}
        task, method = tags.get("task"), tags.get("method")
        papers = episode.retriever.papers_by_id(self.index.papers_for(task, method, k))
        named = ", ".join(f"{kind}={tag[1]}" for kind, tag in sorted(tags.items()))
        total = self.index.n_papers(task, method)
        return episode.result_event(self.name, request, [(paper, 1.0) for paper in papers], lambda new, old: (f"({len(papers)} of {total} papers for {named}; {new} new, {old} already retrieved earlier; newest first)"))


class Landscape(Method):
    name = "landscape"

    def __init__(self, area, corpus):
        super().__init__(area, corpus)
        self.index = TagIndex(area)

    def population(self, n):
        return [[{"agent_id": f"landscape-{i:04d}", "profile": prompts.FREE_PROFILE} for i in range(n)]]

    def system_prompt(self):
        return super().system_prompt() + prompts.LANDSCAPE_ACTION + prompts.LANDSCAPE_HEADER + self.index.landscape_text()

    def tools(self, agent):
        return (TagPapers(self.index),)
