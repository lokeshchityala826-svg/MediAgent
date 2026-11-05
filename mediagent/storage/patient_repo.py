"""Patient repository for database operations on telemetry, labs, and findings."""

import json
from datetime import datetime
from typing import List, Optional

from mediagent.models.patient import (
    Patient,
    BaselineVitals,
    Comorbidity,
    Medication,
    PatientGender,
    CodeStatus,
)
from mediagent.models.telemetry import (
    VitalSigns,
    LabResult,
    LabItem,
    LabPanelType,
    ConsciousnessLevel,
    OxygenDevice,
)
from mediagent.models.finding import AgentFinding, EvidenceBundle, FindingSeverity
from mediagent.models.proposal import ClinicalProposal, DoctorAction, ProposedIntervention, ActionState, ProposalUrgency
from mediagent.storage.db import DatabaseManager


class PatientRepository:
    """Encapsulates data access patterns for patients and associated telemetry."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    # --- Patient CRUD ---

    def upsert_patient(self, patient: Patient) -> None:
        """Insert or replace a patient demographic record."""
        query = """
        INSERT INTO patients (
            patient_id, name, age, gender, admission_id, admission_date,
            admission_reason, code_status, room_bed, baseline_vitals_json,
            comorbidities_json, medications_json, allergies_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(patient_id) DO UPDATE SET
            name = excluded.name,
            age = excluded.age,
            gender = excluded.gender,
            admission_id = excluded.admission_id,
            admission_date = excluded.admission_date,
            admission_reason = excluded.admission_reason,
            code_status = excluded.code_status,
            room_bed = excluded.room_bed,
            baseline_vitals_json = excluded.baseline_vitals_json,
            comorbidities_json = excluded.comorbidities_json,
            medications_json = excluded.medications_json,
            allergies_json = excluded.allergies_json;
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    patient.patient_id,
                    patient.name,
                    patient.age,
                    patient.gender.value,
                    patient.admission_id,
                    patient.admission_date.isoformat(),
                    patient.admission_reason,
                    patient.code_status.value,
                    patient.room_bed,
                    patient.baseline_vitals.model_dump_json(),
                    json.dumps([c.model_dump() for c in patient.comorbidities]),
                    json.dumps([m.model_dump() for m in patient.medications]),
                    json.dumps(patient.allergies),
                ),
            )
            conn.commit()

    def get_patient(self, patient_id: str) -> Optional[Patient]:
        """Retrieve a patient by ID."""
        query = "SELECT * FROM patients WHERE patient_id = ?;"
        with self.db.get_connection() as conn:
            row = conn.execute(query, (patient_id,)).fetchone()
            if not row:
                return None
            return self._row_to_patient(row)

    def list_patients(self) -> List[Patient]:
        """Retrieve all active patients."""
        query = "SELECT * FROM patients ORDER BY patient_id ASC;"
        with self.db.get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [self._row_to_patient(r) for r in rows]

    def _row_to_patient(self, row) -> Patient:
        baseline_dict = json.loads(row["baseline_vitals_json"])
        comorbidities_raw = json.loads(row["comorbidities_json"])
        medications_raw = json.loads(row["medications_json"])
        allergies_raw = json.loads(row["allergies_json"])

        return Patient(
            patient_id=row["patient_id"],
            name=row["name"],
            age=row["age"],
            gender=PatientGender(row["gender"]),
            admission_id=row["admission_id"],
            admission_date=datetime.fromisoformat(row["admission_date"]),
            admission_reason=row["admission_reason"],
            code_status=CodeStatus(row["code_status"]),
            room_bed=row["room_bed"],
            baseline_vitals=BaselineVitals(**baseline_dict),
            comorbidities=[Comorbidity(**c) for c in comorbidities_raw],
            medications=[Medication(**m) for m in medications_raw],
            allergies=allergies_raw,
        )

    # --- Telemetry Operations ---

    def insert_vitals(self, vitals: VitalSigns) -> None:
        """Insert a single vitals record."""
        query = """
        INSERT INTO vitals_stream (
            patient_id, timestamp, heart_rate, systolic_bp, diastolic_bp,
            mean_arterial_pressure, respiratory_rate, spo2, temperature_c,
            on_supplemental_oxygen, oxygen_flow_lpm, oxygen_device,
            consciousness, gcs
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    vitals.patient_id,
                    vitals.timestamp.isoformat(),
                    vitals.heart_rate,
                    vitals.systolic_bp,
                    vitals.diastolic_bp,
                    vitals.mean_arterial_pressure,
                    vitals.respiratory_rate,
                    vitals.spo2,
                    vitals.temperature_c,
                    1 if vitals.on_supplemental_oxygen else 0,
                    vitals.oxygen_flow_lpm or 0.0,
                    vitals.oxygen_device.value,
                    vitals.consciousness.value,
                    vitals.gcs,
                ),
            )
            conn.commit()

    def insert_vitals_batch(self, vitals_list: List[VitalSigns]) -> int:
        """Bulk insert time-series vitals records."""
        if not vitals_list:
            return 0
        query = """
        INSERT INTO vitals_stream (
            patient_id, timestamp, heart_rate, systolic_bp, diastolic_bp,
            mean_arterial_pressure, respiratory_rate, spo2, temperature_c,
            on_supplemental_oxygen, oxygen_flow_lpm, oxygen_device,
            consciousness, gcs
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = [
            (
                v.patient_id,
                v.timestamp.isoformat(),
                v.heart_rate,
                v.systolic_bp,
                v.diastolic_bp,
                v.mean_arterial_pressure,
                v.respiratory_rate,
                v.spo2,
                v.temperature_c,
                1 if v.on_supplemental_oxygen else 0,
                v.oxygen_flow_lpm or 0.0,
                v.oxygen_device.value,
                v.consciousness.value,
                v.gcs,
            )
            for v in vitals_list
        ]
        with self.db.get_connection() as conn:
            conn.executemany(query, params)
            conn.commit()
        return len(vitals_list)

    def get_vitals_stream(self, patient_id: str, limit: Optional[int] = None) -> List[VitalSigns]:
        """Fetch chronologically ordered vitals for a patient."""
        query = "SELECT * FROM vitals_stream WHERE patient_id = ? ORDER BY timestamp ASC"
        if limit:
            query += f" LIMIT {int(limit)}"
        with self.db.get_connection() as conn:
            rows = conn.execute(query, (patient_id,)).fetchall()
            return [
                VitalSigns(
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    patient_id=r["patient_id"],
                    heart_rate=r["heart_rate"],
                    systolic_bp=r["systolic_bp"],
                    diastolic_bp=r["diastolic_bp"],
                    mean_arterial_pressure=r["mean_arterial_pressure"],
                    respiratory_rate=r["respiratory_rate"],
                    spo2=r["spo2"],
                    temperature_c=r["temperature_c"],
                    on_supplemental_oxygen=bool(r["on_supplemental_oxygen"]),
                    oxygen_flow_lpm=r["oxygen_flow_lpm"],
                    oxygen_device=OxygenDevice(r["oxygen_device"]),
                    consciousness=ConsciousnessLevel(r["consciousness"]),
                    gcs=r["gcs"],
                )
                for r in rows
            ]

    # --- Laboratory Operations ---

    def insert_lab_result(self, lab: LabResult) -> None:
        """Insert a single lab report."""
        query = """
        INSERT INTO lab_results (lab_id, patient_id, timestamp, panel_type, items_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(lab_id) DO UPDATE SET
            timestamp = excluded.timestamp,
            panel_type = excluded.panel_type,
            items_json = excluded.items_json;
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    lab.lab_id,
                    lab.patient_id,
                    lab.timestamp.isoformat(),
                    lab.panel_type.value,
                    json.dumps([item.model_dump() for item in lab.items]),
                ),
            )
            conn.commit()

    def insert_labs_batch(self, labs_list: List[LabResult]) -> int:
        """Bulk insert lab results."""
        for lab in labs_list:
            self.insert_lab_result(lab)
        return len(labs_list)

    def get_lab_results(self, patient_id: str) -> List[LabResult]:
        """Fetch all lab panels for a patient sorted chronologically."""
        query = "SELECT * FROM lab_results WHERE patient_id = ? ORDER BY timestamp ASC;"
        with self.db.get_connection() as conn:
            rows = conn.execute(query, (patient_id,)).fetchall()
            results = []
            for r in rows:
                raw_items = json.loads(r["items_json"])
                results.append(
                    LabResult(
                        lab_id=r["lab_id"],
                        patient_id=r["patient_id"],
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                        panel_type=LabPanelType(r["panel_type"]),
                        items=[LabItem(**item) for item in raw_items],
                    )
                )
            return results

    # --- Agent Findings Operations ---

    def insert_agent_finding(self, finding: AgentFinding) -> None:
        """Store an agent's evidence-backed finding."""
        query = """
        INSERT INTO agent_findings (
            finding_id, agent_name, patient_id, timestamp, severity,
            category, title, evidence_json, narrative_summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(finding_id) DO UPDATE SET
            timestamp = excluded.timestamp,
            severity = excluded.severity,
            evidence_json = excluded.evidence_json,
            narrative_summary = excluded.narrative_summary;
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    finding.finding_id,
                    finding.agent_name,
                    finding.patient_id,
                    finding.timestamp.isoformat(),
                    finding.severity.value,
                    finding.category,
                    finding.title,
                    finding.evidence.model_dump_json(),
                    finding.narrative_summary,
                ),
            )
            conn.commit()

    def get_agent_findings(self, patient_id: str) -> List[AgentFinding]:
        """Retrieve all findings for a patient."""
        query = "SELECT * FROM agent_findings WHERE patient_id = ? ORDER BY timestamp ASC;"
        with self.db.get_connection() as conn:
            rows = conn.execute(query, (patient_id,)).fetchall()
            findings = []
            for r in rows:
                evidence_dict = json.loads(r["evidence_json"])
                if "timestamp" in evidence_dict and isinstance(evidence_dict["timestamp"], str):
                    evidence_dict["timestamp"] = datetime.fromisoformat(evidence_dict["timestamp"])
                findings.append(
                    AgentFinding(
                        finding_id=r["finding_id"],
                        agent_name=r["agent_name"],
                        patient_id=r["patient_id"],
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                        severity=FindingSeverity(r["severity"]),
                        category=r["category"],
                        title=r["title"],
                        evidence=EvidenceBundle(**evidence_dict),
                        narrative_summary=r["narrative_summary"],
                    )
                )
            return findings

    # --- Clinical Proposals & Doctor Actions ---

    def insert_clinical_proposal(self, proposal: ClinicalProposal) -> None:
        """Store a synthesized clinical proposal."""
        query = """
        INSERT INTO clinical_proposals (
            proposal_id, patient_id, generated_at, composite_risk_score,
            scoring_system, primary_concern, contributing_findings_json,
            recommended_actions_json, urgency, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(proposal_id) DO UPDATE SET
            status = excluded.status;
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    proposal.proposal_id,
                    proposal.patient_id,
                    proposal.generated_at.isoformat(),
                    proposal.composite_risk_score,
                    proposal.scoring_system,
                    proposal.primary_concern,
                    json.dumps(proposal.contributing_agent_findings),
                    json.dumps([a.model_dump() for a in proposal.recommended_actions]),
                    proposal.urgency.value,
                    proposal.status.value,
                ),
            )
            conn.commit()

    def get_clinical_proposals(self, patient_id: str) -> List[ClinicalProposal]:
        """Fetch all clinical proposals for a patient."""
        query = "SELECT * FROM clinical_proposals WHERE patient_id = ? ORDER BY generated_at ASC;"
        with self.db.get_connection() as conn:
            rows = conn.execute(query, (patient_id,)).fetchall()
            return [self._row_to_proposal(r) for r in rows]

    def get_proposal_by_id(self, proposal_id: str) -> Optional[ClinicalProposal]:
        """Fetch a specific proposal by ID."""
        query = "SELECT * FROM clinical_proposals WHERE proposal_id = ?;"
        with self.db.get_connection() as conn:
            row = conn.execute(query, (proposal_id,)).fetchone()
            if not row:
                return None
            return self._row_to_proposal(row)

    def list_all_proposals(self) -> List[ClinicalProposal]:
        """Fetch all clinical proposals across all patients."""
        query = "SELECT * FROM clinical_proposals ORDER BY generated_at DESC;"
        with self.db.get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [self._row_to_proposal(r) for r in rows]

    def _row_to_proposal(self, r) -> ClinicalProposal:
        raw_actions = json.loads(r["recommended_actions_json"])
        return ClinicalProposal(
            proposal_id=r["proposal_id"],
            patient_id=r["patient_id"],
            generated_at=datetime.fromisoformat(r["generated_at"]),
            composite_risk_score=r["composite_risk_score"],
            scoring_system=r["scoring_system"],
            primary_concern=r["primary_concern"],
            contributing_agent_findings=json.loads(r["contributing_findings_json"]),
            recommended_actions=[ProposedIntervention(**a) for a in raw_actions],
            urgency=ProposalUrgency(r["urgency"]),
            status=ActionState(r["status"]),
        )

    def get_doctor_actions(self, patient_id: Optional[str] = None) -> List[DoctorAction]:
        """Fetch doctor review actions optionally filtered by patient."""
        query = "SELECT * FROM doctor_actions"
        params = ()
        if patient_id:
            query += " WHERE patient_id = ?"
            params = (patient_id,)
        query += " ORDER BY reviewed_at DESC;"

        with self.db.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            actions = []
            for r in rows:
                mod_actions = json.loads(r["modified_actions_json"]) if r["modified_actions_json"] else None
                actions.append(
                    DoctorAction(
                        action_id=r["action_id"],
                        proposal_id=r["proposal_id"],
                        patient_id=r["patient_id"],
                        action=ActionState(r["action"]),
                        physician_id=r["physician_id"],
                        physician_name=r["physician_name"],
                        reviewed_at=datetime.fromisoformat(r["reviewed_at"]),
                        clinical_notes=r["clinical_notes"],
                        modified_actions=mod_actions,
                    )
                )
            return actions

    def record_doctor_action(self, action: DoctorAction) -> None:
        """Record physician review decision and update proposal status."""
        query_action = """
        INSERT INTO doctor_actions (
            action_id, proposal_id, patient_id, action, physician_id,
            physician_name, reviewed_at, clinical_notes, modified_actions_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        query_update_prop = "UPDATE clinical_proposals SET status = ? WHERE proposal_id = ?;"

        with self.db.get_connection() as conn:
            conn.execute(
                query_action,
                (
                    action.action_id,
                    action.proposal_id,
                    action.patient_id,
                    action.action.value,
                    action.physician_id,
                    action.physician_name,
                    action.reviewed_at.isoformat(),
                    action.clinical_notes,
                    json.dumps(action.modified_actions) if action.modified_actions else None,
                ),
            )
            conn.execute(query_update_prop, (action.action.value, action.proposal_id))
            conn.commit()
