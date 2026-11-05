"""Clinical scenario definitions for synthetic patient generation."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from mediagent.models.patient import (
    Patient,
    BaselineVitals,
    Comorbidity,
    Medication,
    PatientGender,
    CodeStatus,
)


@dataclass
class ScenarioDefinition:
    """Encapsulates a clinical scenario, initial patient profile, and trajectory modifiers."""
    scenario_id: str
    name: str
    description: str
    expected_risk_category: str
    duration_hours: int
    patient: Patient
    vitals_progression_fn: Callable[[float], Dict[str, any]]
    lab_schedule: List[Dict[str, any]]


def _stable_vitals(hour: float) -> Dict[str, any]:
    """Trajectory function for stable post-op patient."""
    return {
        "heart_rate": 72.0,
        "systolic_bp": 122.0,
        "diastolic_bp": 78.0,
        "respiratory_rate": 15.0,
        "spo2": 98.0,
        "temperature_c": 36.8,
        "on_supplemental_oxygen": False,
        "oxygen_flow_lpm": 0.0,
        "oxygen_device": "ROOM_AIR",
        "consciousness": "ALERT",
        "gcs": 15,
    }


def _sepsis_vitals(hour: float) -> Dict[str, any]:
    """Trajectory function for progressive sepsis / septic shock."""
    if hour <= 6.0:
        # Phase 1: Mild tachycardia, low-grade fever
        factor = hour / 6.0
        return {
            "heart_rate": 80.0 + 12.0 * factor,         # 80 -> 92
            "systolic_bp": 122.0 - 6.0 * factor,        # 122 -> 116
            "diastolic_bp": 76.0 - 4.0 * factor,        # 76 -> 72
            "respiratory_rate": 16.0 + 3.0 * factor,    # 16 -> 19
            "spo2": 97.0 - 1.0 * factor,                # 97 -> 96
            "temperature_c": 37.1 + 0.8 * factor,       # 37.1 -> 37.9
            "on_supplemental_oxygen": False,
            "oxygen_flow_lpm": 0.0,
            "oxygen_device": "ROOM_AIR",
            "consciousness": "ALERT",
            "gcs": 15,
        }
    elif hour <= 14.0:
        # Phase 2: Moderate SIRS / early sepsis (fever spike, tachypnea, softening BP)
        factor = (hour - 6.0) / 8.0
        return {
            "heart_rate": 92.0 + 20.0 * factor,         # 92 -> 112
            "systolic_bp": 116.0 - 14.0 * factor,       # 116 -> 102
            "diastolic_bp": 72.0 - 8.0 * factor,        # 72 -> 64
            "respiratory_rate": 19.0 + 5.0 * factor,    # 19 -> 24
            "spo2": 96.0 - 2.0 * factor,                # 96 -> 94
            "temperature_c": 37.9 + 1.1 * factor,       # 37.9 -> 39.0
            "on_supplemental_oxygen": factor > 0.5,
            "oxygen_flow_lpm": 2.0 if factor > 0.5 else 0.0,
            "oxygen_device": "NASAL_CANNULA" if factor > 0.5 else "ROOM_AIR",
            "consciousness": "ALERT",
            "gcs": 15,
        }
    else:
        # Phase 3: Severe sepsis / septic shock (hypotension crash, hypothermia, confusion)
        factor = min(1.0, (hour - 14.0) / 10.0)
        return {
            "heart_rate": 112.0 + 16.0 * factor,        # 112 -> 128
            "systolic_bp": 102.0 - 20.0 * factor,       # 102 -> 82 (Critical shock)
            "diastolic_bp": 64.0 - 16.0 * factor,       # 64 -> 48
            "respiratory_rate": 24.0 + 4.0 * factor,    # 24 -> 28
            "spo2": 94.0 - 3.0 * factor,                # 94 -> 91
            "temperature_c": 39.0 - 3.4 * factor,       # 39.0 -> 35.6 (Hypothermia)
            "on_supplemental_oxygen": True,
            "oxygen_flow_lpm": 4.0,
            "oxygen_device": "NASAL_CANNULA",
            "consciousness": "VOICE" if factor > 0.6 else "ALERT",
            "gcs": 13 if factor > 0.6 else 14,
        }


def _respiratory_vitals(hour: float) -> Dict[str, any]:
    """Trajectory function for acute COPD exacerbation & respiratory decompensation."""
    if hour <= 6.0:
        # Phase 1: Baseline COPD on 2L Nasal Cannula
        return {
            "heart_rate": 84.0,
            "systolic_bp": 130.0,
            "diastolic_bp": 82.0,
            "respiratory_rate": 20.0,
            "spo2": 90.0,                               # Acceptable on Scale 2 (88-92%)
            "temperature_c": 37.3,
            "on_supplemental_oxygen": True,
            "oxygen_flow_lpm": 2.0,
            "oxygen_device": "NASAL_CANNULA",
            "consciousness": "ALERT",
            "gcs": 15,
        }
    elif hour <= 16.0:
        # Phase 2: Hypoxic deterioration, escalating oxygen requirements
        factor = (hour - 6.0) / 10.0
        return {
            "heart_rate": 84.0 + 24.0 * factor,         # 84 -> 108
            "systolic_bp": 130.0 + 18.0 * factor,       # 130 -> 148 (hypertensive stress response)
            "diastolic_bp": 82.0 + 10.0 * factor,       # 82 -> 92
            "respiratory_rate": 20.0 + 10.0 * factor,   # 20 -> 30 (tachypnea)
            "spo2": 90.0 - 7.0 * factor,                # 90 -> 83% (hypoxia)
            "temperature_c": 37.3 + 0.5 * factor,       # 37.3 -> 37.8
            "on_supplemental_oxygen": True,
            "oxygen_flow_lpm": 2.0 + 4.0 * factor,      # 2L -> 6L
            "oxygen_device": "VENTURI_MASK" if factor > 0.6 else "NASAL_CANNULA",
            "consciousness": "ALERT",
            "gcs": 15,
        }
    else:
        # Phase 3: Severe hypercapnic respiratory failure and fatigue
        factor = min(1.0, (hour - 16.0) / 8.0)
        # Respiratory rate paradoxically drops or stays rapid due to diaphragm exhaustion
        rr = 30.0 - 14.0 * factor if factor > 0.5 else 30.0 + 2.0 * factor
        return {
            "heart_rate": 108.0 + 14.0 * factor,        # 108 -> 122
            "systolic_bp": 148.0 - 26.0 * factor,       # 148 -> 122
            "diastolic_bp": 92.0 - 16.0 * factor,       # 92 -> 76
            "respiratory_rate": rr,                     # 32 down to 16 (respiratory fatigue / arrest risk)
            "spo2": 83.0 - 3.0 * factor,                # 83 -> 80% (severe hypoxemia)
            "temperature_c": 37.8,
            "on_supplemental_oxygen": True,
            "oxygen_flow_lpm": 8.0,
            "oxygen_device": "VENTURI_MASK",
            "consciousness": "VOICE" if factor > 0.4 else "ALERT",
            "gcs": 12 if factor > 0.4 else 14,
        }


def get_all_scenarios() -> List[ScenarioDefinition]:
    """Instantiate and return the three approved clinical scenarios."""
    now = datetime.now()

    # Scenario 1: Stable Patient
    patient_1 = Patient(
        patient_id="PAT-001",
        name="James Cole",
        age=58,
        gender=PatientGender.MALE,
        admission_id="ADM-2026-001",
        admission_date=now - timedelta(days=1),
        admission_reason="Post-operative day 1 following elective inguinal hernia repair",
        code_status=CodeStatus.FULL_CODE,
        room_bed="Ward 4B - Bed 12",
        baseline_vitals=BaselineVitals(
            heart_rate=72.0,
            systolic_bp=122.0,
            diastolic_bp=78.0,
            respiratory_rate=15.0,
            spo2=98.0,
            temperature_c=36.8,
            is_copd_spo2_scale2=False,
        ),
        comorbidities=[
            Comorbidity(code="I10", description="Essential hypertension (controlled)", severity="MILD")
        ],
        medications=[
            Medication(name="Amlodipine", dosage="5 mg", route="Oral", frequency="Once daily"),
            Medication(name="Acetaminophen", dosage="1000 mg", route="Oral", frequency="Q6H PRN pain"),
        ],
        allergies=["None known"],
    )

    scenario_1 = ScenarioDefinition(
        scenario_id="SCN-STABLE-01",
        name="Stable Post-Operative Patient",
        description="Hemodynamically stable post-operative course with physiological baseline preservation.",
        expected_risk_category="LOW",
        duration_hours=24,
        patient=patient_1,
        vitals_progression_fn=_stable_vitals,
        lab_schedule=[
            {
                "hour": 6.0,
                "panel": "CBC",
                "items": [
                    {"test_code": "WBC", "test_name": "White Blood Cells", "value": 7.2, "unit": "x10^3/uL", "ref_low": 4.5, "ref_high": 11.0},
                    {"test_code": "HGB", "test_name": "Hemoglobin", "value": 14.5, "unit": "g/dL", "ref_low": 13.5, "ref_high": 17.5},
                    {"test_code": "PLT", "test_name": "Platelets", "value": 240.0, "unit": "x10^3/uL", "ref_low": 150.0, "ref_high": 450.0},
                ],
            },
            {
                "hour": 6.0,
                "panel": "BMP",
                "items": [
                    {"test_code": "SODIUM", "test_name": "Serum Sodium", "value": 140.0, "unit": "mEq/L", "ref_low": 135.0, "ref_high": 145.0},
                    {"test_code": "POTASSIUM", "test_name": "Serum Potassium", "value": 4.2, "unit": "mEq/L", "ref_low": 3.5, "ref_high": 5.0},
                    {"test_code": "CREATININE", "test_name": "Serum Creatinine", "value": 0.9, "unit": "mg/dL", "ref_low": 0.7, "ref_high": 1.2},
                ],
            },
        ],
    )

    # Scenario 2: Sepsis Progression
    patient_2 = Patient(
        patient_id="PAT-002",
        name="Elena Rostova",
        age=67,
        gender=PatientGender.FEMALE,
        admission_id="ADM-2026-002",
        admission_date=now - timedelta(days=2),
        admission_reason="Post-operative day 2 following sigmoid colectomy for diverticulitis",
        code_status=CodeStatus.FULL_CODE,
        room_bed="Step-Down Unit - Bed 04",
        baseline_vitals=BaselineVitals(
            heart_rate=80.0,
            systolic_bp=122.0,
            diastolic_bp=76.0,
            respiratory_rate=16.0,
            spo2=97.0,
            temperature_c=37.1,
            is_copd_spo2_scale2=False,
        ),
        comorbidities=[
            Comorbidity(code="E11.9", description="Type 2 Diabetes Mellitus", severity="MODERATE"),
            Comorbidity(code="K57.92", description="Diverticulitis of large intestine", severity="SEVERE"),
        ],
        medications=[
            Medication(name="Cefepime", dosage="2 g", route="IV", frequency="Q8H"),
            Medication(name="Metronidazole", dosage="500 mg", route="IV", frequency="Q8H"),
        ],
        allergies=["Sulfonamides"],
    )

    scenario_2 = ScenarioDefinition(
        scenario_id="SCN-SEPSIS-02",
        name="Sepsis-Like Acute Deterioration",
        description="Progressive post-surgical bacterial infection advancing from SIRS to septic shock and acute end-organ hypoperfusion.",
        expected_risk_category="CRITICAL",
        duration_hours=24,
        patient=patient_2,
        vitals_progression_fn=_sepsis_vitals,
        lab_schedule=[
            {
                "hour": 4.0,
                "panel": "CBC",
                "items": [
                    {"test_code": "WBC", "test_name": "White Blood Cells", "value": 10.4, "unit": "x10^3/uL", "ref_low": 4.5, "ref_high": 11.0},
                    {"test_code": "PLT", "test_name": "Platelets", "value": 210.0, "unit": "x10^3/uL", "ref_low": 150.0, "ref_high": 450.0},
                ],
            },
            {
                "hour": 4.0,
                "panel": "LACTATE",
                "items": [
                    {"test_code": "LACTATE", "test_name": "Serum Lactate", "value": 1.4, "unit": "mmol/L", "ref_low": 0.5, "ref_high": 2.0},
                ],
            },
            {
                "hour": 12.0,
                "panel": "CBC",
                "items": [
                    {"test_code": "WBC", "test_name": "White Blood Cells", "value": 14.8, "unit": "x10^3/uL", "ref_low": 4.5, "ref_high": 11.0, "is_abnormal": True},
                    {"test_code": "PLT", "test_name": "Platelets", "value": 165.0, "unit": "x10^3/uL", "ref_low": 150.0, "ref_high": 450.0},
                ],
            },
            {
                "hour": 12.0,
                "panel": "LACTATE",
                "items": [
                    {"test_code": "LACTATE", "test_name": "Serum Lactate", "value": 2.5, "unit": "mmol/L", "ref_low": 0.5, "ref_high": 2.0, "is_abnormal": True},
                ],
            },
            {
                "hour": 20.0,
                "panel": "CBC",
                "items": [
                    {"test_code": "WBC", "test_name": "White Blood Cells", "value": 19.6, "unit": "x10^3/uL", "ref_low": 4.5, "ref_high": 11.0, "is_abnormal": True},
                    {"test_code": "PLT", "test_name": "Platelets", "value": 98.0, "unit": "x10^3/uL", "ref_low": 150.0, "ref_high": 450.0, "is_abnormal": True},
                ],
            },
            {
                "hour": 20.0,
                "panel": "LACTATE",
                "items": [
                    {"test_code": "LACTATE", "test_name": "Serum Lactate", "value": 4.4, "unit": "mmol/L", "ref_low": 0.5, "ref_high": 2.0, "is_abnormal": True, "is_critical": True},
                ],
            },
            {
                "hour": 20.0,
                "panel": "BMP",
                "items": [
                    {"test_code": "CREATININE", "test_name": "Serum Creatinine", "value": 1.9, "unit": "mg/dL", "ref_low": 0.7, "ref_high": 1.2, "is_abnormal": True},
                    {"test_code": "POTASSIUM", "test_name": "Serum Potassium", "value": 5.4, "unit": "mEq/L", "ref_low": 3.5, "ref_high": 5.0, "is_abnormal": True},
                ],
            },
        ],
    )

    # Scenario 3: Acute Respiratory Deterioration
    patient_3 = Patient(
        patient_id="PAT-003",
        name="Arthur Pendelton",
        age=73,
        gender=PatientGender.MALE,
        admission_id="ADM-2026-003",
        admission_date=now - timedelta(days=1),
        admission_reason="Acute exacerbation of COPD (AECOPD) and right lower lobe pneumonia",
        code_status=CodeStatus.DNR_DNI,
        room_bed="Pulmonary Ward - Bed 07",
        baseline_vitals=BaselineVitals(
            heart_rate=84.0,
            systolic_bp=130.0,
            diastolic_bp=82.0,
            respiratory_rate=20.0,
            spo2=90.0,
            temperature_c=37.3,
            is_copd_spo2_scale2=True,
        ),
        comorbidities=[
            Comorbidity(code="J44.1", description="COPD with acute exacerbation (GOLD Stage 3)", severity="SEVERE"),
            Comorbidity(code="I25.10", description="Atherosclerotic heart disease", severity="MODERATE"),
        ],
        medications=[
            Medication(name="Tiotropium", dosage="18 mcg", route="Inhalation", frequency="Daily"),
            Medication(name="Prednisone", dosage="40 mg", route="Oral", frequency="Daily"),
            Medication(name="Albuterol-Ipratropium", dosage="3 mL", route="Nebulizer", frequency="Q4H"),
        ],
        allergies=["Codeine"],
    )

    scenario_3 = ScenarioDefinition(
        scenario_id="SCN-RESP-03",
        name="Acute Respiratory Deterioration",
        description="Progressive hypoxic and hypercapnic respiratory failure in a patient with severe baseline COPD.",
        expected_risk_category="HIGH",
        duration_hours=24,
        patient=patient_3,
        vitals_progression_fn=_respiratory_vitals,
        lab_schedule=[
            {
                "hour": 2.0,
                "panel": "ABG",
                "items": [
                    {"test_code": "PH", "test_name": "Arterial pH", "value": 7.36, "unit": "", "ref_low": 7.35, "ref_high": 7.45},
                    {"test_code": "PCO2", "test_name": "Arterial pCO2", "value": 48.0, "unit": "mmHg", "ref_low": 35.0, "ref_high": 45.0, "is_abnormal": True},
                    {"test_code": "PO2", "test_name": "Arterial pO2", "value": 68.0, "unit": "mmHg", "ref_low": 80.0, "ref_high": 100.0, "is_abnormal": True},
                ],
            },
            {
                "hour": 14.0,
                "panel": "ABG",
                "items": [
                    {"test_code": "PH", "test_name": "Arterial pH", "value": 7.29, "unit": "", "ref_low": 7.35, "ref_high": 7.45, "is_abnormal": True},
                    {"test_code": "PCO2", "test_name": "Arterial pCO2", "value": 58.0, "unit": "mmHg", "ref_low": 35.0, "ref_high": 45.0, "is_abnormal": True},
                    {"test_code": "PO2", "test_name": "Arterial pO2", "value": 56.0, "unit": "mmHg", "ref_low": 80.0, "ref_high": 100.0, "is_abnormal": True},
                ],
            },
            {
                "hour": 22.0,
                "panel": "ABG",
                "items": [
                    {"test_code": "PH", "test_name": "Arterial pH", "value": 7.21, "unit": "", "ref_low": 7.35, "ref_high": 7.45, "is_abnormal": True, "is_critical": True},
                    {"test_code": "PCO2", "test_name": "Arterial pCO2", "value": 71.0, "unit": "mmHg", "ref_low": 35.0, "ref_high": 45.0, "is_abnormal": True, "is_critical": True},
                    {"test_code": "PO2", "test_name": "Arterial pO2", "value": 51.0, "unit": "mmHg", "ref_low": 80.0, "ref_high": 100.0, "is_abnormal": True, "is_critical": True},
                ],
            },
        ],
    )

    return [scenario_1, scenario_2, scenario_3]


def get_scenario_by_id(scenario_id: str) -> Optional[ScenarioDefinition]:
    """Find a specific scenario by identifier."""
    for s in get_all_scenarios():
        if s.scenario_id == scenario_id:
            return s
    return None
