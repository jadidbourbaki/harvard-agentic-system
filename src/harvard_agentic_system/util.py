from typing import List
from vllm import RequestOutput, RequestMetrics


def validate_outputs(outputs: List[RequestOutput]) -> str:
    """Validate the outputs from vLLM."""
    if len(outputs) == 0 or len(outputs[0].outputs) == 0:
        raise RuntimeError("No output from vLLM")

    generated_output = outputs[0].outputs[0]
    if not hasattr(generated_output, "text") or generated_output.text is None:
        raise RuntimeError("No text in generated output")

    generated_text = generated_output.text

    if not isinstance(generated_text, str):
        raise RuntimeError("Generated text is not a string")

    return generated_text


def validate_metrics(outputs: List[RequestOutput]) -> RequestMetrics:
    """
    Validate the metrics from vLLM RequestOutput.

    Ensures that:
    - Metrics object exists and is a RequestMetrics instance
    - Required timestamps (arrival_time, first_token_time, last_token_time) are present
    - Metrics are valid for calculating TTFT and TPOT

    Args:
        outputs: List of RequestOutput from vLLM

    Returns:
        Validated RequestMetrics object

    Raises:
        RuntimeError: If metrics are missing or invalid
    """
    if (
        len(outputs) == 0
        or not hasattr(outputs[0], "metrics")
        or outputs[0].metrics is None
    ):
        raise RuntimeError(
            "vLLM RequestOutput does not have metrics. "
            "Ensure you're using vLLM >= 0.7.0 with metrics enabled."
        )

    metrics = outputs[0].metrics
    if not isinstance(metrics, RequestMetrics):
        raise RuntimeError("Metrics is not a RequestMetrics object")

    # Validate required timestamps for TTFT calculation
    if not hasattr(metrics, "arrival_time") or metrics.arrival_time is None:
        raise RuntimeError(
            "RequestMetrics.arrival_time is None. "
            "This is required for calculating TTFT."
        )

    if not hasattr(metrics, "first_token_time") or metrics.first_token_time is None:
        raise RuntimeError(
            "RequestMetrics.first_token_time is None. "
            "This may indicate the request failed or was cancelled. "
            "Required for calculating TTFT."
        )

    # Validate timestamps for TPOT calculation
    # last_token_time is always available per RequestMetrics spec
    if not hasattr(metrics, "last_token_time") or metrics.last_token_time is None:
        raise RuntimeError(
            "RequestMetrics.last_token_time is None. "
            "This is required for calculating TPOT."
        )

    # Validate that timestamps are in logical order
    if metrics.first_token_time < metrics.arrival_time:
        raise RuntimeError(
            f"Invalid timestamps: first_token_time ({metrics.first_token_time}) "
            f"is before arrival_time ({metrics.arrival_time})."
        )

    if metrics.last_token_time < metrics.first_token_time:
        raise RuntimeError(
            f"Invalid timestamps: last_token_time ({metrics.last_token_time}) "
            f"is before first_token_time ({metrics.first_token_time})."
        )

    return metrics


def ttft_from_metrics(metrics: RequestMetrics) -> float:
    """
    Calculate TTFT (Time To First Token) from RequestMetrics.

    TTFT = time from request arrival to first token generation.
    This represents the prefill latency.

    Args:
        metrics: Validated RequestMetrics object

    Returns:
        TTFT in seconds
    """
    return metrics.first_token_time - metrics.arrival_time


def decode_time_from_metrics(metrics: RequestMetrics) -> float:
    """
    Calculate total decode time from RequestMetrics.

    Decode time = time from first token to last token (or finished time).
    This is the total time spent generating all output tokens.

    Args:
        metrics: Validated RequestMetrics object

    Returns:
        Total decode time in seconds
    """
    # Use finished_time if available (more accurate), otherwise last_token_time
    if metrics.finished_time is not None:
        return metrics.finished_time - metrics.first_token_time
    else:
        return metrics.last_token_time - metrics.first_token_time


def tpot_from_metrics(metrics: RequestMetrics, num_tokens: int) -> float:
    """
    Calculate TPOT (Time Per Output Token) from RequestMetrics.

    TPOT = average time per output token during decode phase.
    This is the decode time divided by the number of generated tokens.

    Args:
        metrics: Validated RequestMetrics object
        num_tokens: Number of output tokens generated

    Returns:
        TPOT in seconds per token (0.0 if num_tokens is 0)
    """
    if num_tokens == 0:
        return 0.0
    decode_time = decode_time_from_metrics(metrics)
    return decode_time / num_tokens
