"""Story-finishing game implementation."""

import time
import logging

from .agent import Agent, AgentMetrics
from .server import VLLMServer
from openai import OpenAI

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
        server_host: str = "localhost",
        server_port: int = 8000,
        manage_server: bool = True,
    ):
        """
        Initialize the game.

        Args:
            model_name: Name of the model to use (e.g., "mistralai/Mistral-7B-Instruct-v0.3")
            k: Number of inferences per turn (should equal c)
            c: Number of tokens to generate per turn
            num_turns: Total number of turns (T)
            server_host: vLLM server host
            server_port: vLLM server port
            manage_server: If True, automatically start/stop server. If False, assume server is already running.
        """
        self.model_name = model_name
        self.k = k
        self.c = c
        self.num_turns = num_turns
        self.server_host = server_host
        self.server_port = server_port
        self.manage_server = manage_server

        # Server and client
        self.server: VLLMServer | None = None
        self.client: OpenAI | None = None

        # Agents (initialized in start())
        self.agent_i: Agent | None = None
        self.agent_j: Agent | None = None

        self.context = ""  # Accumulated story context
        self.full_story = ""  # Complete story
        self.all_metrics: list[AgentMetrics] = []

    def start(self) -> None:
        """Start the vLLM server and initialize agents."""
        if self.manage_server:
            logger.info(f"Starting vLLM server for model: {self.model_name}")
            self.server = VLLMServer(
                model=self.model_name,
                host=self.server_host,
                port=self.server_port,
            )
            self.server.start()
        else:
            logger.info(
                f"Connecting to existing vLLM server at {self.server_host}:{self.server_port}"
            )

        # Create OpenAI client
        base_url = f"http://{self.server_host}:{self.server_port}/v1"
        self.client = OpenAI(
            base_url=base_url,
            api_key="dummy",  # vLLM doesn't require a real API key
        )

        # Create agents with metrics URL
        # TODO(hayder): support separate server instances for each agent.
        metrics_url = f"http://{self.server_host}:{self.server_port}/metrics"
        self.agent_i = Agent(
            "agent_i",
            self.client,
            self.model_name,
            self.k,
            self.c,
            metrics_url=metrics_url,
        )
        self.agent_j = Agent(
            "agent_j",
            self.client,
            self.model_name,
            self.k,
            self.c,
            metrics_url=metrics_url,
        )

        logger.info("Game initialized and ready")

    def stop(self) -> None:
        """Stop the vLLM server if managed."""
        if self.server and self.manage_server:
            self.server.stop()

    def run(self) -> dict:
        """
        Run the complete game.

        Returns:
            Dictionary with game results and metrics
        """
        # Ensure server is started and agents are initialized
        if self.agent_i is None or self.agent_j is None:
            raise RuntimeError("Game not started. Call start() before run().")

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

            # KV cache is cleared between turns:
            # - Each API request is independent (no shared request_id)
            # - Each request processes only the current context, not previous turns
            # - Between runs: server is stopped (via context manager), clearing all KV cache
            # This matches the baseline spec: agents clear KV cache after sending context

        game_end = time.time()
        total_time = game_end - game_start

        # Exclude turn 1 (warm-up) from aggregate metrics to measure steady-state performance
        # Turn 1 incurs cold start overhead (CUDA kernel init, memory allocation, etc.)
        steady_state_metrics = [m for m in self.all_metrics if m.turn > 1]

        # Aggregate metrics (excluding warm-up turn)
        if steady_state_metrics:
            avg_ttft = sum(m.ttft for m in steady_state_metrics) / len(
                steady_state_metrics
            )
            avg_tpot = sum(m.tpot for m in steady_state_metrics) / len(
                steady_state_metrics
            )
        else:
            # Fallback if only 1 turn
            avg_ttft = sum(m.ttft for m in self.all_metrics) / len(self.all_metrics)
            avg_tpot = sum(m.tpot for m in self.all_metrics) / len(self.all_metrics)

        # Calculate aggregate percentiles across all turns (excluding warm-up)
        ttft_values = (
            sorted([m.ttft for m in steady_state_metrics])
            if steady_state_metrics
            else sorted([m.ttft for m in self.all_metrics])
        )
        tpot_values = (
            sorted([m.tpot for m in steady_state_metrics])
            if steady_state_metrics
            else sorted([m.tpot for m in self.all_metrics])
        )

        def percentile(data: list[float], p: float) -> float:
            """Calculate percentile from sorted data."""
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = k - f
            if f + 1 < len(data):
                return data[f] + c * (data[f + 1] - data[f])
            return data[f]

        ttft_p50 = percentile(ttft_values, 0.5)
        ttft_p99 = percentile(ttft_values, 0.99)
        tpot_p50 = percentile(tpot_values, 0.5)
        tpot_p99 = percentile(tpot_values, 0.99)

        results = {
            "total_turns": self.num_turns,
            "total_time": total_time,
            "full_story": self.full_story,
            "final_context_length": len(self.context),
            "warmup_excluded": True,  # Turn 1 excluded from aggregate metrics
            "metrics": {
                "avg_ttft": avg_ttft,
                "avg_tpot": avg_tpot,
                "ttft_p50": ttft_p50,
                "ttft_p99": ttft_p99,
                "tpot_p50": tpot_p50,
                "tpot_p99": tpot_p99,
                "per_turn_metrics": [
                    {
                        "turn": m.turn,
                        "agent": m.agent_id,
                        "context_size": m.context_size,
                        "tokens_generated": m.tokens_generated,
                        "ttft": m.ttft,
                        "ttft_p50": m.ttft_p50,
                        "ttft_p99": m.ttft_p99,
                        "tpot": m.tpot,
                        "tpot_p50": m.tpot_p50,
                        "tpot_p99": m.tpot_p99,
                        "decode_time": m.decode_time,
                    }
                    for m in self.all_metrics
                ],
            },
        }

        return results

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
