"""Unit tests for ApprovalEngine and Human-in-the-Loop physician review workflows."""

import tempfile
from pathlib import Path
import pytest

from mediagent.coordinator.coordinator import MultiAgentCoordinator
from mediagent.workflow.approval_engine import ApprovalEngine
from mediagent.simulation.scenarios import get_scenario_by_id
from mediagent.simulation.generator import SyntheticTrajectoryGenerator
from mediagent.models.proposal import ActionState
from mediagent.storage.db import DatabaseManager
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


def setup_test_workflow():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_wf.db"
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_schema()
    repo = PatientRepository(db_manager)
    audit = AuditLogger(db_manager)
    coordinator = MultiAgentCoordinator(repo=repo, audit_logger=audit)
    engine = ApprovalEngine(repo=repo, audit_logger=audit)
    generator = SyntheticTrajectoryGenerator(random_seed=12)
    return repo, audit, coordinator, engine, generator


def test_doctor_approval_flow():
    repo, audit, coordinator, engine, generator = setup_test_workflow()
    scenario = get_scenario_by_id("SCN-SEPSIS-02")
    generator.seed_scenario_to_db(scenario, repo, audit, interval_minutes=60)

    # 1. Generate Proposal
    proposal = coordinator.coordinate_patient("PAT-002")
    assert proposal.status == ActionState.PENDING_REVIEW

    # Verify in pending queue
    pending = engine.get_pending_proposals("PAT-002")
    assert len(pending) == 1
    assert pending[0].proposal_id == proposal.proposal_id

    # 2. Doctor Approves Proposal
    action = engine.approve_proposal(
        proposal_id=proposal.proposal_id,
        physician_id="MD-101",
        physician_name="Dr. Marcus Welby",
        clinical_notes="Concur with septic shock risk. 30 mL/kg fluid challenge initiated.",
    )

    assert action.action == ActionState.APPROVED
    assert action.physician_id == "MD-101"

    # 3. Verify Proposal State updated
    updated_prop = repo.get_proposal_by_id(proposal.proposal_id)
    assert updated_prop.status == ActionState.APPROVED

    # Pending queue should now be empty
    assert len(engine.get_pending_proposals("PAT-002")) == 0

    # 4. Verify Audit Integrity
    recent_events = audit.get_recent_events(limit=5)
    app_event = next(e for e in recent_events if e["event_type"] == "DOCTOR_PROPOSAL_APPROVED")
    assert app_event["actor_id"] == "MD-101"
    assert audit.verify_event_integrity(app_event["event_id"]) is True


def test_doctor_modification_flow():
    repo, audit, coordinator, engine, generator = setup_test_workflow()
    scenario = get_scenario_by_id("SCN-RESP-03")
    generator.seed_scenario_to_db(scenario, repo, audit, interval_minutes=60)

    proposal = coordinator.coordinate_patient("PAT-003")

    # Doctor modifies proposal
    custom_actions = [
        "Initiate BiPAP trial (IPAP 12, EPAP 4) immediately",
        "Perform bedside point-of-care lung ultrasound",
        "Hold morning beta-blockers",
    ]
    notes = "Adjusted NIV settings and added bedside POCUS evaluation."

    action = engine.modify_proposal(
        proposal_id=proposal.proposal_id,
        physician_id="MD-202",
        physician_name="Dr. Allison Cameron",
        modified_actions=custom_actions,
        clinical_notes=notes,
    )

    assert action.action == ActionState.MODIFIED
    assert action.modified_actions == custom_actions

    updated_prop = repo.get_proposal_by_id(proposal.proposal_id)
    assert updated_prop.status == ActionState.MODIFIED

    # Check validation when modified actions or notes are missing
    with pytest.raises(ValueError):
        engine.modify_proposal(
            proposal_id=proposal.proposal_id,
            physician_id="MD-202",
            physician_name="Dr. Allison Cameron",
            modified_actions=[],
            clinical_notes="Empty actions should fail",
        )


def test_doctor_dismissal_flow():
    repo, audit, coordinator, engine, generator = setup_test_workflow()
    scenario = get_scenario_by_id("SCN-STABLE-01")
    generator.seed_scenario_to_db(scenario, repo, audit, interval_minutes=60)

    proposal = coordinator.coordinate_patient("PAT-001")

    # Doctor dismisses proposal
    action = engine.dismiss_proposal(
        proposal_id=proposal.proposal_id,
        physician_id="MD-303",
        physician_name="Dr. Lisa Cuddy",
        clinical_notes="Patient is resting comfortably; surgical wound clean, ambulating well. No escalation required.",
    )

    assert action.action == ActionState.DISMISSED
    updated_prop = repo.get_proposal_by_id(proposal.proposal_id)
    assert updated_prop.status == ActionState.DISMISSED

    # Check validation when dismissal note is empty
    with pytest.raises(ValueError):
        engine.dismiss_proposal(
            proposal_id=proposal.proposal_id,
            physician_id="MD-303",
            physician_name="Dr. Lisa Cuddy",
            clinical_notes="",
        )
