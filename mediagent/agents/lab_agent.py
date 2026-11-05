"""Laboratory Analysis Agent: Panel surveillance, delta checking, and critical panic value detection."""

import uuid
from datetime import datetime
from typing import List, Optional

from mediagent.agents.base_agent import BaseClinicalAgent
from mediagent.models.finding import AgentFinding, EvidenceBundle, FindingSeverity
from mediagent.models.telemetry import LabResult, LabItem, LabPanelType


class LaboratoryAnalysisAgent(BaseClinicalAgent):
    """Monitors episodic laboratory results, performs baseline delta checks, and flags panic thresholds."""

    def __init__(self, repo, audit_logger=None) -> None:
        super().__init__(agent_name="LaboratoryAnalysisAgent", repo=repo, audit_logger=audit_logger)

    def analyze_patient(
        self,
        patient_id: str,
        current_time: Optional[datetime] = None,
    ) -> List[AgentFinding]:
        """Examine laboratory panels up to current_time and produce evidence-backed findings."""
        all_labs = self.repo.get_lab_results(patient_id)
        if not all_labs:
            return []

        # Filter by cutoff time if provided
        if current_time:
            labs = [l for l in all_labs if l.timestamp <= current_time]
        else:
            labs = all_labs

        if not labs:
            return []

        findings: List[AgentFinding] = []

        # Flatten items with collection timestamp for temporal delta checking
        analyte_history = {}
        for lab in labs:
            for item in lab.items:
                if item.test_code not in analyte_history:
                    analyte_history[item.test_code] = []
                analyte_history[item.test_code].append((lab.timestamp, item))

        # 1. Serum Lactate (Tissue Hypoperfusion / Shock)
        if "LACTATE" in analyte_history:
            lactate_records = analyte_history["LACTATE"]
            latest_time, latest_lactate = lactate_records[-1]

            if latest_lactate.value >= 4.0:
                delta_str = None
                if len(lactate_records) > 1:
                    initial_val = lactate_records[0][1].value
                    delta_str = f"Rose from {initial_val:.1f} to {latest_lactate.value:.1f} mmol/L"

                findings.append(
                    self.emit_finding(
                        AgentFinding(
                            finding_id=f"FND-LAB-LAC-{uuid.uuid4().hex[:8].upper()}",
                            agent_name=self.agent_name,
                            patient_id=patient_id,
                            timestamp=latest_time,
                            severity=FindingSeverity.CRITICAL,
                            category="METABOLIC_PERFUSION",
                            title=f"Critical Serum Lactate Elevation ({latest_lactate.value:.1f} mmol/L)",
                            evidence=EvidenceBundle(
                                metric="Serum Lactate",
                                observed_value=latest_lactate.value,
                                baseline_value=lactate_records[0][1].value if len(lactate_records) > 1 else None,
                                delta_change=delta_str,
                                reference_range="0.5 - 2.0 mmol/L",
                                clinical_guideline="Surviving Sepsis Campaign: Lactate >= 4.0 mmol/L indicates severe metabolic dysoxia and septic shock.",
                                timestamp=latest_time,
                            ),
                            narrative_summary=(
                                f"Serum lactate has reached a critical value of {latest_lactate.value:.1f} mmol/L, "
                                f"reflecting marked anaerobic metabolism or tissue hypoperfusion."
                            ),
                        )
                    )
                )
            elif latest_lactate.value >= 2.0:
                findings.append(
                    self.emit_finding(
                        AgentFinding(
                            finding_id=f"FND-LAB-LAC-{uuid.uuid4().hex[:8].upper()}",
                            agent_name=self.agent_name,
                            patient_id=patient_id,
                            timestamp=latest_time,
                            severity=FindingSeverity.HIGH,
                            category="METABOLIC_PERFUSION",
                            title=f"Elevated Serum Lactate ({latest_lactate.value:.1f} mmol/L)",
                            evidence=EvidenceBundle(
                                metric="Serum Lactate",
                                observed_value=latest_lactate.value,
                                baseline_value=lactate_records[0][1].value if len(lactate_records) > 1 else None,
                                delta_change=None,
                                reference_range="0.5 - 2.0 mmol/L",
                                clinical_guideline="Surviving Sepsis Campaign: Lactate > 2.0 mmol/L warrants resuscitation protocol assessment.",
                                timestamp=latest_time,
                            ),
                            narrative_summary=f"Serum lactate is elevated at {latest_lactate.value:.1f} mmol/L, indicating cellular stress.",
                        )
                    )
                )

        # 2. Hematology: Leukocytes (WBC) and Platelets
        if "WBC" in analyte_history:
            wbc_records = analyte_history["WBC"]
            latest_time, latest_wbc = wbc_records[-1]

            if latest_wbc.value >= 12.0:
                severity = FindingSeverity.HIGH if latest_wbc.value >= 15.0 else FindingSeverity.MEDIUM
                findings.append(
                    self.emit_finding(
                        AgentFinding(
                            finding_id=f"FND-LAB-WBC-{uuid.uuid4().hex[:8].upper()}",
                            agent_name=self.agent_name,
                            patient_id=patient_id,
                            timestamp=latest_time,
                            severity=severity,
                            category="HEMATOLOGY_INFECTION",
                            title=f"Significant Leukocytosis (WBC {latest_wbc.value:.1f} x10^3/uL)",
                            evidence=EvidenceBundle(
                                metric="White Blood Cell Count",
                                observed_value=latest_wbc.value,
                                baseline_value=wbc_records[0][1].value if len(wbc_records) > 1 else None,
                                delta_change=f"{latest_wbc.value - wbc_records[0][1].value:+.1f} x10^3/uL" if len(wbc_records) > 1 else None,
                                reference_range="4.5 - 11.0 x10^3/uL",
                                clinical_guideline="SIRS Criteria: Leukocytosis > 12.0 x10^3/uL indicates systemic inflammatory or infectious response.",
                                timestamp=latest_time,
                            ),
                            narrative_summary=f"Elevated WBC count of {latest_wbc.value:.1f} x10^3/uL consistent with systemic inflammatory response.",
                        )
                    )
                )

        if "PLT" in analyte_history:
            plt_records = analyte_history["PLT"]
            latest_time, latest_plt = plt_records[-1]

            if latest_plt.value < 100.0:
                severity = FindingSeverity.CRITICAL if latest_plt.value < 50.0 else FindingSeverity.HIGH
                findings.append(
                    self.emit_finding(
                        AgentFinding(
                            finding_id=f"FND-LAB-PLT-{uuid.uuid4().hex[:8].upper()}",
                            agent_name=self.agent_name,
                            patient_id=patient_id,
                            timestamp=latest_time,
                            severity=severity,
                            category="HEMATOLOGY_COAGULATION",
                            title=f"Thrombocytopenia (Platelets {latest_plt.value:.0f} x10^3/uL)",
                            evidence=EvidenceBundle(
                                metric="Platelet Count",
                                observed_value=latest_plt.value,
                                baseline_value=plt_records[0][1].value if len(plt_records) > 1 else None,
                                delta_change=f"{latest_plt.value - plt_records[0][1].value:+.0f} x10^3/uL" if len(plt_records) > 1 else None,
                                reference_range="150 - 450 x10^3/uL",
                                clinical_guideline="SOFA Coagulation Score: Platelets < 100 x10^3/uL defines organ dysfunction.",
                                timestamp=latest_time,
                            ),
                            narrative_summary=(
                                f"Platelet count has decreased to {latest_plt.value:.0f} x10^3/uL, "
                                f"signaling coagulopathy or consumption in severe systemic illness."
                            ),
                        )
                    )
                )

        # 3. Renal Function: Creatinine Delta & KDIGO AKI
        if "CREATININE" in analyte_history:
            cr_records = analyte_history["CREATININE"]
            latest_time, latest_cr = cr_records[-1]

            # Delta check against earliest available creatinine
            baseline_cr = cr_records[0][1].value
            cr_delta = latest_cr.value - baseline_cr
            cr_ratio = latest_cr.value / baseline_cr if baseline_cr > 0 else 1.0

            if cr_delta >= 0.3 or cr_ratio >= 1.5:
                findings.append(
                    self.emit_finding(
                        AgentFinding(
                            finding_id=f"FND-LAB-AKI-{uuid.uuid4().hex[:8].upper()}",
                            agent_name=self.agent_name,
                            patient_id=patient_id,
                            timestamp=latest_time,
                            severity=FindingSeverity.HIGH,
                            category="RENAL",
                            title=f"Acute Kidney Injury Indication (Creatinine {latest_cr.value:.1f} mg/dL)",
                            evidence=EvidenceBundle(
                                metric="Serum Creatinine",
                                observed_value=latest_cr.value,
                                baseline_value=baseline_cr,
                                delta_change=f"{cr_delta:+.2f} mg/dL ({cr_ratio:.2f}x baseline)",
                                reference_range="0.7 - 1.2 mg/dL",
                                clinical_guideline="KDIGO AKI Guideline: Increase in serum creatinine >= 0.3 mg/dL or >= 1.5x baseline within 48h.",
                                timestamp=latest_time,
                            ),
                            narrative_summary=(
                                f"Creatinine escalated from baseline {baseline_cr:.2f} to {latest_cr.value:.2f} mg/dL "
                                f"({cr_delta:+.2f} mg/dL rise), meeting KDIGO Acute Kidney Injury staging criteria."
                            ),
                        )
                    )
                )

        # 4. Arterial Blood Gas (ABG): Acidemia, Hypercapnia, Hypoxemia
        if "PH" in analyte_history and "PCO2" in analyte_history:
            ph_records = analyte_history["PH"]
            pco2_records = analyte_history["PCO2"]
            latest_time, latest_ph = ph_records[-1]
            _, latest_pco2 = pco2_records[-1]

            # Acidemia evaluation
            if latest_ph.value < 7.35:
                severity = FindingSeverity.CRITICAL if latest_ph.value < 7.25 else FindingSeverity.HIGH
                findings.append(
                    self.emit_finding(
                        AgentFinding(
                            finding_id=f"FND-LAB-ABG-{uuid.uuid4().hex[:8].upper()}",
                            agent_name=self.agent_name,
                            patient_id=patient_id,
                            timestamp=latest_time,
                            severity=severity,
                            category="ACID_BASE_RESPIRATORY",
                            title=f"Acute Acidemia on Arterial Blood Gas (pH {latest_ph.value:.2f})",
                            evidence=EvidenceBundle(
                                metric="Arterial pH / pCO2",
                                observed_value=f"pH: {latest_ph.value:.2f}, pCO2: {latest_pco2.value:.1f} mmHg",
                                baseline_value=f"pH: {ph_records[0][1].value:.2f}, pCO2: {pco2_records[0][1].value:.1f} mmHg" if len(ph_records) > 1 else None,
                                delta_change=f"pH {latest_ph.value - ph_records[0][1].value:+.2f}, pCO2 {latest_pco2.value - pco2_records[0][1].value:+.1f} mmHg" if len(ph_records) > 1 else None,
                                reference_range="pH: 7.35 - 7.45, pCO2: 35 - 45 mmHg",
                                clinical_guideline="BTS / ATS Guidelines for Acid-Base Balance: pH < 7.35 with pCO2 > 45 mmHg indicates respiratory acidosis.",
                                timestamp=latest_time,
                            ),
                            narrative_summary=(
                                f"Arterial blood gas confirms acute acidemia (pH {latest_ph.value:.2f}) accompanied by marked "
                                f"carbon dioxide retention (pCO2 {latest_pco2.value:.1f} mmHg)."
                            ),
                        )
                    )
                )

        return findings
