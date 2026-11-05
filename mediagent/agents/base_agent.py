"""Abstract base class for all domain-specialist clinical monitoring agents."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from mediagent.models.finding import AgentFinding
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


class BaseClinicalAgent(ABC):
    """Abstract base class providing common persistence, telemetry queries, and audit logging."""

    def __init__(
        self,
        agent_name: str,
        repo: PatientRepository,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.agent_name = agent_name
        self.repo = repo
        self.audit_logger = audit_logger

    @abstractmethod
    def analyze_patient(
        self,
        patient_id: str,
        current_time: Optional[datetime] = None,
    ) -> List[AgentFinding]:
        """Examine patient telemetry up to current_time and return structured evidence-based findings.

        Args:
            patient_id: Target patient identifier
            current_time: Optional timestamp cutoff for historical replay / point-in-time analysis

        Returns:
            List of structured AgentFinding objects
        """
        pass

    def emit_finding(self, finding: AgentFinding) -> AgentFinding:
        """Persist finding to database repository and record in audit trail."""
        self.repo.insert_agent_finding(finding)

        if self.audit_logger:
            self.audit_logger.log_event(
                event_type="AGENT_FINDING_EMITTED",
                actor_type="AGENT",
                actor_id=self.agent_name,
                patient_id=finding.patient_id,
                payload={
                    "finding_id": finding.finding_id,
                    "title": finding.title,
                    "severity": finding.severity.value,
                    "metric": finding.evidence.metric,
                    "observed_value": str(finding.evidence.observed_value),
                    "guideline": finding.evidence.clinical_guideline,
                },
            )

        return finding
