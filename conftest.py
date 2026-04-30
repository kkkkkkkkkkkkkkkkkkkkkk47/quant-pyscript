"""
Top-level pytest configuration for the Quant Ratings test suite.

Configures Hypothesis with a CI profile that runs 100 examples per property
and suppresses the too_slow health check (common in CI environments).
"""

from hypothesis import HealthCheck, settings

settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")
