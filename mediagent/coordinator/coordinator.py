"""Multi-Agent Coordinator: Cross-domain evidence triangulation and clinical proposal generation."""

import uuid
from datetime import datetime
from typing import List, Optional

from mediagent.agents.vitals_agent import VitalsMonitoringAgent
from mediagent.agents.lab_agent import LaboratoryAnalysisAgent
from mediagent.agents.ehr_agent import EHRAnalysisAgent
from mediagent.engine.news2 import NEWS2Calculator
from mediagent.models.finding import AgentFinding, FindingSeverity
from mediagent.models.proposal import (
    ClinicalProposal,
    ProposedIntervention,
    ProposalUrgency,
    ActionState,
)
from mediagent.models.patient import CodeStatus
from mediagent.storage.patient_repo import PatientRepository
from mediagent.storage.audit_logger import AuditLogger


class MultiAgentCoordinator:
    """Orchestrates specialized domain agents, resolves cross-system signals, and generates explainable review proposals."""

    def __init__(self, repo: PatientRepository, audit_logger: Optional[AuditLogger] = None) -> None:
        self.repo = repo
        self.audit_logger = audit_logger
        self.vitals_agent = VitalsMonitoringAgent(repo=repo, audit_logger=audit_logger)
        self.lab_agent = LaboratoryAnalysisAgent(repo=repo, audit_logger=audit_logger)
        self.ehr_agent = EHRAnalysisAgent(repo=repo, audit_logger=audit_logger)

    def coordinate_patient(
        self,
        patient_id: str,
        current_time: Optional[datetime] = None,
    ) -> ClinicalProposal:
        """Run all specialized agents, triangulate evidence across domains, and synthesize a ClinicalProposal.

        Args:
            patient_id: Target patient identifier
            current_time: Optional cutoff timestamp for point-in-time deliberation

        Returns:
            ClinicalProposal ready for human physician review
        """
        patient = self.repo.get_patient(patient_id)
        if not patient:
            raise ValueError(f"Patient with ID '{patient_id}' not found.")

        # 1. Gather findings from all 3 domain agents
        vitals_findings = self.vitals_agent.analyze_patient(patient_id, current_time=current_time)
        lab_findings = self.lab_agent.analyze_patient(patient_id, current_time=current_time)
        ehr_findings = self.ehr_agent.analyze_patient(patient_id, current_time=current_time)

        all_findings = vitals_findings + lab_findings + ehr_findings
        finding_ids = [f.finding_id for f in all_findings]

        # 2. Extract key signals for clinical triangulation
        has_critical_news = any("Critical NEWS2" in f.title for f in vitals_findings)
        has_medium_news = any("Medium Clinical Risk NEWS2" in f.title for f in vitals_findings)
        has_hypotension = any("Hypotension" in f.title for f in vitals_findings)
        has_qsofa_pos = any("Positive Bedside qSOFA" in f.title for f in vitals_findings)
        has_tachypnea = any("Tachypnea" in f.title for f in vitals_findings)
        has_o2_escalated = any("Escalated Respiratory Support" in f.title for f in vitals_findings)

        has_critical_lactate = any("Critical Serum Lactate" in f.title for f in lab_findings)
        has_elevated_lactate = any("Elevated Serum Lactate" in f.title for f in lab_findings)
        has_leukocytosis = any("Leukocytosis" in f.title for f in lab_findings)
        has_aki = any("Acute Kidney Injury" in f.title for f in lab_findings)
        has_abg_acidosis = any("Acute Acidemia" in f.title for f in lab_findings)

        has_copd = any("Baseline Hypercapnic Risk" in f.title for f in ehr_findings)
        is_dni = patient.code_status in [CodeStatus.DNR_DNI, CodeStatus.DNI_ONLY]

        # Determine composite score based on latest vitals
        vitals_stream = self.repo.get_vitals_stream(patient_id)
        if current_time:
            filtered_v = [v for v in vitals_stream if v.timestamp <= current_time]
        else:
            filtered_v = vitals_stream

        latest_vitals = filtered_v[-1] if filtered_v else None
        base_news = 0
        if latest_vitals:
            base_news = NEWS2Calculator.calculate(
                latest_vitals,
                is_copd_spo2_scale2=patient.baseline_vitals.is_copd_spo2_scale2,
            ).total_score

        # 3. Cross-Domain Triangulation & Protocol Matching

        # PATTERN A: Sepsis / Septic Shock Progression
        # Triangulation: Hemodynamic/Vitals collapse + Metabolic Dysoxia / Leukocytosis + Surgical background
        if (has_critical_lactate or has_elevated_lactate) and (has_qsofa_pos or has_hypotension or has_critical_news):
            primary_concern = (
                "High Clinical Suspicion of Sepsis-Induced Shock with Acute Tissue Hypoperfusion"
            )
            composite_score = max(float(base_news), 9.0)
            scoring_system = "NEWS2 + Surviving Sepsis Campaign 2021 Criteria"
            urgency = ProposalUrgency.STAT

            interventions = [
                ProposedIntervention(
                    intervention_type="BEDSIDE_EVALUATION",
                    description="Immediate physician bedside evaluation by Attending or Rapid Response Team within 15 minutes.",
                    rationale="Bedside qSOFA criteria met and/or severe hypotension indicates high risk of acute clinical decompensation.",
                ),
                ProposedIntervention(
                    intervention_type="REPEAT_LAB",
                    description="Order STAT repeat serum lactate and blood gas in 2 hours to assess clearance; obtain blood cultures prior to antibiotic escalation.",
                    rationale=f"Elevated serum lactate demonstrates anaerobic metabolism requiring surveillance of resuscitation adequacy.",
                ),
                ProposedIntervention(
                    intervention_type="FLUID_RESUSCITATION",
                    description="Assess fluid responsiveness (e.g. passive leg raise or bedside echocardiography); consider balanced crystalloids per protocol.",
                    rationale=f"Hypotension and elevated lactate warrant hemodynamic volume optimization to preserve organ perfusion.",
                ),
                ProposedIntervention(
                    intervention_type="SURGICAL_INFECTION_REVIEW",
                    description="Review active antimicrobial coverage and assess surgical site for potential anastomotic or deep infection source.",
                    rationale="Patient history of major abdominal surgery represents potential anatomical origin for acute sepsis.",
                ),
            ]

        # PATTERN B: Acute Decompensated Respiratory Failure
        # Triangulation: Tachypnea/Hypoxemia + ABG Acidemia/Hypercapnia + COPD/Advance Directive Context
        elif (has_abg_acidosis or (has_tachypnea and has_o2_escalated)) and (has_copd or has_critical_news or has_medium_news):
            primary_concern = (
                "Acute Hypercapnic and Hypoxemic Respiratory Decompensation in Chronic Lung Disease"
            )
            composite_score = max(float(base_news), 8.0)
            scoring_system = "NEWS2 + BTS Acute Respiratory Failure Protocol"
            urgency = ProposalUrgency.STAT if has_abg_acidosis else ProposalUrgency.URGENT

            dni_note = (
                " Note: Patient has documented DNR/DNI status; mechanical endotracheal intubation is legally contraindicated."
                if is_dni else ""
            )

            interventions = [
                ProposedIntervention(
                    intervention_type="BEDSIDE_EVALUATION",
                    description=f"Urgent pulmonary / critical care review within 30 minutes.{dni_note}",
                    rationale="Progressive tachypnea and gas exchange impairment indicate impending respiratory muscle exhaustion.",
                ),
                ProposedIntervention(
                    intervention_type="NON_INVASIVE_VENTILATION",
                    description="Evaluate indication for Non-Invasive Positive Pressure Ventilation (BiPAP/NIV) trial.",
                    rationale="First-line therapy for acute hypercapnic respiratory acidosis in COPD; complies with DNI directive.",
                ),
                ProposedIntervention(
                    intervention_type="OXYGEN_TITRATION",
                    description="Carefully titrate FiO2 to maintain SpO2 strictly between 88-92% (NEWS2 Scale 2).",
                    rationale="Hyperoxemia blunts hypoxic ventilatory drive in chronic carbon dioxide retainers.",
                ),
                ProposedIntervention(
                    intervention_type="REPEAT_LAB",
                    description="Repeat Arterial Blood Gas (ABG) within 1 hour post-intervention to assess PaCO2 and pH trajectory.",
                    rationale="Monitors resolution of acute respiratory acidosis.",
                ),
            ]

        # PATTERN C: Moderate Hemodynamic or Vitals Deterioration (Early Warning Trigger)
        elif has_medium_news or has_critical_news or has_aki:
            primary_concern = "Multi-System Physiological Instability / Escalating Early Warning Score"
            composite_score = float(base_news)
            scoring_system = "NEWS2 National Early Warning Standard"
            urgency = ProposalUrgency.URGENT

            interventions = [
                ProposedIntervention(
                    intervention_type="BEDSIDE_EVALUATION",
                    description="Urgent review by ward physician or acute care clinical team within 1 hour.",
                    rationale=f"NEWS2 score of {base_news} crosses medium/high clinical escalation threshold.",
                ),
                ProposedIntervention(
                    intervention_type="INCREASE_MONITORING",
                    description="Increase vital signs monitoring frequency to hourly until stabilized.",
                    rationale="Detects rapid trajectory changes early before cardiac or respiratory arrest.",
                ),
                ProposedIntervention(
                    intervention_type="ORDER_LAB",
                    description="Order basic metabolic panel and complete blood count to screen for occult infection or renal injury.",
                    rationale="Investigates underlying physiological trigger for vital sign deviation.",
                ),
            ]

        # PATTERN D: Stable Ward Patient
        else:
            primary_concern = "Hemodynamically Stable Post-Operative Course"
            composite_score = float(base_news)
            scoring_system = "NEWS2 National Early Warning Standard"
            urgency = ProposalUrgency.ROUTINE

            interventions = [
                ProposedIntervention(
                    intervention_type="ROUTINE_OBSERVATION",
                    description="Continue routine ward observations (minimum 12-hourly) and standard post-operative care.",
                    rationale="Patient vital signs and laboratory parameters remain within baseline physiological tolerances.",
                )
            ]

        # 4. Create and persist Proposal
        proposal_id = f"PROP-{uuid.uuid4().hex[:8].upper()}"
        gen_time = latest_vitals.timestamp if latest_vitals else (current_time or datetime.now())

        proposal = ClinicalProposal(
            proposal_id=proposal_id,
            patient_id=patient_id,
            generated_at=gen_time,
            composite_risk_score=composite_score,
            scoring_system=scoring_system,
            primary_concern=primary_concern,
            contributing_agent_findings=finding_ids,
            recommended_actions=interventions,
            urgency=urgency,
            status=ActionState.PENDING_REVIEW,
        )

        self.repo.insert_clinical_proposal(proposal)

        if self.audit_logger:
            self.audit_logger.log_event(
                event_type="PROPOSAL_GENERATED",
                actor_type="AGENT",
                actor_id="MultiAgentCoordinator",
                patient_id=patient_id,
                payload={
                    "proposal_id": proposal.proposal_id,
                    "primary_concern": proposal.primary_concern,
                    "urgency": proposal.urgency.value,
                    "composite_score": proposal.composite_risk_score,
                    "actions_count": len(proposal.recommended_actions),
                    "contributing_findings_count": len(finding_ids),
                },
            )

        return proposal
