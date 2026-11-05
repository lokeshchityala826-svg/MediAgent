"""Immutable audit logging module with cryptographic integrity hashing."""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from mediagent.storage.db import DatabaseManager


class AuditLogger:
    """Provides tamper-evident, append-only clinical event logging."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    def log_event(
        self,
        event_type: str,
        actor_type: str,
        actor_id: str,
        patient_id: Optional[str],
        payload: Dict[str, Any],
    ) -> str:
        """Record an immutable clinical event into the audit ledger.

        Args:
            event_type: Classification (e.g. 'VITALS_INGESTED', 'AGENT_FINDING_EMITTED', 'DOCTOR_APPROVAL')
            actor_type: Entity executing action ('SYSTEM', 'AGENT', 'PHYSICIAN')
            actor_id: ID of actor ('SIMULATOR', 'VitalsMonitoringAgent', 'MD-4091')
            patient_id: Optional relevant patient identifier
            payload: Structured event metadata

        Returns:
            Unique event ID
        """
        event_id = f"EVT-{uuid.uuid4().hex[:12].upper()}"
        timestamp_str = datetime.now().isoformat()
        payload_json = json.dumps(payload, sort_keys=True, default=str)

        # Cryptographic integrity digest: SHA-256(event_id + timestamp + actor + patient + payload)
        hash_seed = f"{event_id}|{timestamp_str}|{actor_type}:{actor_id}|{patient_id or ''}|{payload_json}"
        checksum = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()

        query = """
        INSERT INTO audit_trail (
            event_id, timestamp, event_type, actor_type, actor_id,
            patient_id, payload_json, checksum
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        with self.db.get_connection() as conn:
            conn.execute(
                query,
                (
                    event_id,
                    timestamp_str,
                    event_type,
                    actor_type,
                    actor_id,
                    patient_id,
                    payload_json,
                    checksum,
                ),
            )
            conn.commit()

        return event_id

    def get_patient_audit_trail(self, patient_id: str) -> List[Dict[str, Any]]:
        """Retrieve complete chronological audit events for a given patient."""
        query = "SELECT * FROM audit_trail WHERE patient_id = ? ORDER BY id ASC;"
        with self.db.get_connection() as conn:
            rows = conn.execute(query, (patient_id,)).fetchall()
            return [self._format_row(r) for r in rows]

    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve the most recent audit events across the platform."""
        query = "SELECT * FROM audit_trail ORDER BY log_id DESC LIMIT ?;"
        with self.db.get_connection() as conn:
            rows = conn.execute(query, (int(limit),)).fetchall()
            return [self._format_row(r) for r in rows]

    def verify_event_integrity(self, event_id: str) -> bool:
        """Validate SHA-256 checksum against stored event data."""
        query = "SELECT * FROM audit_trail WHERE event_id = ?;"
        with self.db.get_connection() as conn:
            row = conn.execute(query, (event_id,)).fetchone()
            if not row:
                return False
            payload_json = row["payload_json"]
            hash_seed = f"{row['event_id']}|{row['timestamp']}|{row['actor_type']}:{row['actor_id']}|{row['patient_id'] or ''}|{payload_json}"
            expected_checksum = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()
            return expected_checksum == row["checksum"]

    def _format_row(self, row) -> Dict[str, Any]:
        return {
            "log_id": row["log_id"],
            "event_id": row["event_id"],
            "timestamp": row["timestamp"],
            "event_type": row["event_type"],
            "actor_type": row["actor_type"],
            "actor_id": row["actor_id"],
            "patient_id": row["patient_id"],
            "payload": json.loads(row["payload_json"]),
            "checksum": row["checksum"],
        }
