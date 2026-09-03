"""
Tests for the pure calculation functions in binance_market.py — no network,
no mocking needed, since compute_volume_anomaly and compute_oi_trend take
plain data in and return plain data out.

Run with: pytest tests/test_binance_market.py -v
"""

import pytest
from agent.tools.binance_market import compute_volume_anomaly, compute_oi_trend


class TestComputeVolumeAnomaly:
    def test_normal_volume_is_not_anomalous(self):
        result = compute_volume_anomaly(
            current_24h_quote_volume=1_000_000,
            historical_daily_volumes=[950_000, 1_020_000, 980_000, 1_010_000, 990_000, 1_000_000, 970_000],
        )
        assert result["is_anomaly"] is False
        assert result["baseline_avg_volume"] == pytest.approx(988_571.43, rel=0.01)

    def test_spike_volume_is_anomalous(self):
        result = compute_volume_anomaly(
            current_24h_quote_volume=2_000_000,  # roughly double baseline
            historical_daily_volumes=[950_000, 1_020_000, 980_000, 1_010_000, 990_000, 1_000_000, 970_000],
        )
        assert result["is_anomaly"] is True
        assert result["pct_above_baseline"] > 40.0

    def test_exactly_at_threshold_boundary(self):
        # baseline 1,000,000 -> 40% above = 1,400,000 exactly at the boundary (not > threshold)
        result = compute_volume_anomaly(
            current_24h_quote_volume=1_400_000,
            historical_daily_volumes=[1_000_000] * 7,
        )
        assert result["pct_above_baseline"] == 40.0
        assert result["is_anomaly"] is False  # strictly greater than 40, not equal

    def test_no_history_returns_safe_default(self):
        result = compute_volume_anomaly(current_24h_quote_volume=1_000_000, historical_daily_volumes=[])
        assert result["is_anomaly"] is False
        assert result["baseline_avg_volume"] is None

    def test_low_volume_is_not_anomalous(self):
        """Below-baseline volume shouldn't trigger the anomaly flag (it only fires on spikes)."""
        result = compute_volume_anomaly(
            current_24h_quote_volume=400_000,
            historical_daily_volumes=[1_000_000] * 7,
        )
        assert result["is_anomaly"] is False
        assert result["pct_above_baseline"] == -60.0


class TestComputeOiTrend:
    def test_building_oi(self):
        result = compute_oi_trend([100_000, 102_000, 105_000, 110_000])
        assert result["direction"] == "building"
        assert result["pct_change"] == 10.0

    def test_unwinding_oi(self):
        result = compute_oi_trend([100_000, 95_000, 90_000, 88_000])
        assert result["direction"] == "unwinding"
        assert result["pct_change"] == -12.0

    def test_flat_oi(self):
        result = compute_oi_trend([100_000, 101_000, 99_500, 102_000])
        assert result["direction"] == "flat"

    def test_insufficient_data(self):
        result = compute_oi_trend([100_000])
        assert result["direction"] == "unknown"
        assert result["pct_change"] is None

    def test_empty_data(self):
        result = compute_oi_trend([])
        assert result["direction"] == "unknown"
