"""Populations: topic allocation and FRONTIER rounds on a synthetic corpus."""

from collections import Counter

from ideataste.methods import Free, Frontier, Topic
from ideataste.methods.free_topic import allocate

CORPUS = [{"publication_year": 2025, "topic_names": ["A"]}] * 6 + [{"publication_year": 2023, "topic_names": ["B", "C"]}] * 4 + [{"publication_year": 1990, "topic_names": ["D"]}] * 50  # before 2000: ignored


def test_largest_remainder_allocation():
    assert allocate({"A": 0.5, "B": 0.3, "C": 0.2}, 7) == {"A": 4, "B": 2, "C": 1}
    assert sum(allocate({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}, 10).values()) == 10


def test_topic_population_follows_recency_weighted_prior():
    [agents] = Topic("auto_research", CORPUS).population(10)
    topics = Counter(agent["topic"] for agent in agents)
    # mass: A = 6, B = C = 4 * 0.5 / 2 = 1 -> 6/8, 1/8, 1/8 of 10 agents
    assert topics == {"A": 8, "B": 1, "C": 1}
    assert all("primary research area is: " + a["topic"] in a["profile"] for a in agents)


def test_frontier_splits_topic_population_into_two_rounds():
    rounds = Frontier("auto_research", CORPUS).population(11)
    assert [len(r) for r in rounds] == [6, 5]
    [topic_agents] = Topic("auto_research", CORPUS).population(11)
    assert Counter(a["topic"] for r in rounds for a in r) == Counter(a["topic"] for a in topic_agents)


def test_free_population():
    [agents] = Free("auto_research", CORPUS).population(3)
    assert len({a["agent_id"] for a in agents}) == 3
