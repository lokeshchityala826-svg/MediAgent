"""Unit tests for SQLite database management, repository queries, and audit logs."""

import tempfile
from datetime import datetime
from pathlib import Path

from mediagent.models.patient import (
    Patient,
    PatientGender,
    CodeStatus,
    BaselineVitals,
    Comorbidity,
    Medication,
)
from mediagent.models.telemetry import (
    VitalSigns,
    LabResult,
    LabItem,
    LabPanelType,
    ConsciousnessLevel,
    OxygenDevice,
)
from mediagent.models.finding import AgentFinding, EvidenceBundle, FindingSeverity
from mediagent.models.proposal import ClinicalProposal, DoctorAction, ProposedIntervention, ActionState, ProposalUrgency
from mediagent.storage.db import DatabaseManager
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


def create_test_db():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_mediagent.db"
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_schema()
    repo = PatientRepository(db_manager)
    audit = AuditLogger(db_manager)
    return db_manager, repo, audit


def test_patient_upsert_and_retrieve():
    _, repo, _ = create_test_db()

    patient = Patient(
        patient_id="PAT-DB-01",
        name="Alice Smith",
        age=52,
        gender=PatientGender.FEMALE,
        admission_id="ADM-2026-99",
        admission_reason="Post-op cholecystectomy",
        code_status=CodeStatus.FULL_CODE,
        room_bed="Ward 2A - Bed 05",
        baseline_vitals=BaselineVitals(
            heart_rate=70.0,
            systolic_bp=118.0,
            diastolic_bp=75.0,
            respiratory_rate=14.0,
            spo2=99.0,
            temperature_c=36.7,
        ),
        comorbidities=[
            Comorbidity(code="K80.0", description="Calculus of gallbladder with acute cholecystitis", severity="MILD")
        ],
        medications=[
            Medication(name="Cefazolin", dosage="1 g", route="IV", frequency="Q8H")
        ],
        allergies=["Latex"],
    )

    repo.upsert_patient(patient)
    retrieved = repo.get_patient("PAT-DB-01")

    assert retrieved is not None
    assert retrieved.name == "Alice Smith"
    assert retrieved.age == 52
    assert retrieved.gender == PatientGender.FEMALE
    assert len(retrieved.comorbidities) == 1
    assert retrieved.comorbidities[0].code == "K80.0"
    assert retrieved.medications[0].name == "Cefazolin"
    assert retrieved.allergies == ["Latex"]


def test_vitals_stream_storage_and_query():
    _, repo, _ = create_test_db()

    # Create dummy patient first for foreign key integrity
    patient = Patient(
        patient_id="PAT-VTL-01",
        name="Bob Jones",
        age=45,
        gender=PatientGender.MALE,
        admission_id="ADM-101",
        admission_reason="Observation",
        room_bed="Room 1",
    )
    repo.upsert_patient(patient)

    v1 = VitalSigns(
        timestamp=datetime(2026, 11, 5, 8, 0),
        patient_id="PAT-VTL-01",
        heart_rate=72.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=16.0,
        spo2=98.0,
        temperature_c=36.8,
    )
    v2 = VitalSigns(
        timestamp=datetime(2026, 11, 5, 9, 0),
        patient_id="PAT-VTL-01",
        heart_rate=88.0,
        systolic_bp=114.0,
        diastolic_bp=74.0,
        respiratory_rate=18.0,
        spo2=97.0,
        temperature_c=37.2,
    )

    count = repo.insert_vitals_batch([v1, v2])
    assert count == 2

    stream = repo.get_vitals_stream("PAT-VTL-01")
    assert len(stream) == 2
    assert stream[0].heart_rate == 72.0
    assert stream[1].heart_rate == 88.0
    assert stream[1].timestamp > stream[0].timestamp


def test_lab_results_storage_and_query():
    _, repo, _ = create_test_db()

    patient = Patient(
        patient_id="PAT-LAB-01",
        name="Charlie Brown",
        age=60,
        gender=PatientGender.MALE,
        admission_id="ADM-102",
        admission_reason="Sepsis workup",
        room_bed="Room 2",
    )
    repo.upsert_patient(patient)

    lab = LabResult(
        lab_id="LAB-101",
        patient_id="PAT-LAB-01",
        timestamp=datetime(2026, 11, 5, 10, 0),
        panel_type=LabPanelType.LACTATE,
        items=[
            LabItem(
                test_code="LACTATE",
                test_name="Serum Lactate",
                value=3.4,
                unit="mmol/L",
                ref_range_low=0.5,
                ref_range_high=2.0,
                is_abnormal=True,
            )
        ],
    )

    repo.insert_lab_result(lab)
    labs = repo.get_lab_results("PAT-LAB-01")

    assert len(labs) == 1
    assert labs[0].lab_id == "LAB-101"
    assert labs[0].items[0].value == 3.4
    assert labs[0].items[0].is_abnormal is True


def test_doctor_action_and_proposal_flow():
    _, repo, _ = create_test_db()

    patient = Patient(
        patient_id="PAT-ACT-01",
        name="Diana Prince",
        age=34,
        gender=PatientGender.FEMALE,
        admission_id="ADM-103",
        admission_reason="Post-op monitor",
        room_bed="Room 3",
    )
    repo.upsert_patient(patient)

    proposal = ClinicalProposal(
        proposal_id="PROP-101",
        patient_id="PAT-ACT-01",
        composite_risk_score=7.0,
        scoring_system="NEWS2",
        primary_concern="Escalating respiratory rate and tachycardia",
        contributing_agent_findings=[],
        recommended_actions=[
            ProposedIntervention(
                intervention_type="BEDSIDE_EVALUATION",
                description="Prompt physician evaluation",
                rationale="NEWS2 score 7 is high risk",
            )
        ],
        urgency=ProposalUrgency.URGENT,
        status=ActionState.PENDING_REVIEW,
    )
    repo.insert_clinical_proposal(proposal)

    # Doctor approves proposal
    action = DoctorAction(
        action_id="ACT-101",
        proposal_id="PROP-101",
        patient_id="PAT-ACT-01",
        action=ActionState.APPROVED,
        physician_id="MD-123",
        physician_name="Dr. Gregory House",
        clinical_notes="Patient reviewed at bedside; initiating fluid bolus.",
    )
    repo.record_doctor_action(action)

    # Check updated proposal state
    proposals = repo.get_clinical_proposals("PAT-ACT-01")
    assert len(proposals) == 1
    assert proposals[0].status == ActionState.APPROVED


def test_audit_logger_integrity():
    _, _, audit = create_test_db()

    event_id = audit.log_event(
        event_type="TEST_CRITICAL_ALERT",
        actor_type="AGENT",
        actor_id="VitalsMonitoringAgent",
        patient_id="PAT-001",
        payload={"metric": "Heart Rate", "value": 140.0},
    )

    assert event_id.startswith("EVT-")
    assert audit.verify_event_integrity(event_id) is True

    # Check recent events
    recent = audit.get_recent_events(limit=10)
    assert len(recent) == 1
    assert recent[0]["event_id"] == event_id
    assert recent[0]["payload"]["value"] == 140.0
