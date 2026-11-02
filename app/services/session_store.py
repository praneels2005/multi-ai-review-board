"""
Session Storage Service for Multiple AI Review Board.
Persists review sessions to JSON files in data/saved_reviews/
allowing users to reopen, inspect, or rerun previous review boards.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.schemas.review_board_schema import ReviewBoardSession


STORAGE_DIR = Path("./data/saved_reviews")


class SessionStore:
    """Manages persistent disk storage of review board sessions."""

    @classmethod
    def _ensure_dir(cls) -> Path:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return STORAGE_DIR

    @classmethod
    def save(cls, session: ReviewBoardSession) -> None:
        """Persist session object to disk as JSON."""
        dir_path = cls._ensure_dir()
        file_path = dir_path / f"{session.session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(session.model_dump_json(indent=2))

    @classmethod
    def get(cls, session_id: str) -> Optional[ReviewBoardSession]:
        """Load session by session_id."""
        dir_path = cls._ensure_dir()
        file_path = dir_path / f"{session_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return ReviewBoardSession(**data)

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
        dir_path = cls._ensure_dir()
        file_path = dir_path / f"{session_id}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

