"""Agent finding and evidence bundle data models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    """Clinical alert severity classification."""
    NORMAL = "NORMAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceBundle(BaseModel):
    """Auditable evidence packet supporting an agent's clinical observation.

    Constraint: AI agents must explain evidence rather than invent medical conclusions.
    Every bundle must provide concrete values, baselines, and guideline citations.
    """
    metric: str = Field(..., description="Observed clinical parameter name, e.g. 'Heart Rate' or 'Serum Lactate'")
    observed_value: Any = Field(..., description="Actual recorded parameter value")
    baseline_value: Optional[Any] = Field(default=None, description="Patient-specific baseline value for delta evaluation")
    delta_change: Optional[str] = Field(default=None, description="Quantitative shift (e.g., '+48 bpm over 6 hours')")
    reference_range: Optional[str] = Field(default=None, description="Established physiological normal range (e.g., '60-100 bpm')")
    clinical_guideline: str = Field(..., description="Referenced evidence protocol (e.g. 'Royal College of Physicians NEWS2')")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp of observation")


class AgentFinding(BaseModel):
    """Structured observation emitted by a domain specialist agent."""
    finding_id: str = Field(..., description="Unique alphanumeric identifier (e.g. 'FND-VTL-001')")
    agent_name: str = Field(..., description="Emitting agent identifier, e.g. 'VitalsMonitoringAgent'")
    patient_id: str = Field(..., description="Patient ID under observation")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp of finding generation")
    severity: FindingSeverity = Field(..., description="Assessed clinical severity level")
    category: str = Field(..., description="Clinical system category (e.g. 'HEMODYNAMICS', 'RESPIRATORY', 'METABOLIC')")
    title: str = Field(..., description="Concise, non-diagnostic finding headline")
    evidence: EvidenceBundle = Field(..., description="Structured supporting evidence bundle")
    narrative_summary: str = Field(
        ...,
        description="Objective clinical narrative describing the deviation and trajectory without diagnostic assertions."
    )
