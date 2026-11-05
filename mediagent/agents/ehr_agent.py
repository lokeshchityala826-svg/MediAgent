"""EHR Analysis Agent: Baseline condition appraisal, medication safety checks, and advance directive governance."""

import uuid
from datetime import datetime
from typing import List, Optional

from mediagent.agents.base_agent import BaseClinicalAgent
from mediagent.models.finding import AgentFinding, EvidenceBundle, FindingSeverity
from mediagent.models.patient import CodeStatus


class EHRAnalysisAgent(BaseClinicalAgent):
    """Parses static Electronic Health Record data (comorbidities, active medications, admission history, and code status)."""

    def __init__(self, repo, audit_logger=None) -> None:
        super().__init__(agent_name="EHRAnalysisAgent", repo=repo, audit_logger=audit_logger)

    def analyze_patient(
        self,
        patient_id: str,
        current_time: Optional[datetime] = None,
    ) -> List[AgentFinding]:
        """Evaluate patient EHR baseline context and advance directives."""
        patient = self.repo.get_patient(patient_id)
        if not patient:
            return []

        ts = current_time or datetime.now()
        findings: List[AgentFinding] = []

        # 1. Chronic Respiratory Disease & SpO2 Scale 2 Mandate
        has_copd = any("COPD" in c.description.upper() or c.code.startswith("J44") for c in patient.comorbidities)
        if has_copd or patient.baseline_vitals.is_copd_spo2_scale2:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-EHR-COPD-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=ts,
                        severity=FindingSeverity.MEDIUM,
                        category="CHRONIC_PULMONARY_CONTEXT",
                        title="Baseline Hypercapnic Risk (Target SpO2: 88-92%)",
                        evidence=EvidenceBundle(
                            metric="COPD / Chronic Respiratory Failure History",
                            observed_value="Documented COPD / Hypercapnic Risk",
                            baseline_value="Resting SpO2 Target: 88-92%",
                            delta_change=None,
                            reference_range="88 - 92% (NEWS2 Scale 2)",
                            clinical_guideline="British Thoracic Society (BTS) Guideline for Oxygen Use: Oxygen prescription should target 88-92% in patients at risk of hypercapnic respiratory failure.",
                            timestamp=ts,
                        ),
                        narrative_summary=(
                            f"Patient has documented {patient.comorbidities[0].description if patient.comorbidities else 'COPD'}. "
                            "Uncontrolled oxygen supplementation risks depressing respiratory drive and aggravating CO2 retention."
                        ),
                    )
                )
            )

        # 2. Post-Surgical Sepsis / Peritonitis Vulnerability
        adm_reason = patient.admission_reason.lower()
        if "colectomy" in adm_reason or "diverticulitis" in adm_reason or "bowel" in adm_reason or "post-op" in adm_reason:
            active_abx = [m.name for m in patient.medications if any(k in m.name.lower() for k in ["cef", "cillin", "azole", "mycin", "penem", "floxacin"])]
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-EHR-SURG-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=ts,
                        severity=FindingSeverity.MEDIUM,
                        category="POST_SURGICAL_VULNERABILITY",
                        title="High-Risk Post-Operative Status (Intra-Abdominal Infection Susceptibility)",
                        evidence=EvidenceBundle(
                            metric="Surgical History / Antimicrobial Regimen",
                            observed_value=patient.admission_reason,
                            baseline_value="Elective / Urgent Abdominal Surgery",
                            delta_change=None,
                            reference_range="Normal post-operative recovery",
                            clinical_guideline="SIS/IDSA Guidelines: Major abdominal surgery confers elevated risk of anastomotic leak, intra-abdominal abscess, or sepsis.",
                            timestamp=ts,
                        ),
                        narrative_summary=(
                            f"Patient admitted for '{patient.admission_reason}'. Active antimicrobial coverage: {active_abx or 'None noted'}. "
                            "Clinical signs of systemic inflammation require prompt evaluation for surgical source."
                        ),
                    )
                )
            )

        # 3. Advance Directives & Code Status Constraints
        if patient.code_status in [CodeStatus.DNR_DNI, CodeStatus.DNI_ONLY]:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-EHR-CODE-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=ts,
                        severity=FindingSeverity.HIGH,
                        category="ADVANCE_DIRECTIVE_GOVERNANCE",
                        title=f"Advance Directive Active: {patient.code_status.value}",
                        evidence=EvidenceBundle(
                            metric="Patient Resuscitation Preferences",
                            observed_value=patient.code_status.value,
                            baseline_value=patient.code_status.value,
                            delta_change=None,
                            reference_range="Documented legally binding directive",
                            clinical_guideline="AMA Code of Medical Ethics: Patient advance directives and DNR/DNI orders must be honored during clinical escalation.",
                            timestamp=ts,
                        ),
                        narrative_summary=(
                            f"Patient has documented {patient.code_status.value} status. "
                            "In the event of acute respiratory failure or arrest, invasive endotracheal intubation is prohibited. "
                            "Non-invasive ventilation (NIV/BiPAP) and aggressive medical optimization remain permissible if consistent with patient goals."
                        ),
                    )
                )
            )

        return findings
