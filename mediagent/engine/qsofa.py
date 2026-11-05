"""Quick Sepsis-related Organ Failure Assessment (qSOFA) Calculator.

Reference:
Singer M, Deutschman CS, Seymour CW, et al. The Third International Consensus
Definitions for Sepsis and Septic Shock (Sepsis-3). JAMA. 2016;315(8):801-810.
"""

from dataclasses import dataclass
from typing import Dict

from mediagent.models.telemetry import VitalSigns, ConsciousnessLevel


@dataclass
class QSOFAScoreResult:
    """Breakdown of calculated qSOFA score and clinical risk interpretation."""
    total_score: int              # 0 to 3
    is_positive: bool             # Score >= 2
    clinical_risk: str            # "LOW" or "HIGH"
    criteria_met: Dict[str, bool]
    guideline_statement: str


class QSOFACalculator:
    """Deterministic qSOFA screening algorithm for bedside sepsis risk evaluation."""

    @classmethod
    def calculate(cls, vitals: VitalSigns) -> QSOFAScoreResult:
        """Evaluate bedside qSOFA criteria.

        Args:
            vitals: Current vital signs snapshot

        Returns:
            QSOFAScoreResult containing individual criteria flags and composite score
        """
        criteria = {}

        # 1. Respiratory Rate >= 22 breaths/min
        criteria["respiratory_rate_ge_22"] = vitals.respiratory_rate >= 22.0

        # 2. Altered Mentation (GCS < 15 or AVPU != ALERT)
        criteria["altered_mentation"] = (
            vitals.gcs < 15 or vitals.consciousness != ConsciousnessLevel.ALERT
        )

        # 3. Systolic Blood Pressure <= 100 mmHg
        criteria["systolic_bp_le_100"] = vitals.systolic_bp <= 100.0

        score = sum(1 for met in criteria.values() if met)
        is_pos = score >= 2

        if is_pos:
            risk = "HIGH"
            statement = (
                "qSOFA >= 2: Clinically significant risk of deterioration, prolonged ICU stay, "
                "or hospital mortality in patients with suspected infection. Prompt sepsis bundle initiation recommended."
            )
        else:
            risk = "LOW"
            statement = "qSOFA < 2: Sepsis criteria not acutely met at bedside. Continue ongoing surveillance."

        return QSOFAScoreResult(
            total_score=score,
            is_positive=is_pos,
            clinical_risk=risk,
            criteria_met=criteria,
            guideline_statement=statement,
        )
