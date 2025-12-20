"""Story-finishing game implementation."""

from typing import List
import time
import logging

from .agent import Agent, AgentMetrics
from vllm import LLM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StoryFinishingGame:
    """Implements the baseline story-finishing game."""

    def __init__(
        self,
        model_name: str,
        k: int,
        c: int,
        num_turns: int,
    ):
        """
        Initialize the game.

        Args:
            model_name: Name of the model to use (e.g., "meta-llama/Llama-3.1-8B-Instruct")
            k: Number of inferences per turn (should equal c)
            c: Number of tokens to generate per turn
            num_turns: Total number of turns (T)
        """
        self.model_name = model_name
        self.k = k
        self.c = c
        self.num_turns = num_turns

        # Initialize LLM (shared between agents for now)
        # TODO(hayder): support separate instances for each agent.
        print(f"Loading model: {model_name}")
        self.llm = LLM(model=model_name)

        # Create agents
        self.agent_i = Agent("agent_i", self.llm, k, c)
        self.agent_j = Agent("agent_j", self.llm, k, c)

        self.context = ""  # Accumulated story context
        self.full_story = ""  # Complete story
        self.all_metrics: List[AgentMetrics] = []

    def run(self) -> dict:
        """
        Run the complete game.

        Returns:
            Dictionary with game results and metrics
        """
        logger.info(f"Starting game with {self.num_turns} turns")
        game_start = time.time()

        for turn in range(1, self.num_turns + 1):
            # Determine which agent's turn it is
            if turn % 2 == 1:  # Odd turns: agent i
                agent = self.agent_i
                agent_name = "agent_i"
            else:  # Even turns: agent j
                agent = self.agent_j
                agent_name = "agent_j"

            logger.info(f"\nTurn {turn}: {agent_name}'s turn")
            logger.info(f"Current context length: {len(self.context)} characters")

            # Agent generates tokens
            generated_text, metrics = agent.generate_turn(turn, self.context)

            # Update context
            self.context += " " + generated_text
            self.full_story += generated_text

            # Store metrics
            self.all_metrics.append(metrics)

            logger.info(f"Generated {metrics.tokens_generated} tokens")
            logger.info(f"TTFT: {metrics.ttft:.4f}s, TPOT: {metrics.tpot:.4f}s")
            logger.info(f"Generated text: {generated_text[:100]}...")

            # Clear KV-cache (in vLLM, this happens by ending the request)
            # The next request will rebuild the cache from the new context

        game_end = time.time()
        total_time = game_end - game_start

        # Aggregate metrics
        avg_ttft = sum(m.ttft for m in self.all_metrics) / len(self.all_metrics)
        avg_tpot = sum(m.tpot for m in self.all_metrics) / len(self.all_metrics)

        results = {
            "total_turns": self.num_turns,
            "total_time": total_time,
            "full_story": self.full_story,
            "final_context_length": len(self.context),
            "metrics": {
                "avg_ttft": avg_ttft,
                "avg_tpot": avg_tpot,
                "per_turn_metrics": [
                    {
                        "turn": m.turn,
                        "agent": m.agent_id,
                        "ttft": m.ttft,
                        "tpot": m.tpot,
                        "context_size": m.context_size,
                        "tokens_generated": m.tokens_generated,
                        "prefill_time": m.prefill_time,
                        "decode_time": m.decode_time,
                    }
                    for m in self.all_metrics
                ],
            },
        }

        return results
