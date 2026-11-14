"""
Session Storage Service for Multiple AI Review Board.
Persists review sessions to JSON files in data/saved_reviews/
with strict path traversal protection and rerun lineage tracking.
"""

import json
import os
import re
import fcntl
import tempfile
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
        # Atomic replacement prevents readers seeing a partially written checkpoint.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=file_path.parent,
                                             prefix=".checkpoint-", delete=False) as f:
                temporary = f.name
                f.write(session.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, file_path)
            temporary = None
        finally:
            if temporary is not None:
                os.unlink(temporary)

    @classmethod
    def acquire_run_lock(cls, session_id):
        path = cls._validate_session_id(session_id).with_suffix(".lock")
        handle = open(path, "a")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            handle.close()
            return None

    @staticmethod
    def release_run_lock(handle):
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()

    @staticmethod
    def interrupted(session):
        session = session.model_copy(deep=True)
        session.status = "partial_failure" if session.specialist_reviews or session.challenge_round or session.combined_review else "failed"
        session.run_metadata["interrupted"] = True
        session.run_metadata["interruption_reason"] = "Execution owner stopped; dispatched calls are not resumed. In-flight usage and remote completion may be unknown."
        return session

    @classmethod
    def get(cls, session_id: str, *, detect_interruption: bool = True) -> Optional[ReviewBoardSession]:
        """Load session by session_id."""
        file_path = cls._validate_session_id(session_id)
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            session = ReviewBoardSession(**data)
        if detect_interruption and session.status == "in_progress":
            lock_path = file_path.with_suffix(".lock")
            if not lock_path.exists():
                return cls.interrupted(session)
            handle = cls.acquire_run_lock(session_id)
            if handle is not None:
                try:
                    # The owner may have finished between the first read and lock acquisition.
                    session = ReviewBoardSession.model_validate_json(file_path.read_text(encoding="utf-8"))
                    return cls.interrupted(session) if session.status == "in_progress" else session
                finally:
                    cls.release_run_lock(handle)
        return session

    @classmethod
    def record_rerun_lineage(cls, parent_id: str, child_id: str) -> None:
        """Record that child_id is a rerun of parent_id, preserving both."""
        path = cls._validate_session_id(parent_id).with_suffix(".lineage-lock")
        with open(path, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            parent = cls.get(parent_id)
            if parent and child_id not in parent.rerun_history:
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
                    session = cls.get(file.stem)
                    data = session.model_dump()
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
