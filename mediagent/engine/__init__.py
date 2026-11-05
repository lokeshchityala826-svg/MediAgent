"""Deterministic clinical risk calculation engines."""

from mediagent.engine.news2 import NEWS2Calculator, NEWS2ScoreResult
from mediagent.engine.qsofa import QSOFACalculator, QSOFAScoreResult

__all__ = [
    "NEWS2Calculator",
    "NEWS2ScoreResult",
    "QSOFACalculator",
    "QSOFAScoreResult",
]
