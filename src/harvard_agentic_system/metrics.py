"""Metrics manager for querying vLLM's Prometheus metrics."""

import requests
from typing import Any
from prometheus_client.parser import text_string_to_metric_families


class MetricsSnapshot:
    """Snapshot of vLLM metrics at a point in time."""

    def __init__(
        self, metrics: dict[str, float], buckets: dict[str, list[tuple[float, float]]]
    ):
        self.request_count = metrics.get("request_count", 0.0)
        self.ttft_sum = metrics.get("ttft_sum", 0.0)
        self.tpot_sum = metrics.get("tpot_sum", 0.0)
        self.decode_sum = metrics.get("decode_sum", 0.0)
        self.prefill_sum = metrics.get("prefill_sum", 0.0)

        # Histogram buckets: list of (bucket_boundary, cumulative_count) tuples
        self.ttft_buckets = buckets.get("ttft_buckets", [])
        self.tpot_buckets = buckets.get("tpot_buckets", [])
        self.decode_buckets = buckets.get("decode_buckets", [])

    def delta(self, other: "MetricsSnapshot") -> "MetricsDelta":
        """Calculate delta between two snapshots."""
        return MetricsDelta(
            request_count=self.request_count - other.request_count,
            ttft_sum=self.ttft_sum - other.ttft_sum,
            tpot_sum=self.tpot_sum - other.tpot_sum,
            decode_sum=self.decode_sum - other.decode_sum,
            prefill_sum=self.prefill_sum - other.prefill_sum,
            # Calculate bucket deltas for percentile calculation
            ttft_buckets=self._delta_buckets(self.ttft_buckets, other.ttft_buckets),
            tpot_buckets=self._delta_buckets(self.tpot_buckets, other.tpot_buckets),
            decode_buckets=self._delta_buckets(
                self.decode_buckets, other.decode_buckets
            ),
        )

    @staticmethod
    def _delta_buckets(
        current: list[tuple[float, float]], previous: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """
        Calculate delta between bucket counts.

        Note: Prometheus histogram bucket boundaries are fixed and must remain
        consistent between snapshots. If boundaries differ, this indicates a serious
        error in metrics collection.

        Raises:
            RuntimeError: If bucket boundaries differ between snapshots
        """
        # Verify boundaries match (they should be fixed in Prometheus)
        current_boundaries = {boundary for boundary, _ in current}
        previous_boundaries = {boundary for boundary, _ in previous}

        if current_boundaries != previous_boundaries:
            raise RuntimeError(
                f"Bucket boundaries differ between snapshots. "
                f"This indicates a serious error in metrics collection. "
                f"Current: {sorted(current_boundaries)}, "
                f"Previous: {sorted(previous_boundaries)}"
            )

        # Create a dict for quick lookup
        prev_dict = dict(previous)
        delta = []
        for boundary, count in current:
            prev_count = prev_dict.get(boundary, 0.0)
            delta.append((boundary, count - prev_count))

        return delta


class MetricsDelta:
    """Delta between two metrics snapshots."""

    def __init__(
        self,
        request_count: float,
        ttft_sum: float,
        tpot_sum: float,
        decode_sum: float,
        prefill_sum: float,
        ttft_buckets: list[tuple[float, float]],
        tpot_buckets: list[tuple[float, float]],
        decode_buckets: list[tuple[float, float]],
    ):
        self.request_count = request_count
        self.ttft_sum = ttft_sum
        self.tpot_sum = tpot_sum
        self.decode_sum = decode_sum
        self.prefill_sum = prefill_sum
        self.ttft_buckets = ttft_buckets
        self.tpot_buckets = tpot_buckets
        self.decode_buckets = decode_buckets

    def get_ttft(self) -> float:
        """Get average time to first token (TTFT) for this request."""
        if self.request_count > 0:
            return self.ttft_sum / self.request_count
        return 0.0

    def get_tpot(self) -> float:
        """Get average time per output token (TPOT) for this request."""
        if self.request_count > 0:
            return self.tpot_sum / self.request_count
        return 0.0

    def get_decode_time(self) -> float:
        """Get average total decode time for this request."""
        if self.request_count > 0:
            return self.decode_sum / self.request_count
        return 0.0

    def get_prefill_time(self) -> float:
        """Get average prefill time for this request."""
        if self.request_count > 0:
            return self.prefill_sum / self.request_count
        return 0.0

    def get_ttft_percentile(self, percentile: float) -> float:
        """Get TTFT percentile (0.0-1.0, e.g., 0.5 for median, 0.99 for p99)."""
        return self._calculate_percentile(self.ttft_buckets, percentile)

    def get_tpot_percentile(self, percentile: float) -> float:
        """Get TPOT percentile (0.0-1.0, e.g., 0.5 for median, 0.99 for p99)."""
        return self._calculate_percentile(self.tpot_buckets, percentile)

    def get_decode_time_percentile(self, percentile: float) -> float:
        """Get decode time percentile (0.0-1.0, e.g., 0.5 for median, 0.99 for p99)."""
        return self._calculate_percentile(self.decode_buckets, percentile)

    @staticmethod
    def _calculate_percentile(
        buckets: list[tuple[float, float]], percentile: float
    ) -> float:
        """
        Calculate percentile from histogram buckets.

        Args:
            buckets: List of (bucket_boundary, count) tuples, sorted by boundary
            percentile: Desired percentile (0.0-1.0)

        Returns:
            Percentile value, or 0.0 if no data
        """
        if not buckets:
            return 0.0

        # Calculate total count
        total_count = sum(count for _, count in buckets)
        if total_count == 0:
            return 0.0

        # Find the target count for this percentile
        target_count = total_count * percentile

        # Find the bucket where cumulative count crosses the threshold
        cumulative = 0.0
        for i, (boundary, count) in enumerate(buckets):
            cumulative += count
            if cumulative >= target_count:
                # Found the bucket containing the percentile
                if i == 0:
                    # First bucket, return its boundary
                    return boundary

                # Linear interpolation between previous and current bucket
                prev_boundary, prev_count = buckets[i - 1]
                prev_cumulative = cumulative - count

                # Interpolate
                ratio = (target_count - prev_cumulative) / count if count > 0 else 0.0
                return prev_boundary + ratio * (boundary - prev_boundary)

        # If we get here, percentile is beyond the last bucket
        return buckets[-1][0] if buckets else 0.0


class MetricsManager:
    """Manages querying and parsing vLLM's Prometheus metrics."""

    def __init__(self, metrics_url: str):
        """
        Initialize the metrics manager.

        Args:
            metrics_url: URL to vLLM's Prometheus metrics endpoint
        """
        self.metrics_url = metrics_url

    def get_snapshot(self) -> MetricsSnapshot:
        """
        Query Prometheus metrics and return a snapshot.

        Returns:
            MetricsSnapshot with current metric values and histogram buckets
        """
        metrics, buckets = self._query_prometheus_metrics()
        return MetricsSnapshot(metrics, buckets)

    def _query_prometheus_metrics(
        self,
    ) -> tuple[dict[str, float], dict[str, list[tuple[float, float]]]]:
        """
        Query vLLM's Prometheus metrics endpoint and parse relevant metrics.

        Note: vLLM exposes metrics in Prometheus exposition format at /metrics,
        but does not provide a Prometheus query API (/api/v1/query), so we cannot
        use PromQL. Instead, we parse the exposition format directly.

        Returns:
            Tuple of (metrics dict, buckets dict)
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            response = requests.get(self.metrics_url, timeout=5)
            response.raise_for_status()
            metrics_text = response.text

            # Parse using Prometheus client library
            families_by_name = {
                family.name: family
                for family in text_string_to_metric_families(metrics_text)
            }

            # Extract metrics using helper
            metrics = self._extract_sum_metrics(families_by_name, logger)
            buckets = self._extract_histogram_buckets(families_by_name, logger)

            if metrics.get("request_count", 0) == 0:
                logger.warning(
                    "request_count is 0. Metrics may not be updating or metric name changed."
                )

            return metrics, buckets
        except Exception as e:
            logger.error(f"Failed to query Prometheus metrics: {e}")
            raise RuntimeError(
                f"Failed to query Prometheus metrics from {self.metrics_url}: {e}"
            ) from e

    def _extract_sum_metrics(
        self, families_by_name: dict[str, Any], logger: Any
    ) -> dict[str, float]:
        """Extract sum metrics from parsed Prometheus families."""
        metrics = {}

        # Sum metrics - note: Prometheus client parses histogram families without _sum suffix
        # The _sum samples are within the histogram family
        sum_metric_mappings = {
            "ttft_sum": "vllm:time_to_first_token_seconds",
            "tpot_sum": "vllm:request_time_per_output_token_seconds",
            "prefill_sum": "vllm:request_prefill_time_seconds",
            "decode_sum": "vllm:request_decode_time_seconds",
        }

        for key, family_name in sum_metric_mappings.items():
            if family_name in families_by_name:
                family = families_by_name[family_name]
                # Look for samples with _sum suffix
                sum_samples = [
                    sample for sample in family.samples if sample.name.endswith("_sum")
                ]
                if sum_samples:
                    metrics[key] = sum(sample.value for sample in sum_samples)

        # Request count (try alternatives)
        # request_success has samples with _total suffix and finished_reason label
        for metric_name in [
            "vllm:request_success",
            "vllm:e2e_request_latency_seconds",
        ]:
            if metric_name in families_by_name:
                family = families_by_name[metric_name]
                # For request_success, sum all _total samples (across all finished_reason labels)
                # For e2e_request_latency_seconds, use _count samples
                if metric_name == "vllm:request_success":
                    total_samples = [
                        sample
                        for sample in family.samples
                        if sample.name.endswith("_total")
                    ]
                    metrics["request_count"] = sum(
                        sample.value for sample in total_samples
                    )
                else:
                    # e2e_request_latency_seconds has _count samples
                    count_samples = [
                        sample
                        for sample in family.samples
                        if sample.name.endswith("_count")
                    ]
                    metrics["request_count"] = sum(
                        sample.value for sample in count_samples
                    )

                break

        return metrics

    def _extract_histogram_buckets(
        self, families_by_name: dict[str, Any], logger: Any
    ) -> dict[str, list[tuple[float, float]]]:
        """Extract histogram buckets from parsed Prometheus families."""
        buckets = {}

        for bucket_key, metric_name in {
            "ttft_buckets": "vllm:time_to_first_token_seconds_bucket",
            "tpot_buckets": "vllm:request_time_per_output_token_seconds_bucket",
            "decode_buckets": "vllm:request_decode_time_seconds_bucket",
        }.items():
            if metric_name in families_by_name:
                family = families_by_name[metric_name]
                bucket_list = []
                for sample in family.samples:
                    le_value = sample.labels.get("le")
                    if le_value:
                        try:
                            boundary = (
                                float("inf") if le_value == "+Inf" else float(le_value)
                            )
                            bucket_list.append((boundary, sample.value))
                        except (ValueError, TypeError):
                            continue
                    bucket_list.sort(key=lambda x: x[0])
                    buckets[bucket_key] = bucket_list

        return buckets
