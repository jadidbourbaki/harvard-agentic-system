"""Agent implementation for the baseline agentic system.

This implementation uses vLLM's OpenAI-compatible server and queries
Prometheus metrics for accurate TTFT and TPOT measurements.
"""

from dataclasses import dataclass
from openai import OpenAI

from .metrics import MetricsManager


@dataclass
class AgentMetrics:
    """Metrics collected for each agent turn."""

    turn: int
    agent_id: str
    context_size: int
    tokens_generated: int
    ttft: float  # Average time to first token (prefill latency)
    tpot: float  # Average time per output token (decode latency)
    decode_time: float  # Average total decode time
    ttft_p50: float  # Median TTFT
    ttft_p99: float  # 99th percentile TTFT
    tpot_p50: float  # Median TPOT
    tpot_p99: float  # 99th percentile TPOT


class Agent:
    """An agent that participates in the story-finishing game."""

    def __init__(
        self,
        agent_id: str,
        client: OpenAI,
        model: str,
        k: int,
        c: int,
        temperature: float = 0.7,
        metrics_url: str | None = None,
    ):
        """
        Initialize an agent.

        Args:
            agent_id: Unique identifier for this agent
            client: OpenAI client connected to vLLM server
            model: Model name being served
            k: Number of inferences to perform (should equal c)
            c: Number of tokens to generate per turn
            temperature: Sampling temperature
            metrics_url: URL to vLLM's Prometheus metrics endpoint (defaults to base_url/metrics)
        """
        self.agent_id = agent_id
        self.client = client
        self.model = model
        self.k = k
        self.c = c
        self.temperature = temperature

        # Initialize metrics manager
        if metrics_url:
            self.metrics_manager = MetricsManager(metrics_url)
        else:
            # Extract base URL from OpenAI client (e.g., "http://localhost:8000/v1" -> "http://localhost:8000/metrics")
            base_url = (
                str(client.base_url)
                if hasattr(client, "base_url")
                else "http://localhost:8000"
            )
            metrics_url = base_url.replace("/v1", "").rstrip("/") + "/metrics"
            self.metrics_manager = MetricsManager(metrics_url)

    def generate_turn(
        self,
        turn: int,
        context: str,
    ) -> tuple[str, AgentMetrics]:
        """
        Generate tokens for a turn.

        Args:
            turn: Current turn number
            context: Context received from the other agent

        Returns:
            Tuple of (generated_tokens, metrics)
        """
        # Construct the prompt
        prompt = self._construct_prompt(context)

        # Query Prometheus metrics before request
        # vLLM exposes metrics at /metrics endpoint
        # See: https://docs.vllm.ai/en/latest/usage/metrics/#general-metrics
        metrics_before = self.metrics_manager.get_snapshot()

        # Make the request (non-streaming for simplicity)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.c,
            temperature=self.temperature,
        )

        # Extract generated text
        generated_text = response.choices[0].message.content
        if not generated_text:
            raise RuntimeError("No text generated from vLLM server")

        # Get token count from usage
        usage = response.usage
        if not usage:
            raise RuntimeError("No usage metrics in response")
        generated_tokens = usage.completion_tokens

        # Small delay to ensure Prometheus metrics have updated
        import time

        time.sleep(0.1)  # 100ms delay for metrics to update

        # Query Prometheus metrics after request and calculate delta
        metrics_after = self.metrics_manager.get_snapshot()
        delta = metrics_after.delta(metrics_before)

        # Extract per-request metrics from delta
        # If request_count delta is 0, metrics aren't updating - use fallback
        if delta.request_count == 0:
            # Metrics not updating - this can happen if vLLM hasn't processed the request yet
            # or if metrics aren't being exposed. Log a warning and use zeros.
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Metrics delta is 0 (before: {metrics_before.request_count}, "
                f"after: {metrics_after.request_count}). "
                "Prometheus metrics may not be updating correctly."
            )
            ttft = 0.0
            tpot = 0.0
            decode_time = 0.0
            ttft_p50 = 0.0
            ttft_p99 = 0.0
            tpot_p50 = 0.0
            tpot_p99 = 0.0
        else:
            ttft = delta.get_ttft()
            tpot = delta.get_tpot()
            decode_time = delta.get_decode_time()

            # Calculate percentiles (p50 = median, p99 = 99th percentile)
            ttft_p50 = delta.get_ttft_percentile(0.5)
            ttft_p99 = delta.get_ttft_percentile(0.99)
            tpot_p50 = delta.get_tpot_percentile(0.5)
            tpot_p99 = delta.get_tpot_percentile(0.99)

        return generated_text, AgentMetrics(
            turn=turn,
            agent_id=self.agent_id,
            context_size=len(context),
            tokens_generated=generated_tokens,
            ttft=ttft,
            tpot=tpot,
            decode_time=decode_time,
            ttft_p50=ttft_p50,
            ttft_p99=ttft_p99,
            tpot_p50=tpot_p50,
            tpot_p99=tpot_p99,
        )

    def _construct_prompt(self, context: str) -> str:
        """Construct the prompt for story finishing."""
        return f"""We are playing a story finishing game. It is your turn. You are only 
allowed to give me the next {self.c} tokens. You must give me exactly the next {self.c} 
tokens to finish the story. The story starts as follows:

Once upon a time {context}"""
