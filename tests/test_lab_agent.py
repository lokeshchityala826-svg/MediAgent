"""Unit tests for LaboratoryAnalysisAgent."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from mediagent.agents.lab_agent import LaboratoryAnalysisAgent
from mediagent.models.patient import Patient, PatientGender
from mediagent.models.telemetry import (
    LabResult,
    LabItem,
    LabPanelType,
)
from mediagent.models.finding import FindingSeverity
from mediagent.storage.db import DatabaseManager
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


def setup_test_agent():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_lab.db"
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_schema()
    repo = PatientRepository(db_manager)
    audit = AuditLogger(db_manager)
    agent = LaboratoryAnalysisAgent(repo=repo, audit_logger=audit)
    return repo, agent


def test_lab_agent_normal_panels():
    repo, agent = setup_test_agent()

    patient = Patient(
        patient_id="PAT-LAB-TEST-01",
        name="Normal Labs Patient",
        age=45,
        gender=PatientGender.MALE,
        admission_id="ADM-L1",
        admission_reason="Elective checkup",
        room_bed="Bed 10",
    )
    repo.upsert_patient(patient)

    lab_cbc = LabResult(
        lab_id="LAB-CBC-01",
        patient_id="PAT-LAB-TEST-01",
        timestamp=datetime.now(),
        panel_type=LabPanelType.CBC,
        items=[
            LabItem(test_code="WBC", test_name="White Blood Cells", value=7.0, unit="x10^3/uL", ref_range_low=4.5, ref_range_high=11.0),
            LabItem(test_code="PLT", test_name="Platelets", value=250.0, unit="x10^3/uL", ref_range_low=150.0, ref_range_high=450.0),
        ],
    )
    repo.insert_lab_result(lab_cbc)

    findings = agent.analyze_patient("PAT-LAB-TEST-01")
    assert len(findings) == 0


def test_lab_agent_sepsis_and_aki():
    repo, agent = setup_test_agent()

    patient = Patient(
        patient_id="PAT-LAB-TEST-02",
        name="Septic Labs Patient",
        age=67,
        gender=PatientGender.FEMALE,
        admission_id="ADM-L2",
        admission_reason="Sepsis evaluation",
        room_bed="Bed 11",
    )
    repo.upsert_patient(patient)

    now = datetime.now()
    # Baseline labs (12 hours ago)
    repo.insert_lab_result(
        LabResult(
            lab_id="LAB-BASE-01",
            patient_id="PAT-LAB-TEST-02",
            timestamp=now - timedelta(hours=12),
            panel_type=LabPanelType.BMP,
            items=[
                LabItem(test_code="CREATININE", test_name="Serum Creatinine", value=0.9, unit="mg/dL", ref_range_low=0.7, ref_range_high=1.2),
            ],
        )
    )
    repo.insert_lab_result(
        LabResult(
            lab_id="LAB-BASE-02",
            patient_id="PAT-LAB-TEST-02",
            timestamp=now - timedelta(hours=12),
            panel_type=LabPanelType.LACTATE,
            items=[
                LabItem(test_code="LACTATE", test_name="Serum Lactate", value=1.2, unit="mmol/L", ref_range_low=0.5, ref_range_high=2.0),
            ],
        )
    )

    # Deteriorated labs (current)
    repo.insert_lab_result(
        LabResult(
            lab_id="LAB-CURR-01",
            patient_id="PAT-LAB-TEST-02",
            timestamp=now,
            panel_type=LabPanelType.LACTATE,
            items=[
                LabItem(test_code="LACTATE", test_name="Serum Lactate", value=4.5, unit="mmol/L", ref_range_low=0.5, ref_range_high=2.0, is_abnormal=True, is_critical=True),
            ],
        )
    )
    repo.insert_lab_result(
        LabResult(
            lab_id="LAB-CURR-02",
            patient_id="PAT-LAB-TEST-02",
            timestamp=now,
            panel_type=LabPanelType.BMP,
            items=[
                LabItem(test_code="CREATININE", test_name="Serum Creatinine", value=2.0, unit="mg/dL", ref_range_low=0.7, ref_range_high=1.2, is_abnormal=True),
            ],
        )
    )
    repo.insert_lab_result(
        LabResult(
            lab_id="LAB-CURR-03",
            patient_id="PAT-LAB-TEST-02",
            timestamp=now,
            panel_type=LabPanelType.CBC,
            items=[
                LabItem(test_code="WBC", test_name="White Blood Cells", value=18.5, unit="x10^3/uL", ref_range_low=4.5, ref_range_high=11.0, is_abnormal=True),
                LabItem(test_code="PLT", test_name="Platelets", value=85.0, unit="x10^3/uL", ref_range_low=150.0, ref_range_high=450.0, is_abnormal=True),
            ],
        )
    )

    findings = agent.analyze_patient("PAT-LAB-TEST-02")
    assert len(findings) == 4

    categories = [f.category for f in findings]
    assert "METABOLIC_PERFUSION" in categories
    assert "RENAL" in categories
    assert "HEMATOLOGY_INFECTION" in categories
    assert "HEMATOLOGY_COAGULATION" in categories

    lactate_f = next(f for f in findings if f.category == "METABOLIC_PERFUSION")
    assert lactate_f.severity == FindingSeverity.CRITICAL
    assert lactate_f.evidence.observed_value == 4.5
    assert "Rose from 1.2 to 4.5" in lactate_f.evidence.delta_change

    aki_f = next(f for f in findings if f.category == "RENAL")
    assert aki_f.severity == FindingSeverity.HIGH
    assert aki_f.evidence.baseline_value == 0.9
    assert "+1.10 mg/dL" in aki_f.evidence.delta_change
    assert "KDIGO" in aki_f.evidence.clinical_guideline


def test_lab_agent_abg_respiratory_acidosis():
    repo, agent = setup_test_agent()

    patient = Patient(
        patient_id="PAT-LAB-TEST-03",
        name="ABG Patient",
        age=73,
        gender=PatientGender.MALE,
        admission_id="ADM-L3",
        admission_reason="Respiratory acidosis",
        room_bed="Bed 12",
    )
    repo.upsert_patient(patient)

    repo.insert_lab_result(
        LabResult(
            lab_id="LAB-ABG-01",
            patient_id="PAT-LAB-TEST-03",
            timestamp=datetime.now(),
            panel_type=LabPanelType.ABG,
            items=[
                LabItem(test_code="PH", test_name="Arterial pH", value=7.22, unit="", ref_range_low=7.35, ref_range_high=7.45, is_abnormal=True, is_critical=True),
                LabItem(test_code="PCO2", test_name="Arterial pCO2", value=70.0, unit="mmHg", ref_range_low=35.0, ref_range_high=45.0, is_abnormal=True, is_critical=True),
            ],
        )
    )

    findings = agent.analyze_patient("PAT-LAB-TEST-03")
    assert len(findings) == 1
    abg_f = findings[0]
    assert abg_f.severity == FindingSeverity.CRITICAL
    assert abg_f.category == "ACID_BASE_RESPIRATORY"
    assert "7.22" in str(abg_f.evidence.observed_value)
    assert "70.0" in str(abg_f.evidence.observed_value)
