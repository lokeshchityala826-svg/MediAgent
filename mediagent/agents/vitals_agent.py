"""Vitals Monitoring Agent: Real-time telemetry surveillance, trend detection, and NEWS2/qSOFA scoring."""

import uuid
from datetime import datetime
from typing import List, Optional

from mediagent.agents.base_agent import BaseClinicalAgent
from mediagent.engine.news2 import NEWS2Calculator
from mediagent.engine.qsofa import QSOFACalculator
from mediagent.models.finding import AgentFinding, EvidenceBundle, FindingSeverity
from mediagent.models.telemetry import VitalSigns, ConsciousnessLevel, OxygenDevice


class VitalsMonitoringAgent(BaseClinicalAgent):
    """Monitors physiological telemetry streams, evaluates NEWS2 and qSOFA, and identifies deterioration trajectories."""

    def __init__(self, repo, audit_logger=None) -> None:
        super().__init__(agent_name="VitalsMonitoringAgent", repo=repo, audit_logger=audit_logger)

    def analyze_patient(
        self,
        patient_id: str,
        current_time: Optional[datetime] = None,
    ) -> List[AgentFinding]:
        """Examine chronological vitals and produce evidence-backed findings."""
        patient = self.repo.get_patient(patient_id)
        if not patient:
            return []

        all_vitals = self.repo.get_vitals_stream(patient_id)
        if not all_vitals:
            return []

        # Filter by cutoff time if provided
        if current_time:
            stream = [v for v in all_vitals if v.timestamp <= current_time]
        else:
            stream = all_vitals

        if not stream:
            return []

        latest = stream[-1]
        baseline = patient.baseline_vitals
        is_scale_2 = baseline.is_copd_spo2_scale2

        findings: List[AgentFinding] = []

        # 1. Deterministic NEWS2 Evaluation
        news_result = NEWS2Calculator.calculate(latest, is_copd_spo2_scale2=is_scale_2)
        if news_result.total_score >= 7:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-NEWS-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.CRITICAL,
                        category="COMPOSITE_EARLY_WARNING",
                        title=f"Critical NEWS2 Score ({news_result.total_score}/20)",
                        evidence=EvidenceBundle(
                            metric="NEWS2 Total Score",
                            observed_value=news_result.total_score,
                            baseline_value=0,
                            delta_change=f"+{news_result.total_score} points from baseline",
                            reference_range="0-4 (Low Clinical Risk)",
                            clinical_guideline="Royal College of Physicians NEWS2 (2017): Score >= 7 mandates emergency critical care review.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            f"Patient NEWS2 aggregate score has escalated to {news_result.total_score}, placing patient "
                            f"in the HIGH risk category. Parameter breakdown: {news_result.parameter_scores}."
                        ),
                    )
                )
            )
        elif news_result.total_score >= 5:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-NEWS-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.HIGH,
                        category="COMPOSITE_EARLY_WARNING",
                        title=f"Medium Clinical Risk NEWS2 Score ({news_result.total_score}/20)",
                        evidence=EvidenceBundle(
                            metric="NEWS2 Total Score",
                            observed_value=news_result.total_score,
                            baseline_value=0,
                            delta_change=f"+{news_result.total_score} points from baseline",
                            reference_range="0-4 (Low Clinical Risk)",
                            clinical_guideline="Royal College of Physicians NEWS2 (2017): Score 5-6 warrants urgent acute medical review.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            f"Patient NEWS2 score reached {news_result.total_score} (Medium Risk). "
                            f"Urgent bedside medical assessment indicated."
                        ),
                    )
                )
            )
        elif news_result.has_extreme_score:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-RED-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.MEDIUM,
                        category="COMPOSITE_EARLY_WARNING",
                        title="NEWS2 Single Red Parameter Trigger",
                        evidence=EvidenceBundle(
                            metric="NEWS2 Extreme Parameter",
                            observed_value=news_result.total_score,
                            baseline_value=0,
                            delta_change="Single parameter scores 3",
                            reference_range="Scores < 3 per parameter",
                            clinical_guideline="Royal College of Physicians NEWS2: Score of 3 in any single parameter requires urgent nurse assessment.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            "Patient has an individual physiological parameter scoring 3 points despite composite score < 5. "
                            f"Parameter breakdown: {news_result.parameter_scores}."
                        ),
                    )
                )
            )

        # 2. Bedside qSOFA Screening
        qsofa_result = QSOFACalculator.calculate(latest)
        if qsofa_result.is_positive:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-QSOFA-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.HIGH,
                        category="SEPSIS_SCREENING",
                        title=f"Positive Bedside qSOFA ({qsofa_result.total_score}/3)",
                        evidence=EvidenceBundle(
                            metric="qSOFA Score",
                            observed_value=qsofa_result.total_score,
                            baseline_value=0,
                            delta_change=f"{qsofa_result.total_score} criteria met",
                            reference_range="0-1 (Screen Negative)",
                            clinical_guideline=qsofa_result.guideline_statement,
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            f"qSOFA score is positive ({qsofa_result.total_score}/3). "
                            f"Criteria met: {qsofa_result.criteria_met}. Increased risk of poor clinical outcome."
                        ),
                    )
                )
            )

        # 3. Hemodynamic Deterioration & Trend Analysis
        # Check MAP & Hypotension
        map_val = latest.mean_arterial_pressure or (2.0 * latest.diastolic_bp + latest.systolic_bp) / 3.0
        if latest.systolic_bp <= 90.0 or map_val < 65.0:
            sbp_delta = latest.systolic_bp - baseline.systolic_bp
            sbp_pct = (sbp_delta / baseline.systolic_bp) * 100.0
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-BP-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.CRITICAL,
                        category="HEMODYNAMICS",
                        title="Severe Hypotension / End-Organ Hypoperfusion Risk",
                        evidence=EvidenceBundle(
                            metric="Blood Pressure / MAP",
                            observed_value=f"{latest.systolic_bp:.0f}/{latest.diastolic_bp:.0f} (MAP: {map_val:.1f})",
                            baseline_value=f"{baseline.systolic_bp:.0f}/{baseline.diastolic_bp:.0f}",
                            delta_change=f"{sbp_delta:+.1f} mmHg ({sbp_pct:+.1f}%)",
                            reference_range="MAP >= 65 mmHg, SBP 111-219 mmHg",
                            clinical_guideline="Surviving Sepsis Campaign 2021: Target MAP >= 65 mmHg to maintain vital organ perfusion.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            f"Patient Mean Arterial Pressure has fallen to {map_val:.1f} mmHg with SBP {latest.systolic_bp:.0f} mmHg, "
                            f"representing a {abs(sbp_pct):.1f}% decline below baseline."
                        ),
                    )
                )
            )

        # Check Tachycardia & Trend
        hr_delta = latest.heart_rate - baseline.heart_rate
        if latest.heart_rate >= 110.0:
            severity = FindingSeverity.HIGH if latest.heart_rate >= 130.0 else FindingSeverity.MEDIUM
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-HR-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=severity,
                        category="HEMODYNAMICS",
                        title=f"Significant Tachycardia ({latest.heart_rate:.0f} bpm)",
                        evidence=EvidenceBundle(
                            metric="Heart Rate",
                            observed_value=latest.heart_rate,
                            baseline_value=baseline.heart_rate,
                            delta_change=f"{hr_delta:+.1f} bpm ({ (hr_delta/baseline.heart_rate)*100:+.1f}%)",
                            reference_range="51-90 bpm (NEWS2 normal)",
                            clinical_guideline="RCP NEWS2: Heart rate >= 111 bpm scores 2 points; >= 131 scores 3 points.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            f"Heart rate is elevated at {latest.heart_rate:.0f} bpm (baseline: {baseline.heart_rate:.0f} bpm, "
                            f"net increase of {hr_delta:+.0f} bpm)."
                        ),
                    )
                )
            )

        # 4. Respiratory Decompensation & Oxygen Escalation
        rr_delta = latest.respiratory_rate - baseline.respiratory_rate
        if latest.respiratory_rate >= 24.0 or (latest.spo2 <= 91.0 and not is_scale_2) or (latest.spo2 <= 83.0 and is_scale_2):
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-RESP-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.HIGH,
                        category="RESPIRATORY",
                        title="Acute Tachypnea & Hypoxemia",
                        evidence=EvidenceBundle(
                            metric="Respiratory Rate / SpO2",
                            observed_value=f"RR: {latest.respiratory_rate:.0f}/min, SpO2: {latest.spo2:.1f}%",
                            baseline_value=f"RR: {baseline.respiratory_rate:.0f}/min, SpO2: {baseline.spo2:.1f}%",
                            delta_change=f"RR {rr_delta:+.1f}/min, SpO2 {latest.spo2 - baseline.spo2:+.1f}%",
                            reference_range="RR: 12-20/min, SpO2: 96-100% (Scale 1) / 88-92% (Scale 2)",
                            clinical_guideline="British Thoracic Society Guideline for Oxygen Use: Severe hypoxemia or tachypnea >= 24.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            f"Patient demonstrates significant respiratory effort with tachypnea of {latest.respiratory_rate:.0f}/min "
                            f"and SpO2 of {latest.spo2:.1f}% on {latest.oxygen_device.value} ({latest.oxygen_flow_lpm} L/min)."
                        ),
                    )
                )
            )

        # Check oxygen device escalation
        if latest.on_supplemental_oxygen and latest.oxygen_device in [OxygenDevice.VENTURI_MASK, OxygenDevice.NON_REBREATHER, OxygenDevice.HFNC]:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-O2-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.MEDIUM,
                        category="RESPIRATORY",
                        title=f"Escalated Respiratory Support ({latest.oxygen_device.value})",
                        evidence=EvidenceBundle(
                            metric="Oxygen Delivery Device",
                            observed_value=f"{latest.oxygen_device.value} at {latest.oxygen_flow_lpm} L/min",
                            baseline_value="ROOM_AIR" if not baseline.is_copd_spo2_scale2 else "NASAL_CANNULA (2L)",
                            delta_change=f"Escalated to {latest.oxygen_flow_lpm} L/min",
                            reference_range="Room air (FiO2 0.21)",
                            clinical_guideline="BTS Emergency Oxygen Guideline: Escalating FiO2 requirements indicate worsening gas exchange.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            f"Patient oxygen therapy escalated to {latest.oxygen_device.value} delivering {latest.oxygen_flow_lpm} L/min."
                        ),
                    )
                )
            )

        # 5. Temperature Abnormalities (Fever or Late Hypothermia)
        if latest.temperature_c >= 38.3:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-TEMP-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.MEDIUM,
                        category="METABOLIC",
                        title=f"Pyrexia Detected ({latest.temperature_c:.1f}°C)",
                        evidence=EvidenceBundle(
                            metric="Body Temperature",
                            observed_value=latest.temperature_c,
                            baseline_value=baseline.temperature_c,
                            delta_change=f"{latest.temperature_c - baseline.temperature_c:+.1f}°C",
                            reference_range="36.1 - 38.0°C (Normal)",
                            clinical_guideline="SIRS Criteria: Temperature > 38.0°C meets systemic inflammatory response threshold.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=f"Elevated core temperature of {latest.temperature_c:.1f}°C, consistent with pyrexia.",
                    )
                )
            )
        elif latest.temperature_c <= 36.0:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-HYPO-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.HIGH,
                        category="METABOLIC",
                        title=f"Hypothermia Detected ({latest.temperature_c:.1f}°C)",
                        evidence=EvidenceBundle(
                            metric="Body Temperature",
                            observed_value=latest.temperature_c,
                            baseline_value=baseline.temperature_c,
                            delta_change=f"{latest.temperature_c - baseline.temperature_c:+.1f}°C",
                            reference_range="36.1 - 38.0°C (Normal)",
                            clinical_guideline="Sepsis-3 / SIRS: Hypothermia (< 36.0°C) is a marker of impaired thermoregulation in severe sepsis.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=f"Subnormal core temperature of {latest.temperature_c:.1f}°C, concerning for severe infection or shock.",
                    )
                )
            )

        # 6. Altered Consciousness / AVPU
        if latest.consciousness != ConsciousnessLevel.ALERT or latest.gcs < 15:
            findings.append(
                self.emit_finding(
                    AgentFinding(
                        finding_id=f"FND-VTL-CNS-{uuid.uuid4().hex[:8].upper()}",
                        agent_name=self.agent_name,
                        patient_id=patient_id,
                        timestamp=latest.timestamp,
                        severity=FindingSeverity.HIGH,
                        category="NEUROLOGICAL",
                        title=f"Altered Level of Consciousness ({latest.consciousness.value}, GCS {latest.gcs})",
                        evidence=EvidenceBundle(
                            metric="Consciousness (AVPU / GCS)",
                            observed_value=f"{latest.consciousness.value} (GCS {latest.gcs})",
                            baseline_value="ALERT (GCS 15)",
                            delta_change=f"GCS drop of {15 - latest.gcs} points",
                            reference_range="ALERT (GCS 15)",
                            clinical_guideline="RCP NEWS2: Any new deviation from Alert scores 3 points and indicates acute cerebral dysfunction.",
                            timestamp=latest.timestamp,
                        ),
                        narrative_summary=(
                            f"Patient level of responsiveness has altered to {latest.consciousness.value} with Glasgow Coma Scale of {latest.gcs}."
                        ),
                    )
                )
            )

        return findings
