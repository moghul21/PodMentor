"""Database access layer for storing and querying usage logs in PodMentor."""

import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any


class UsageDatabase:
    """Thread-safe SQLite database manager for tracking LLM token and cost usage."""

    def __init__(self, db_path: str = "podmentor.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS usage_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        model TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        prompt_tokens INTEGER NOT NULL,
                        completion_tokens INTEGER NOT NULL,
                        total_tokens INTEGER NOT NULL,
                        cost_usd REAL NOT NULL,
                        latency_ms REAL NOT NULL,
                        status TEXT NOT NULL,
                        fallback_used INTEGER NOT NULL DEFAULT 0,
                        error_message TEXT
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_usage_logs_model ON usage_logs(model);
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_usage_logs_timestamp ON usage_logs(timestamp);
                """)
                conn.commit()

    def record_usage(
        self,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: float,
        latency_ms: float,
        status: str = "success",
        fallback_used: bool = False,
        error_message: str | None = None,
        timestamp: str | None = None,
    ) -> int:
        if timestamp is None:
            timestamp = datetime.now(UTC).isoformat()

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO usage_logs (
                        timestamp, model, provider, prompt_tokens,
                        completion_tokens, total_tokens, cost_usd,
                        latency_ms, status, fallback_used, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        model,
                        provider,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        cost_usd,
                        latency_ms,
                        status,
                        1 if fallback_used else 0,
                        error_message,
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid or 0)

    def get_usage_summary(self, limit: int = 50) -> dict[str, Any]:
        """Aggregate total tokens and cost, breakdown by model, and recent request logs."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Overall totals
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        COALESCE(SUM(prompt_tokens), 0) as total_prompt,
                        COALESCE(SUM(completion_tokens), 0) as total_completion,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COALESCE(SUM(cost_usd), 0.0) as total_cost
                    FROM usage_logs
                """)
                row = cursor.fetchone()
                total_requests = row["total_requests"] if row else 0
                total_prompt = row["total_prompt"] if row else 0
                total_completion = row["total_completion"] if row else 0
                total_tokens = row["total_tokens"] if row else 0
                total_cost = round(row["total_cost"] if row else 0.0, 8)

                # Breakdown by model
                cursor.execute("""
                    SELECT
                        model,
                        COUNT(*) as requests,
                        COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as total_tokens,
                        COALESCE(SUM(cost_usd), 0.0) as cost_usd
                    FROM usage_logs
                    GROUP BY model
                    ORDER BY requests DESC
                """)
                by_model = {}
                for m_row in cursor.fetchall():
                    by_model[m_row["model"]] = {
                        "requests": m_row["requests"],
                        "prompt_tokens": m_row["prompt_tokens"],
                        "completion_tokens": m_row["completion_tokens"],
                        "total_tokens": m_row["total_tokens"],
                        "cost_usd": round(m_row["cost_usd"], 8),
                    }

                # Recent requests
                cursor.execute(
                    """
                    SELECT
                        id, timestamp, model, provider, prompt_tokens,
                        completion_tokens, total_tokens, cost_usd, latency_ms,
                        status, fallback_used
                    FROM usage_logs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                recent = []
                for r_row in cursor.fetchall():
                    recent.append(
                        {
                            "id": r_row["id"],
                            "timestamp": r_row["timestamp"],
                            "model": r_row["model"],
                            "provider": r_row["provider"],
                            "prompt_tokens": r_row["prompt_tokens"],
                            "completion_tokens": r_row["completion_tokens"],
                            "total_tokens": r_row["total_tokens"],
                            "cost_usd": round(r_row["cost_usd"], 8),
                            "latency_ms": round(r_row["latency_ms"], 2),
                            "status": r_row["status"],
                            "fallback_used": bool(r_row["fallback_used"]),
                        }
                    )

                return {
                    "total_requests": total_requests,
                    "total_prompt_tokens": total_prompt,
                    "total_completion_tokens": total_completion,
                    "total_tokens": total_tokens,
                    "total_cost_usd": total_cost,
                    "by_model": by_model,
                    "recent_requests": recent,
                }

    def clear_all(self) -> None:
        """Clear all records from usage_logs (used in test fixtures)."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM usage_logs;")
                conn.commit()


_db_instance: UsageDatabase | None = None


def get_db(db_path: str = "podmentor.db") -> UsageDatabase:
    """Singleton getter for the UsageDatabase."""
    global _db_instance
    if _db_instance is None or _db_instance.db_path != db_path:
        _db_instance = UsageDatabase(db_path=db_path)
    return _db_instance
