"""Reusable, data-agnostic ARFI statistical primitives (pre-publication)."""
from .core import (
    CHARTS, CONTRACT, METHODS, VERSION, boxplot, ecdf, frequency,
    histogram, intervals, scatter, time_series,
)

__all__ = ["CHARTS", "CONTRACT", "METHODS", "VERSION", "histogram",
           "ecdf", "boxplot", "frequency", "scatter", "time_series", "intervals"]
