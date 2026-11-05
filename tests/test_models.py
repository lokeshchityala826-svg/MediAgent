"""Unit tests for MediAgent data models and validation constraints."""

from datetime import datetime
import pytest
from pydantic import ValidationError

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
    ConsciousnessLevel,
    OxygenDevice,
    LabItem,
    LabResult,
    LabPanelType,
)
from mediagent.models.finding import (
    FindingSeverity,
    EvidenceBundle,
    AgentFinding,
)
from mediagent.models.proposal import (
    ProposalUrgency,
    ActionState,
    ProposedIntervention,
    ClinicalProposal,
    DoctorAction,
)


def test_patient_model_creation():
    patient = Patient(
        patient_id="PAT-TEST-01",
        name="John Doe",
        age=65,
        gender=PatientGender.MALE,
        admission_id="ADM-100",
        admission_reason="Community acquired pneumonia",
        code_status=CodeStatus.FULL_CODE,
        room_bed="Ward 3A - Bed 4",
        baseline_vitals=BaselineVitals(
            heart_rate=75.0,
            systolic_bp=125.0,
            diastolic_bp=80.0,
            respiratory_rate=16.0,
            spo2=96.0,
            temperature_c=37.0,
        ),
        comorbidities=[
            Comorbidity(code="J18.9", description="Pneumonia, unspecified", severity="MODERATE")
        ],
        medications=[
            Medication(name="Azithromycin", dosage="500 mg", route="Oral", frequency="Daily")
        ],
        allergies=["Penicillin"],
    )

    assert patient.patient_id == "PAT-TEST-01"
    assert patient.age == 65
    assert patient.gender == PatientGender.MALE
    assert len(patient.comorbidities) == 1
    assert patient.comorbidities[0].code == "J18.9"
    assert patient.baseline_vitals.spo2 == 96.0


def test_vitals_map_auto_calculation():
    # If MAP is omitted: (2 * DBP + SBP) / 3 = (2 * 80 + 120) / 3 = 93.33 -> 93.3
    vitals = VitalSigns(
        timestamp=datetime.now(),
        patient_id="PAT-TEST-01",
        heart_rate=80.0,
        systolic_bp=120.0,
        diastolic_bp=80.0,
        respiratory_rate=16.0,
        spo2=98.0,
        temperature_c=36.7,
        on_supplemental_oxygen=False,
    )
    assert vitals.mean_arterial_pressure == 93.3


def test_vitals_boundary_validation():
    with pytest.raises(ValidationError):
        # SpO2 cannot be > 100%
        VitalSigns(
            timestamp=datetime.now(),
            patient_id="PAT-TEST-01",
            heart_rate=80.0,
            systolic_bp=120.0,
            diastolic_bp=80.0,
            respiratory_rate=16.0,
            spo2=105.0,
            temperature_c=36.7,
        )


def test_lab_item_abnormality_flagging():
    # Value inside normal limits
    normal_item = LabItem(
        test_code="WBC",
        test_name="White Blood Cells",
        value=7.5,
        unit="x10^3/uL",
        ref_range_low=4.5,
        ref_range_high=11.0,
    )
    assert normal_item.is_abnormal is False

    # Value above normal limits
    abnormal_item = LabItem(
        test_code="LACTATE",
        test_name="Serum Lactate",
        value=3.2,
        unit="mmol/L",
        ref_range_low=0.5,
        ref_range_high=2.0,
    )
    assert abnormal_item.is_abnormal is True


def test_agent_finding_with_evidence():
    evidence = EvidenceBundle(
        metric="Heart Rate",
        observed_value=125.0,
        baseline_value=72.0,
        delta_change="+53 bpm (+73.6%) over 4 hours",
        reference_range="51-90 bpm (NEWS2)",
        clinical_guideline="RCP NEWS2 Parameter Trigger: Tachycardia >= 111 bpm scores 2 points",
    )

    finding = AgentFinding(
        finding_id="FND-001",
        agent_name="VitalsMonitoringAgent",
        patient_id="PAT-TEST-01",
        severity=FindingSeverity.HIGH,
        category="HEMODYNAMICS",
        title="Sustained Sinus Tachycardia",
        evidence=evidence,
        narrative_summary="Patient heart rate escalated from baseline 72 bpm to 125 bpm over 4 hours.",
    )

    assert finding.finding_id == "FND-001"
    assert finding.severity == FindingSeverity.HIGH
    assert finding.evidence.observed_value == 125.0


def test_clinical_proposal_and_doctor_action():
    proposal = ClinicalProposal(
        proposal_id="PROP-001",
        patient_id="PAT-TEST-01",
        composite_risk_score=8.0,
        scoring_system="NEWS2",
        primary_concern="Hemodynamic and respiratory deterioration",
        contributing_agent_findings=["FND-001"],
        recommended_actions=[
            ProposedIntervention(
                intervention_type="BEDSIDE_EVALUATION",
                description="Urgent physician bedside assessment within 15 minutes",
                rationale="NEWS2 score >= 7 represents high clinical risk category",
            )
        ],
        urgency=ProposalUrgency.STAT,
        status=ActionState.PENDING_REVIEW,
    )

    assert proposal.status == ActionState.PENDING_REVIEW
    assert proposal.composite_risk_score == 8.0

    doctor_action = DoctorAction(
        action_id="ACT-001",
        proposal_id="PROP-001",
        patient_id="PAT-TEST-01",
        action=ActionState.APPROVED,
        physician_id="MD-789",
        physician_name="Dr. Sarah Chen",
        clinical_notes="Assessing patient now; ordered STAT repeat lactate and chest radiograph.",
    )

    assert doctor_action.action == ActionState.APPROVED
    assert doctor_action.physician_id == "MD-789"
