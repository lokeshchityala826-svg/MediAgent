"""Thin integration layer for the existing MediAgent backend.

This frontend deliberately contains no backend package, patient fixtures, agent
implementations, or clinical scoring logic. Configure MEDIAGENT_BACKEND_PATH if
the backend is not located beside this frontend folder.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

FRONTEND_ROOT = Path(__file__).resolve().parent


def _resolve_backend_root() -> Path:
    configured = os.environ.get("MEDIAGENT_BACKEND_PATH", "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            FRONTEND_ROOT.parent / "MediAgent_Backend",
            FRONTEND_ROOT.parent / "MediAgent",
            FRONTEND_ROOT.parents[1],
            FRONTEND_ROOT.parent,
            FRONTEND_ROOT,
        ]
    )
    for candidate in candidates:
        root = candidate.resolve()
        if (root / "mediagent" / "__init__.py").is_file():
            return root
    searched = "\n".join(str(p.resolve()) for p in candidates)
    raise FileNotFoundError(
        "Could not locate the existing MediAgent backend package. Set the "
        "MEDIAGENT_BACKEND_PATH environment variable to the backend folder. "
        f"\nSearched:\n{searched}"
    )


BACKEND_ROOT = _resolve_backend_root()
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Import only the existing backend services. These classes are not reimplemented.
from mediagent.storage.db import DatabaseManager  # noqa: E402
from mediagent.storage.patient_repo import PatientRepository  # noqa: E402
from mediagent.storage.audit_logger import AuditLogger  # noqa: E402
from mediagent.coordinator.coordinator import MultiAgentCoordinator  # noqa: E402
from mediagent.workflow.approval_engine import ApprovalEngine  # noqa: E402


@st.cache_resource(show_spinner=False)
def get_services():
    """Return shared backend service instances bound to the backend's DB file."""
    db_path = BACKEND_ROOT / "data" / "mediagent.db"
    if not db_path.is_file():
        raise FileNotFoundError(
            f"Backend database not found: {db_path}. Run the backend's own "
            "database initialization/seed workflow; the frontend will not create demo records."
        )

    db = DatabaseManager(db_path=db_path)
    repo = PatientRepository(db)
    audit = AuditLogger(db)
    return {
        "db": db,
        "repo": repo,
        "audit": audit,
        "coordinator": MultiAgentCoordinator(repo=repo, audit_logger=audit),
        "approval": ApprovalEngine(repo=repo, audit_logger=audit),
        "backend_root": BACKEND_ROOT,
        "database_path": db_path,
    }

