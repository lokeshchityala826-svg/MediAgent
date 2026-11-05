"""SQLite database initialization and connection management."""

import os
import sqlite3
from pathlib import Path
from typing import Optional


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "mediagent.db"


class DatabaseManager:
    """Manages SQLite connection lifecycle and schema migrations."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create and return a configured SQLite connection with foreign keys and row factory."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def initialize_schema(self) -> None:
        """Create database tables and performance indexes if they do not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Patients Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                patient_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                admission_id TEXT NOT NULL,
                admission_date TEXT NOT NULL,
                admission_reason TEXT NOT NULL,
                code_status TEXT NOT NULL,
                room_bed TEXT NOT NULL,
                baseline_vitals_json TEXT NOT NULL,
                comorbidities_json TEXT NOT NULL,
                medications_json TEXT NOT NULL,
                allergies_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """)

            # 2. Vitals Telemetry Stream Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS vitals_stream (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                heart_rate REAL NOT NULL,
                systolic_bp REAL NOT NULL,
                diastolic_bp REAL NOT NULL,
                mean_arterial_pressure REAL NOT NULL,
                respiratory_rate REAL NOT NULL,
                spo2 REAL NOT NULL,
                temperature_c REAL NOT NULL,
                on_supplemental_oxygen INTEGER NOT NULL,
                oxygen_flow_lpm REAL NOT NULL DEFAULT 0.0,
                oxygen_device TEXT NOT NULL,
                consciousness TEXT NOT NULL,
                gcs INTEGER NOT NULL DEFAULT 15,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
            );
            """)

            # 3. Laboratory Results Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS lab_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lab_id TEXT UNIQUE NOT NULL,
                patient_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                panel_type TEXT NOT NULL,
                items_json TEXT NOT NULL,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
            );
            """)

            # 4. Agent Findings Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_findings (
                finding_id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                narrative_summary TEXT NOT NULL,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
            );
            """)

            # 5. Clinical Proposals Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS clinical_proposals (
                proposal_id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                composite_risk_score REAL NOT NULL,
                scoring_system TEXT NOT NULL,
                primary_concern TEXT NOT NULL,
                contributing_findings_json TEXT NOT NULL,
                recommended_actions_json TEXT NOT NULL,
                urgency TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
            );
            """)

            # 6. Doctor Actions (Sign-Off Ledger) Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS doctor_actions (
                action_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                action TEXT NOT NULL,
                physician_id TEXT NOT NULL,
                physician_name TEXT NOT NULL,
                reviewed_at TEXT NOT NULL,
                clinical_notes TEXT,
                modified_actions_json TEXT,
                FOREIGN KEY (proposal_id) REFERENCES clinical_proposals(proposal_id) ON DELETE CASCADE,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
            );
            """)

            # 7. Immutable Audit Trail Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                patient_id TEXT,
                payload_json TEXT NOT NULL,
                checksum TEXT NOT NULL
            );
            """)

            # Performance Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vitals_patient_time ON vitals_stream (patient_id, timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_labs_patient_time ON lab_results (patient_id, timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_patient_time ON agent_findings (patient_id, timestamp);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_proposals_patient_time ON clinical_proposals (patient_id, generated_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_patient_time ON audit_trail (patient_id, timestamp);")

            conn.commit()

    def reset_database(self) -> None:
        """Drop and recreate all tables for testing and fresh demo setup."""
        if self.db_path.exists():
            try:
                os.remove(self.db_path)
            except OSError:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    tables = ["doctor_actions", "clinical_proposals", "agent_findings", "lab_results", "vitals_stream", "audit_trail", "patients"]
                    for t in tables:
                        cursor.execute(f"DROP TABLE IF EXISTS {t};")
                    conn.commit()
        self.initialize_schema()
