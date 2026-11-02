"""What every method shares: the system prompt and the shape of a population."""

from ideataste.agent import prompts
from ideataste.catalog import area_config


def base_system_prompt(area):
    """The shared LLM agent prompt (paper Figure "agent prompt") for one area."""
    block = prompts.AREA_BLOCK.replace("{definition}", area_config(area)["definition"])
    return prompts.SYSTEM_TEMPLATE.replace("{area_block}", block)


class Method:
    """A method decides who the LLM agents are and what else they can do.

    population(n) -> rounds of agents, each agent a dict with `agent_id`, `profile` and optionally `topic`. Rounds run one after another; agents within a round run independently. A subclass overrides only what it changes.
    """

    name = ""
    no_action_feedback = prompts.NO_ACTION_FEEDBACK  # what the agent hears after a reply with no action

    def __init__(self, area, corpus):
        self.area, self.corpus = area, corpus

    def population(self, n):
        raise NotImplementedError

    def system_prompt(self):
        return base_system_prompt(self.area)

    def tools(self, agent):
        """Extra actions available to `agent` (see agent.episode.Tool)."""
        return ()

    def finish_round(self, agents, records, trajectories):
        """Called after each round with its agents, records and step trajectories."""
