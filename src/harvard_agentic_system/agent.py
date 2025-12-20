"""Agent implementation for the baseline agentic system.

This implementation uses vLLM's OpenAI-compatible server for accurate
TTFT and TPOT metrics collection.
"""

from dataclasses import dataclass
from openai import OpenAI


@dataclass
class AgentMetrics:
    """Metrics collected for each agent turn."""

    turn: int
    agent_id: str
    context_size: int
    tokens_generated: int
    ttft: float  # Time to first token (prefill latency)
    tpot: float  # Time per output token (decode latency)
    decode_time: float  # Total decode time


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
        """
        self.agent_id = agent_id
        self.client = client
        self.model = model
        self.k = k
        self.c = c
        self.temperature = temperature

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

        # Call vLLM server via OpenAI API
        # Each request is independent (no request_id) to ensure fresh KV cache per turn
        # Between runs, the server is stopped (clearing all KV cache)
        # This matches the baseline spec: agents clear KV cache after sending context
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.c,
            temperature=self.temperature,
            # Each request is independent - no request_id means fresh KV cache
            extra_body={
                "include_usage": True,
            },
        )

        # Extract generated text
        generated_text = response.choices[0].message.content
        if not generated_text:
            raise RuntimeError("No text generated from vLLM server")

        # Extract metrics from response
        # vLLM's OpenAI server provides detailed timing metrics
        usage = response.usage
        if not usage:
            raise RuntimeError("No usage metrics in response")

        generated_tokens = usage.completion_tokens

        # Extract timing metrics from vLLM's response
        # TODO: vLLM's exact metric fields may vary by version
        # We'll refine these field names after testing on Lambda
        extra = getattr(usage, "model_extra", {}) or {}

        # Get timing metrics (field names to be confirmed during testing)
        ttft = extra.get("time_to_first_token", extra.get("ttft", 0.0))
        decode_time = extra.get("decode_time", extra.get("generation_time", 0.0))
        tpot = decode_time / generated_tokens if generated_tokens > 0 else 0.0

        return generated_text, AgentMetrics(
            turn=turn,
            agent_id=self.agent_id,
            context_size=len(context),
            tokens_generated=generated_tokens,
            ttft=ttft,
            tpot=tpot,
            decode_time=decode_time,
        )

    def _construct_prompt(self, context: str) -> str:
        """Construct the prompt for story finishing."""
        return f"""We are playing a story finishing game. It is your turn. You are only 
allowed to give me the next {self.c} tokens. You must give me exactly the next {self.c} 
tokens to finish the story. The story starts as follows:

Once upon a time {context}"""
