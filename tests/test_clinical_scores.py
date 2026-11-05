"""Unit tests for deterministic clinical scoring algorithms (NEWS2 & qSOFA)."""

from datetime import datetime
from mediagent.models.telemetry import VitalSigns, ConsciousnessLevel, OxygenDevice
from mediagent.engine.news2 import NEWS2Calculator
from mediagent.engine.qsofa import QSOFACalculator


def test_news2_normal_patient():
    vitals = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-NORM",
        heart_rate=72.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=16.0,
        spo2=98.0,
        temperature_c=36.8,
        on_supplemental_oxygen=False,
        consciousness=ConsciousnessLevel.ALERT,
    )

    result = NEWS2Calculator.calculate(vitals, is_copd_spo2_scale2=False)

    assert result.total_score == 0
    assert result.risk_level == "LOW"
    assert result.has_extreme_score is False
    assert result.parameter_scores["respiration_rate"] == 0
    assert result.parameter_scores["spo2"] == 0
    assert result.parameter_scores["air_or_oxygen"] == 0
    assert result.parameter_scores["systolic_bp"] == 0
    assert result.parameter_scores["heart_rate"] == 0
    assert result.parameter_scores["consciousness"] == 0
    assert result.parameter_scores["temperature"] == 0


def test_news2_single_red_trigger():
    # Patient is normal except HR = 135 bpm (individual score of 3)
    vitals = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-RED-TRIG",
        heart_rate=135.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=16.0,
        spo2=98.0,
        temperature_c=36.8,
        on_supplemental_oxygen=False,
        consciousness=ConsciousnessLevel.ALERT,
    )

    result = NEWS2Calculator.calculate(vitals, is_copd_spo2_scale2=False)

    assert result.total_score == 3
    assert result.has_extreme_score is True
    # In RCP NEWS2, a single red score of 3 triggers LOW_MEDIUM clinical escalation
    assert result.risk_level == "LOW_MEDIUM"
    assert result.parameter_scores["heart_rate"] == 3


def test_news2_medium_and_high_risk():
    # Medium Risk (score 5-6)
    # HR: 115 (2), RR: 22 (2), Temp: 38.3 (1) = 5 points
    vitals_med = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-MED",
        heart_rate=115.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=22.0,
        spo2=98.0,
        temperature_c=38.3,
        on_supplemental_oxygen=False,
        consciousness=ConsciousnessLevel.ALERT,
    )
    res_med = NEWS2Calculator.calculate(vitals_med)
    assert res_med.total_score == 5
    assert res_med.risk_level == "MEDIUM"

    # High Risk (score >= 7)
    # HR: 125 (2), SBP: 85 (3), RR: 26 (3), SpO2: 91 on Air (3) = 11 points
    vitals_high = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-HIGH",
        heart_rate=125.0,
        systolic_bp=85.0,
        diastolic_bp=50.0,
        respiratory_rate=26.0,
        spo2=91.0,
        temperature_c=38.5,
        on_supplemental_oxygen=False,
        consciousness=ConsciousnessLevel.ALERT,
    )
    res_high = NEWS2Calculator.calculate(vitals_high)
    assert res_high.total_score == 12  # 2 + 3 + 3 + 3 + 1 = 12
    assert res_high.risk_level == "HIGH"


def test_news2_copd_scale2():
    # Patient with hypercapnic respiratory failure
    # In Scale 2, SpO2 88-92% is target range (0 points)
    vitals_copd_normal = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-COPD-01",
        heart_rate=80.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=18.0,
        spo2=90.0,
        temperature_c=37.0,
        on_supplemental_oxygen=False,
    )
    res1 = NEWS2Calculator.calculate(vitals_copd_normal, is_copd_spo2_scale2=True)
    assert res1.parameter_scores["spo2"] == 0

    # Hyperoxemia risk: SpO2 >= 97% ON OXYGEN in Scale 2 scores 3 points
    vitals_copd_hyperox = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-COPD-02",
        heart_rate=80.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=18.0,
        spo2=98.0,
        temperature_c=37.0,
        on_supplemental_oxygen=True,
    )
    res2 = NEWS2Calculator.calculate(vitals_copd_hyperox, is_copd_spo2_scale2=True)
    assert res2.parameter_scores["spo2"] == 3
    assert res2.parameter_scores["air_or_oxygen"] == 2


def test_qsofa_scoring():
    # 0 criteria met
    v0 = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-Q0",
        heart_rate=75.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=16.0,
        spo2=98.0,
        temperature_c=37.0,
        consciousness=ConsciousnessLevel.ALERT,
        gcs=15,
    )
    q0 = QSOFACalculator.calculate(v0)
    assert q0.total_score == 0
    assert q0.is_positive is False
    assert q0.clinical_risk == "LOW"

    # 1 criteria met (RR >= 22)
    v1 = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-Q1",
        heart_rate=75.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=24.0,
        spo2=98.0,
        temperature_c=37.0,
        consciousness=ConsciousnessLevel.ALERT,
        gcs=15,
    )
    q1 = QSOFACalculator.calculate(v1)
    assert q1.total_score == 1
    assert q1.is_positive is False

    # 2 criteria met (RR >= 22 and SBP <= 100) -> qSOFA Positive
    v2 = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-Q2",
        heart_rate=110.0,
        systolic_bp=95.0,
        diastolic_bp=60.0,
        respiratory_rate=25.0,
        spo2=95.0,
        temperature_c=38.5,
        consciousness=ConsciousnessLevel.ALERT,
        gcs=15,
    )
    q2 = QSOFACalculator.calculate(v2)
    assert q2.total_score == 2
    assert q2.is_positive is True
    assert q2.clinical_risk == "HIGH"

    # 3 criteria met (RR >= 22, SBP <= 100, altered mentation)
    v3 = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-Q3",
        heart_rate=125.0,
        systolic_bp=88.0,
        diastolic_bp=55.0,
        respiratory_rate=28.0,
        spo2=93.0,
        temperature_c=38.8,
        consciousness=ConsciousnessLevel.VOICE,
        gcs=13,
    )
    q3 = QSOFACalculator.calculate(v3)
    assert q3.total_score == 3
    assert q3.is_positive is True
    assert q3.clinical_risk == "HIGH"
