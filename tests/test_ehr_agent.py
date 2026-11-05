"""Unit tests for EHRAnalysisAgent."""

import tempfile
from pathlib import Path

from mediagent.agents.ehr_agent import EHRAnalysisAgent
from mediagent.models.patient import (
    Patient,
    PatientGender,
    CodeStatus,
    BaselineVitals,
    Comorbidity,
    Medication,
)
from mediagent.models.finding import FindingSeverity
from mediagent.storage.db import DatabaseManager
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


def setup_test_agent():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_ehr.db"
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_schema()
    repo = PatientRepository(db_manager)
    audit = AuditLogger(db_manager)
    agent = EHRAnalysisAgent(repo=repo, audit_logger=audit)
    return repo, agent


def test_ehr_agent_copd_and_dni_context():
    repo, agent = setup_test_agent()

    patient = Patient(
        patient_id="PAT-EHR-01",
        name="Arthur Pendelton",
        age=73,
        gender=PatientGender.MALE,
        admission_id="ADM-EHR-1",
        admission_reason="AECOPD with pneumonia",
        code_status=CodeStatus.DNR_DNI,
        room_bed="Bed 7",
        baseline_vitals=BaselineVitals(
            is_copd_spo2_scale2=True,
        ),
        comorbidities=[
            Comorbidity(code="J44.1", description="Chronic obstructive pulmonary disease", severity="SEVERE")
        ],
        medications=[
            Medication(name="Tiotropium", dosage="18 mcg", route="Inhalation", frequency="Daily")
        ],
    )
    repo.upsert_patient(patient)

    findings = agent.analyze_patient("PAT-EHR-01")
    assert len(findings) == 2

    titles = [f.title for f in findings]
    assert any("Baseline Hypercapnic Risk" in t for t in titles)
    assert any("Advance Directive Active: DNR_DNI" in t for t in titles)

    dni_finding = next(f for f in findings if "DNR_DNI" in f.title)
    assert dni_finding.severity == FindingSeverity.HIGH
    assert "endotracheal intubation is prohibited" in dni_finding.narrative_summary


def test_ehr_agent_surgical_vulnerability():
    repo, agent = setup_test_agent()

    patient = Patient(
        patient_id="PAT-EHR-02",
        name="Elena Rostova",
        age=67,
        gender=PatientGender.FEMALE,
        admission_id="ADM-EHR-2",
        admission_reason="Post-operative day 2 following sigmoid colectomy for diverticulitis",
        code_status=CodeStatus.FULL_CODE,
        room_bed="Bed 4",
        medications=[
            Medication(name="Cefepime", dosage="2 g", route="IV", frequency="Q8H"),
            Medication(name="Metronidazole", dosage="500 mg", route="IV", frequency="Q8H"),
        ],
    )
    repo.upsert_patient(patient)

    findings = agent.analyze_patient("PAT-EHR-02")
    assert len(findings) == 1
    surg_finding = findings[0]
    assert "High-Risk Post-Operative Status" in surg_finding.title
    assert "Cefepime" in surg_finding.narrative_summary
