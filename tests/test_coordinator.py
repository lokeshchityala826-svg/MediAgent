"""Unit tests for MultiAgentCoordinator cross-domain evidence triangulation and proposal synthesis."""

import tempfile
from pathlib import Path

from mediagent.coordinator.coordinator import MultiAgentCoordinator
from mediagent.simulation.scenarios import get_scenario_by_id
from mediagent.simulation.generator import SyntheticTrajectoryGenerator
from mediagent.models.proposal import ProposalUrgency, ActionState
from mediagent.storage.db import DatabaseManager
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


def setup_test_coordinator():
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_coord.db"
    db_manager = DatabaseManager(db_path=db_path)
    db_manager.initialize_schema()
    repo = PatientRepository(db_manager)
    audit = AuditLogger(db_manager)
    coordinator = MultiAgentCoordinator(repo=repo, audit_logger=audit)
    generator = SyntheticTrajectoryGenerator(random_seed=42)
    return repo, audit, coordinator, generator


def test_coordinator_stable_scenario():
    repo, audit, coordinator, generator = setup_test_coordinator()
    scenario = get_scenario_by_id("SCN-STABLE-01")

    generator.seed_scenario_to_db(scenario, repo, audit, interval_minutes=60)

    proposal = coordinator.coordinate_patient("PAT-001")

    assert proposal is not None
    assert proposal.patient_id == "PAT-001"
    assert proposal.urgency == ProposalUrgency.ROUTINE
    assert proposal.status == ActionState.PENDING_REVIEW
    assert proposal.composite_risk_score <= 4.0
    assert "Stable" in proposal.primary_concern
    assert len(proposal.recommended_actions) >= 1
    assert proposal.recommended_actions[0].intervention_type == "ROUTINE_OBSERVATION"


def test_coordinator_sepsis_scenario():
    repo, audit, coordinator, generator = setup_test_coordinator()
    scenario = get_scenario_by_id("SCN-SEPSIS-02")

    generator.seed_scenario_to_db(scenario, repo, audit, interval_minutes=60)

    proposal = coordinator.coordinate_patient("PAT-002")

    assert proposal is not None
    assert proposal.patient_id == "PAT-002"
    assert proposal.urgency == ProposalUrgency.STAT
    assert proposal.status == ActionState.PENDING_REVIEW
    assert proposal.composite_risk_score >= 9.0
    assert "Sepsis" in proposal.primary_concern or "Shock" in proposal.primary_concern

    # Triangulation verification: must have contributing findings from multiple agents
    assert len(proposal.contributing_agent_findings) >= 3

    # Check recommended interventions
    action_types = [a.intervention_type for a in proposal.recommended_actions]
    assert "BEDSIDE_EVALUATION" in action_types
    assert "REPEAT_LAB" in action_types
    assert "FLUID_RESUSCITATION" in action_types


def test_coordinator_respiratory_scenario():
    repo, audit, coordinator, generator = setup_test_coordinator()
    scenario = get_scenario_by_id("SCN-RESP-03")

    generator.seed_scenario_to_db(scenario, repo, audit, interval_minutes=60)

    proposal = coordinator.coordinate_patient("PAT-003")

    assert proposal is not None
    assert proposal.patient_id == "PAT-003"
    assert proposal.urgency in [ProposalUrgency.STAT, ProposalUrgency.URGENT]
    assert proposal.status == ActionState.PENDING_REVIEW
    assert "Respiratory" in proposal.primary_concern

    # Interventions must include Non-Invasive Ventilation and Oxygen Titration
    action_types = [a.intervention_type for a in proposal.recommended_actions]
    assert "NON_INVASIVE_VENTILATION" in action_types
    assert "OXYGEN_TITRATION" in action_types

    # DNR/DNI advance directive must be respected in clinical guidance
    bedside_act = next(a for a in proposal.recommended_actions if a.intervention_type == "BEDSIDE_EVALUATION")
    assert "DNR/DNI" in bedside_act.description
