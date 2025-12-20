"""Agent implementation for the baseline agentic system."""

from typing import List
from dataclasses import dataclass
from .util import (
    validate_outputs,
    validate_metrics,
    ttft_from_metrics,
    decode_time_from_metrics,
    tpot_from_metrics,
)

from vllm import LLM, SamplingParams


@dataclass
class AgentMetrics:
    """Metrics collected for each agent turn."""

    turn: int
    agent_id: str
    ttft: float  # Time to first token (prefill latency)
    tpot: float  # Time per output token (decode latency)
    context_size: int  # Size of context received
    tokens_generated: int  # Number of tokens generated (c)
    prefill_time: float
    decode_time: float


class Agent:
    """An agent that participates in the story-finishing game."""

    def __init__(
        self,
        agent_id: str,
        llm: LLM,
        k: int,
        c: int,
    ):
        """
        Initialize an agent.

        Args:
            agent_id: Unique identifier for this agent
            llm: vLLM LLM instance
            k: Number of inferences to perform (should equal c)
            c: Number of tokens to generate per turn
        """
        self.agent_id = agent_id
        self.llm = llm
        self.k = k
        self.c = c
        self.sampling_params = SamplingParams(
            temperature=0.7,
            max_tokens=c,
        )
        self.metrics: List[AgentMetrics] = []

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

        # Generate tokens
        # vLLM's RequestOutput includes RequestMetrics with accurate timing
        # See: https://docs.vllm.ai/en/latest/api/vllm/sequence/#vllm.sequence.RequestMetrics
        outputs = self.llm.generate([prompt], self.sampling_params)

        # some validation on the outputs
        generated_text = validate_outputs(outputs)

        # Get tokenizer for accurate token counting
        tokenizer = self.llm.get_tokenizer()
        # Count generated tokens directly (more efficient than encoding full text)
        generated_ids = tokenizer.encode(generated_text)
        generated_tokens = len(generated_ids)

        # Extract and validate metrics from RequestOutput
        # validate_metrics ensures all required timestamps are present and valid
        # See: https://docs.vllm.ai/en/latest/api/vllm/sequence/#vllm.sequence.RequestMetrics
        metrics_obj = validate_metrics(outputs)

        # Calculate metrics using helper functions
        # All timestamps are validated in validate_metrics
        ttft = ttft_from_metrics(metrics_obj)
        prefill_time = ttft
        decode_time = decode_time_from_metrics(metrics_obj)
        tpot = tpot_from_metrics(metrics_obj, generated_tokens)

        metrics = AgentMetrics(
            turn=turn,
            agent_id=self.agent_id,
            ttft=ttft,
            tpot=tpot,
            context_size=len(context),
            tokens_generated=generated_tokens,
            prefill_time=prefill_time,
            decode_time=decode_time,
        )

        self.metrics.append(metrics)

        return generated_text, metrics

    def _construct_prompt(self, context: str) -> str:
        """Construct the prompt for story finishing."""
        return f"""We are playing a story finishing game. It is your turn. You are only 
allowed to give me the next {self.c} tokens. You must give me exactly the next {self.c} 
tokens to finish the story. The story starts as follows:

Once upon a time {context}"""
