"""FREE and TOPIC: the LLM agent is told only its community, or also one research topic."""

import math
from collections import Counter

from ideataste.agent import prompts
from ideataste.methods.base import Method

TOPIC_HALF_LIFE_YEARS = 2.0
TOPIC_BASE_YEAR = 2025
TOPIC_MIN_YEAR = 2000


class Free(Method):
    name = "free"

    def population(self, n):
        return [[{"agent_id": f"free-{i:04d}", "profile": prompts.FREE_PROFILE} for i in range(n)]]


def topic_prior(corpus):
    """Topic distribution of the corpus (paper Appendix D.2).

    Each paper splits its weight evenly over its OpenAlex topics, and is weighted by 0.5 ** ((2025 - year) / 2), so recent practice counts more.
    """
    mass = Counter()
    for paper in corpus:
        year = paper["publication_year"] or 0
        if year < TOPIC_MIN_YEAR:
            continue
        topics = [t for t in (paper.get("topic_names") or ()) if t]
        if not topics:
            continue
        weight = 0.5 ** ((TOPIC_BASE_YEAR - year) / TOPIC_HALF_LIFE_YEARS)
        for topic in topics:
            mass[topic] += weight / len(topics)
    total = sum(mass.values())
    return {topic: m / total for topic, m in mass.items() if m > 0}


def allocate(prior, n):
    """Largest-remainder allocation of n agents in proportion to `prior`; ties by name."""
    quota = {topic: p * n for topic, p in prior.items()}
    count = {topic: int(math.floor(q)) for topic, q in quota.items()}
    remaining = n - sum(count.values())
    for topic in sorted(prior, key=lambda t: (-(quota[t] - count[t]), t))[: max(remaining, 0)]:
        count[topic] += 1
    return {topic: c for topic, c in count.items() if c > 0}


def assign_topics(prior, n):
    """n topics, most allocated first (deterministic)."""
    allocation = allocate(prior, n)
    return [topic for topic in sorted(allocation, key=lambda t: (-allocation[t], t)) for _ in range(allocation[topic])]


def topic_agent(i, topic, prefix="topic"):
    return {"agent_id": f"{prefix}-{i:04d}", "topic": topic, "profile": prompts.TOPIC_PROFILE.replace("{topic}", topic)}


class Topic(Method):
    name = "topic"

    def population(self, n):
        return [[topic_agent(i, topic) for i, topic in enumerate(assign_topics(topic_prior(self.corpus), n))]]
