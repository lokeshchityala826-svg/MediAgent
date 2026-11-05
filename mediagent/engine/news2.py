"""Royal College of Physicians National Early Warning Score 2 (NEWS2) Calculator.

Reference:
Royal College of Physicians. National Early Warning Score (NEWS) 2:
Standardising the assessment of acute-illness severity in the NHS.
Updated report of a working party. London: RCP, 2017.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from mediagent.models.telemetry import VitalSigns, ConsciousnessLevel


@dataclass
class NEWS2ScoreResult:
    """Detailed breakdown of calculated NEWS2 score."""
    total_score: int
    risk_level: str               # "LOW", "LOW_MEDIUM", "MEDIUM", "HIGH"
    clinical_response: str
    parameter_scores: Dict[str, int]
    has_extreme_score: bool      # True if any individual parameter scores 3 (Red trigger)
    is_scale_2: bool


class NEWS2Calculator:
    """Deterministic, validated implementation of the RCP NEWS2 scoring algorithm."""

    @classmethod
    def calculate(cls, vitals: VitalSigns, is_copd_spo2_scale2: bool = False) -> NEWS2ScoreResult:
        """Calculate the complete NEWS2 score and clinical escalation band.

        Args:
            vitals: Point-in-time vital signs snapshot
            is_copd_spo2_scale2: True if patient has documented hypercapnic respiratory failure

        Returns:
            NEWS2ScoreResult with parameter breakdown and risk categorization
        """
        scores: Dict[str, int] = {}

        # 1. Respiration Rate
        scores["respiration_rate"] = cls._score_respiration_rate(vitals.respiratory_rate)

        # 2. SpO2 (Scale 1 vs Scale 2)
        if is_copd_spo2_scale2:
            scores["spo2"] = cls._score_spo2_scale2(vitals.spo2, vitals.on_supplemental_oxygen)
        else:
            scores["spo2"] = cls._score_spo2_scale1(vitals.spo2)

        # 3. Supplemental Oxygen
        scores["air_or_oxygen"] = 2 if vitals.on_supplemental_oxygen else 0

        # 4. Systolic Blood Pressure
        scores["systolic_bp"] = cls._score_systolic_bp(vitals.systolic_bp)

        # 5. Heart Rate (Pulse)
        scores["heart_rate"] = cls._score_heart_rate(vitals.heart_rate)

        # 6. Consciousness (AVPU)
        scores["consciousness"] = cls._score_consciousness(vitals.consciousness)

        # 7. Temperature
        scores["temperature"] = cls._score_temperature(vitals.temperature_c)

        total = sum(scores.values())
        has_extreme = any(s >= 3 for s in scores.values())

        # Determine clinical risk tier according to RCP guidance
        if total >= 7:
            risk_level = "HIGH"
            clinical_response = "Emergency assessment by critical care team / Medical Emergency Team (MET)."
        elif total >= 5:
            risk_level = "MEDIUM"
            clinical_response = "Urgent clinical review by ward doctor or acute care team within 1 hour."
        elif has_extreme:
            risk_level = "LOW_MEDIUM"
            clinical_response = "Urgent registered nurse review for single red-score parameter trigger."
        else:
            risk_level = "LOW"
            clinical_response = "Routine ward observation (12-hourly minimum monitoring frequency)."

        return NEWS2ScoreResult(
            total_score=total,
            risk_level=risk_level,
            clinical_response=clinical_response,
            parameter_scores=scores,
            has_extreme_score=has_extreme,
            is_scale_2=is_copd_spo2_scale2,
        )

    @staticmethod
    def _score_respiration_rate(rr: float) -> int:
        if rr <= 8:
            return 3
        elif 9 <= rr <= 11:
            return 1
        elif 12 <= rr <= 20:
            return 0
        elif 21 <= rr <= 24:
            return 2
        else:  # >= 25
            return 3

    @staticmethod
    def _score_spo2_scale1(spo2: float) -> int:
        if spo2 <= 91:
            return 3
        elif 92 <= spo2 <= 93:
            return 2
        elif 94 <= spo2 <= 95:
            return 1
        else:  # >= 96
            return 0

    @staticmethod
    def _score_spo2_scale2(spo2: float, on_oxygen: bool) -> int:
        if spo2 <= 83:
            return 3
        elif 84 <= spo2 <= 85:
            return 2
        elif 86 <= spo2 <= 87:
            return 1
        elif 88 <= spo2 <= 92:
            return 0
        else:  # >= 93
            if on_oxygen:
                if 93 <= spo2 <= 94:
                    return 1
                elif 95 <= spo2 <= 96:
                    return 2
                else:  # >= 97
                    return 3
            else:
                return 0

    @staticmethod
    def _score_systolic_bp(sbp: float) -> int:
        if sbp <= 90:
            return 3
        elif 91 <= sbp <= 100:
            return 2
        elif 101 <= sbp <= 110:
            return 1
        elif 111 <= sbp <= 219:
            return 0
        else:  # >= 220
            return 3

    @staticmethod
    def _score_heart_rate(hr: float) -> int:
        if hr <= 40:
            return 3
        elif 41 <= hr <= 50:
            return 1
        elif 51 <= hr <= 90:
            return 0
        elif 91 <= hr <= 110:
            return 1
        elif 111 <= hr <= 130:
            return 2
        else:  # >= 131
            return 3

    @staticmethod
    def _score_consciousness(avpu: ConsciousnessLevel) -> int:
        if avpu == ConsciousnessLevel.ALERT:
            return 0
        return 3  # VOICE, PAIN, UNRESPONSIVE (or newly confused)

    @staticmethod
    def _score_temperature(temp_c: float) -> int:
        if temp_c <= 35.0:
            return 3
        elif 35.1 <= temp_c <= 36.0:
            return 1
        elif 36.1 <= temp_c <= 38.0:
            return 0
        elif 38.1 <= temp_c <= 39.0:
            return 1
        else:  # >= 39.1
            return 2
