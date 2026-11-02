"""
Session Storage Service for Multiple AI Review Board.
Persists review sessions to JSON files in data/saved_reviews/
with strict path traversal protection and rerun lineage tracking.
"""

import json
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.schemas.review_board_schema import ReviewBoardSession


STORAGE_DIR = Path("./data/saved_reviews")
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


class SessionStore:
    """Manages persistent disk storage of review board sessions."""

    @classmethod
    def _ensure_dir(cls) -> Path:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return STORAGE_DIR.resolve()

    @classmethod
    def _validate_session_id(cls, session_id: str) -> Path:
        """Validate session ID format and ensure safe path resolution against directory traversal."""
        if not session_id or not SESSION_ID_PATTERN.match(session_id):
            raise ValueError(f"Invalid session ID format: '{session_id}'. Must be alphanumeric with dashes or underscores.")
        
        base_dir = cls._ensure_dir()
        file_path = (base_dir / f"{session_id}.json").resolve()
        if not file_path.is_relative_to(base_dir):
            raise ValueError(f"Path traversal detected for session ID: '{session_id}'")
        return file_path

    @classmethod
    def save(cls, session: ReviewBoardSession) -> None:
        """Persist session object to disk as JSON."""
        file_path = cls._validate_session_id(session.session_id)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(session.model_dump_json(indent=2))

    @classmethod
    def get(cls, session_id: str) -> Optional[ReviewBoardSession]:
        """Load session by session_id."""
        file_path = cls._validate_session_id(session_id)
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return ReviewBoardSession(**data)

    @classmethod
    def record_rerun_lineage(cls, parent_id: str, child_id: str) -> None:
        """Record that child_id is a rerun of parent_id, preserving both."""
        parent = cls.get(parent_id)
        if parent:
            if child_id not in parent.rerun_history:
                parent.rerun_history.append(child_id)
                cls.save(parent)

    @classmethod
    def list_all(cls) -> List[Dict[str, Any]]:
        """List summary metadata for all saved reviews, most recent first."""
        dir_path = cls._ensure_dir()
        summaries = []
        for file in dir_path.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    idea_data = data.get("idea", {})
                    summaries.append({
                        "session_id": data.get("session_id"),
                        "created_at": data.get("created_at"),
                        "title": idea_data.get("title", "Untitled Startup"),
                        "status": data.get("status", "unknown"),
                        "version": data.get("version", 1),
                        "rerun_of_session_id": data.get("rerun_of_session_id"),
                        "rerun_history": data.get("rerun_history", []),
                        "specialist_count": len(data.get("panel", [])),
                        "failures_encountered": data.get("execution_summary", {}).get("failures_encountered", 0),
                        "total_cost_usd": data.get("execution_summary", {}).get("total_cost_usd", 0.0),
                        "evidence_status": (data.get("combined_review") or {}).get("evidence_sufficiency", {}).get("status", "unknown")
                    })
            except Exception:
                continue

        # Sort descending by created_at
        summaries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return summaries

    @classmethod
    def delete(cls, session_id: str) -> bool:
        """Delete a saved session."""
        file_path = cls._validate_session_id(session_id)
        if file_path.exists():
            file_path.unlink()
            return True
        return False
