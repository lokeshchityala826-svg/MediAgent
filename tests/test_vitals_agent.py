"""Unit tests for VitalsMonitoringAgent."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from mediagent.agents.vitals_agent import VitalsMonitoringAgent
from mediagent.models.patient import (
    Patient,
    PatientGender,
    CodeStatus,
    BaselineVitals,
)
from mediagent.models.telemetry import (
    VitalSigns,
    ConsciousnessLevel,
    OxygenDevice,
)
from mediagent.models.finding import FindingSeverity
from mediagent.storage.db import DatabaseManager
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


def setup_test_agent():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_vitals.db"
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_schema()
    repo = PatientRepository(db_manager)
    audit = AuditLogger(db_manager)
    agent = VitalsMonitoringAgent(repo=repo, audit_logger=audit)
    return repo, agent


def test_vitals_agent_stable_patient():
    repo, agent = setup_test_agent()

    patient = Patient(
        patient_id="PAT-VTL-TEST-01",
        name="Stable Patient",
        age=50,
        gender=PatientGender.MALE,
        admission_id="ADM-01",
        admission_reason="Elective repair",
        room_bed="Bed 1",
        baseline_vitals=BaselineVitals(
            heart_rate=72.0,
            systolic_bp=120.0,
            diastolic_bp=80.0,
            respiratory_rate=15.0,
            spo2=98.0,
            temperature_c=36.8,
        ),
    )
    repo.upsert_patient(patient)

    vitals = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-VTL-TEST-01",
        heart_rate=72.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=15.0,
        spo2=98.0,
        temperature_c=36.8,
        on_supplemental_oxygen=False,
    )
    repo.insert_vitals(vitals)

    findings = agent.analyze_patient("PAT-VTL-TEST-01")
    # For a completely normal patient, no critical or warning findings should be generated
    assert len(findings) == 0


def test_vitals_agent_sepsis_deterioration():
    repo, agent = setup_test_agent()

    patient = Patient(
        patient_id="PAT-VTL-TEST-02",
        name="Septic Patient",
        age=65,
        gender=PatientGender.FEMALE,
        admission_id="ADM-02",
        admission_reason="Post-op infection risk",
        room_bed="Bed 2",
        baseline_vitals=BaselineVitals(
            heart_rate=75.0,
            systolic_bp=120.0,
            diastolic_bp=75.0,
            respiratory_rate=16.0,
            spo2=98.0,
            temperature_c=36.9,
        ),
    )
    repo.upsert_patient(patient)

    # Deteriorated vitals: tachycardia, severe hypotension, tachypnea, hypothermia, somnolence
    vitals = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-VTL-TEST-02",
        heart_rate=128.0,
        systolic_bp=84.0,
        diastolic_bp=48.0,
        respiratory_rate=26.0,
        spo2=92.0,
        temperature_c=35.6,
        on_supplemental_oxygen=True,
        oxygen_flow_lpm=4.0,
        oxygen_device=OxygenDevice.NASAL_CANNULA,
        consciousness=ConsciousnessLevel.VOICE,
        gcs=13,
    )
    repo.insert_vitals(vitals)

    findings = agent.analyze_patient("PAT-VTL-TEST-02")
    assert len(findings) >= 4

    categories = [f.category for f in findings]
    assert "COMPOSITE_EARLY_WARNING" in categories
    assert "SEPSIS_SCREENING" in categories
    assert "HEMODYNAMICS" in categories
    assert "RESPIRATORY" in categories

    # Verify critical severity for high NEWS2 and hypotension
    severities = [f.severity for f in findings]
    assert FindingSeverity.CRITICAL in severities

    # Check evidence bundle integrity
    news_finding = next(f for f in findings if f.category == "COMPOSITE_EARLY_WARNING")
    assert news_finding.evidence.observed_value >= 7
    assert "Royal College of Physicians" in news_finding.evidence.clinical_guideline


def test_vitals_agent_respiratory_failure():
    repo, agent = setup_test_agent()

    patient = Patient(
        patient_id="PAT-VTL-TEST-03",
        name="COPD Patient",
        age=72,
        gender=PatientGender.MALE,
        admission_id="ADM-03",
        admission_reason="AECOPD",
        room_bed="Bed 3",
        baseline_vitals=BaselineVitals(
            heart_rate=80.0,
            systolic_bp=130.0,
            diastolic_bp=80.0,
            respiratory_rate=20.0,
            spo2=90.0,
            temperature_c=37.0,
            is_copd_spo2_scale2=True,
        ),
    )
    repo.upsert_patient(patient)

    # Acute hypoxic failure on Venturi Mask: SpO2 81% on Scale 2, RR 30/min
    vitals = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-VTL-TEST-03",
        heart_rate=112.0,
        systolic_bp=135.0,
        diastolic_bp=85.0,
        respiratory_rate=30.0,
        spo2=81.0,
        temperature_c=37.5,
        on_supplemental_oxygen=True,
        oxygen_flow_lpm=8.0,
        oxygen_device=OxygenDevice.VENTURI_MASK,
        consciousness=ConsciousnessLevel.ALERT,
        gcs=15,
    )
    repo.insert_vitals(vitals)

    findings = agent.analyze_patient("PAT-VTL-TEST-03")
    assert len(findings) >= 2

    resp_findings = [f for f in findings if f.category == "RESPIRATORY"]
    assert len(resp_findings) >= 1
    assert "Acute Tachypnea & Hypoxemia" in [f.title for f in resp_findings]
