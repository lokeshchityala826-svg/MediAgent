"""Approval Engine: Human-in-the-Loop physician review, modification, and sign-off governance."""

import uuid
from datetime import datetime
from typing import List, Optional

from mediagent.models.proposal import (
    ClinicalProposal,
    DoctorAction,
    ActionState,
)
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


class ApprovalEngine:
    """Enforces strict Human-in-the-Loop governance for clinical decision support proposals."""

    def __init__(self, repo: PatientRepository, audit_logger: Optional[AuditLogger] = None) -> None:
        self.repo = repo
        self.audit_logger = audit_logger

    def get_pending_proposals(self, patient_id: Optional[str] = None) -> List[ClinicalProposal]:
        """Fetch all proposals awaiting physician review."""
        if patient_id:
            all_proposals = self.repo.get_clinical_proposals(patient_id)
        else:
            all_proposals = self.repo.list_all_proposals()
        return [p for p in all_proposals if p.status == ActionState.PENDING_REVIEW]

    def approve_proposal(
        self,
        proposal_id: str,
        physician_id: str,
        physician_name: str,
        clinical_notes: Optional[str] = None,
    ) -> DoctorAction:
        """Physician approves the proposed clinical interventions without modification.

        Args:
            proposal_id: Target proposal ID
            physician_id: Identifier of the signing physician (e.g., 'MD-4091')
            physician_name: Formal name of the reviewing physician
            clinical_notes: Optional documentation rationale

        Returns:
            The recorded DoctorAction object
        """
        proposal = self.repo.get_proposal_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal '{proposal_id}' does not exist.")

        action = DoctorAction(
            action_id=f"ACT-APP-{uuid.uuid4().hex[:8].upper()}",
            proposal_id=proposal_id,
            patient_id=proposal.patient_id,
            action=ActionState.APPROVED,
            physician_id=physician_id,
            physician_name=physician_name,
            reviewed_at=datetime.now(),
            clinical_notes=clinical_notes or "Physician concurred with all recommended interventions.",
            modified_actions=None,
        )

        self.repo.record_doctor_action(action)

        if self.audit_logger:
            self.audit_logger.log_event(
                event_type="DOCTOR_PROPOSAL_APPROVED",
                actor_type="PHYSICIAN",
                actor_id=physician_id,
                patient_id=proposal.patient_id,
                payload={
                    "action_id": action.action_id,
                    "proposal_id": proposal_id,
                    "physician_name": physician_name,
                    "action": ActionState.APPROVED.value,
                    "notes": action.clinical_notes,
                },
            )

        return action

    def modify_proposal(
        self,
        proposal_id: str,
        physician_id: str,
        physician_name: str,
        modified_actions: List[str],
        clinical_notes: str,
    ) -> DoctorAction:
        """Physician modifies the recommended interventions before sign-off.

        Args:
            proposal_id: Target proposal ID
            physician_id: Identifier of the signing physician
            physician_name: Formal name of the reviewing physician
            modified_actions: Specific customized action items selected by physician
            clinical_notes: Mandatory justification for overriding or adjusting recommendations

        Returns:
            The recorded DoctorAction object
        """
        proposal = self.repo.get_proposal_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal '{proposal_id}' does not exist.")

        if not modified_actions:
            raise ValueError("Modified actions list cannot be empty when choosing MODIFIED.")

        if not clinical_notes or not clinical_notes.strip():
            raise ValueError("Clinical notes are required when overriding or modifying recommended actions.")

        action = DoctorAction(
            action_id=f"ACT-MOD-{uuid.uuid4().hex[:8].upper()}",
            proposal_id=proposal_id,
            patient_id=proposal.patient_id,
            action=ActionState.MODIFIED,
            physician_id=physician_id,
            physician_name=physician_name,
            reviewed_at=datetime.now(),
            clinical_notes=clinical_notes,
            modified_actions=modified_actions,
        )

        self.repo.record_doctor_action(action)

        if self.audit_logger:
            self.audit_logger.log_event(
                event_type="DOCTOR_PROPOSAL_MODIFIED",
                actor_type="PHYSICIAN",
                actor_id=physician_id,
                patient_id=proposal.patient_id,
                payload={
                    "action_id": action.action_id,
                    "proposal_id": proposal_id,
                    "physician_name": physician_name,
                    "action": ActionState.MODIFIED.value,
                    "modified_actions": modified_actions,
                    "notes": clinical_notes,
                },
            )

        return action

    def dismiss_proposal(
        self,
        proposal_id: str,
        physician_id: str,
        physician_name: str,
        clinical_notes: str,
    ) -> DoctorAction:
        """Physician dismisses the proposal as clinically non-indicated or artifactual.

        Args:
            proposal_id: Target proposal ID
            physician_id: Identifier of the signing physician
            physician_name: Formal name of the reviewing physician
            clinical_notes: Mandatory rationale explaining dismissal (e.g. baseline chronic status, patient ambulating)

        Returns:
            The recorded DoctorAction object
        """
        proposal = self.repo.get_proposal_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal '{proposal_id}' does not exist.")

        if not clinical_notes or not clinical_notes.strip():
            raise ValueError("Clinical justification note is required to dismiss an alert.")

        action = DoctorAction(
            action_id=f"ACT-DIS-{uuid.uuid4().hex[:8].upper()}",
            proposal_id=proposal_id,
            patient_id=proposal.patient_id,
            action=ActionState.DISMISSED,
            physician_id=physician_id,
            physician_name=physician_name,
            reviewed_at=datetime.now(),
            clinical_notes=clinical_notes,
            modified_actions=None,
        )

        self.repo.record_doctor_action(action)

        if self.audit_logger:
            self.audit_logger.log_event(
                event_type="DOCTOR_PROPOSAL_DISMISSED",
                actor_type="PHYSICIAN",
                actor_id=physician_id,
                patient_id=proposal.patient_id,
                payload={
                    "action_id": action.action_id,
                    "proposal_id": proposal_id,
                    "physician_name": physician_name,
                    "action": ActionState.DISMISSED.value,
                    "dismissal_reason": clinical_notes,
                },
            )

        return action
