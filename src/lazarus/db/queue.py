"""SQLite-based job queue with stop/resume support."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from lazarus.db.migrations import migrate
from lazarus.db.models import FixMethod, Job, JobStatus


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        package_name=row["package_name"],
        version=row["version"],
        status=JobStatus(row["status"]),
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        last_error=row["last_error"],
        fix_method=FixMethod(row["fix_method"]),
        priority=row["priority"],
        python_target=row["python_target"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class JobQueue:
    """Persistent job queue backed by SQLite.

    Supports atomic job claiming, stop/resume, and priority ordering.
    """

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def initialize(self) -> None:
        """Create tables and run migrations."""
        migrate(self._conn)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def reset_stale_jobs(self) -> int:
        """Reset any in_progress jobs back to pending (for restart recovery)."""
        now = _utcnow()
        cursor = self._conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE status = ?",
            (JobStatus.PENDING, now, JobStatus.IN_PROGRESS),
        )
        self._conn.commit()
        return cursor.rowcount

    def add(self, package_name: str, version: str, priority: int = 0,
            python_target: str = "3.14") -> Job:
        """Add a single job to the queue. Returns the job (ignores duplicates)."""
        now = _utcnow()
        try:
            cursor = self._conn.execute(
                """INSERT INTO jobs (package_name, version, priority, python_target,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (package_name, version, priority, python_target, now, now),
            )
            self._conn.commit()
            job_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            # Already exists — fetch the existing one
            row = self._conn.execute(
                """SELECT * FROM jobs WHERE package_name = ? AND version = ?
                   AND python_target = ?""",
                (package_name, version, python_target),
            ).fetchone()
            return _row_to_job(row)

        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row)

    def add_batch(self, jobs: list[tuple[str, str, int]],
                  python_target: str = "3.14") -> int:
        """Add multiple jobs. Each tuple is (package_name, version, priority).
        Returns number of new jobs added."""
        now = _utcnow()
        added = 0
        for package_name, version, priority in jobs:
            try:
                self._conn.execute(
                    """INSERT INTO jobs (package_name, version, priority, python_target,
                       created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (package_name, version, priority, python_target, now, now),
                )
                added += 1
            except sqlite3.IntegrityError:
                continue
        self._conn.commit()
        return added

    def claim_next(self) -> Job | None:
        """Atomically claim the highest-priority pending job."""
        now = _utcnow()
        # Find the next pending job ordered by priority DESC
        row = self._conn.execute(
            """SELECT id FROM jobs WHERE status = ?
               ORDER BY priority DESC, created_at ASC LIMIT 1""",
            (JobStatus.PENDING,),
        ).fetchone()

        if row is None:
            return None

        job_id = row["id"]
        self._conn.execute(
            """UPDATE jobs SET status = ?, attempts = attempts + 1, updated_at = ?
               WHERE id = ?""",
            (JobStatus.IN_PROGRESS, now, job_id),
        )
        self._conn.commit()

        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row)

    def complete(self, job_id: int, fix_method: FixMethod = FixMethod.NONE) -> None:
        """Mark a job as complete."""
        now = _utcnow()
        self._conn.execute(
            "UPDATE jobs SET status = ?, fix_method = ?, last_error = NULL, updated_at = ? WHERE id = ?",
            (JobStatus.COMPLETE, fix_method, now, job_id),
        )
        self._conn.commit()

    def fail(self, job_id: int, error: str) -> None:
        """Mark a job as failed."""
        now = _utcnow()
        self._conn.execute(
            "UPDATE jobs SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (JobStatus.FAILED, error, now, job_id),
        )
        self._conn.commit()

    def mark_review(self, job_id: int, reason: str) -> None:
        """Mark a job as needing manual review."""
        now = _utcnow()
        self._conn.execute(
            "UPDATE jobs SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (JobStatus.NEEDS_REVIEW, reason, now, job_id),
        )
        self._conn.commit()

    def retry(self, job_id: int) -> bool:
        """Reset a failed/review job back to pending if under max attempts."""
        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return False
        job = _row_to_job(row)
        if job.attempts >= job.max_attempts:
            return False
        now = _utcnow()
        self._conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
            (JobStatus.PENDING, now, job_id),
        )
        self._conn.commit()
        return True

    def get(self, job_id: int) -> Job | None:
        """Get a job by ID."""
        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return _row_to_job(row)

    def get_status(self) -> dict[str, int]:
        """Get counts by status."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
        ).fetchall()
        return {row["status"]: row["count"] for row in rows}

    def get_failures(self, limit: int = 50) -> list[Job]:
        """Get failed jobs."""
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
            (JobStatus.FAILED, limit),
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def get_reviews(self) -> list[Job]:
        """Get jobs needing manual review."""
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY priority DESC",
            (JobStatus.NEEDS_REVIEW,),
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def get_error_patterns(self) -> list[tuple[str, int]]:
        """Get error messages grouped by frequency."""
        rows = self._conn.execute(
            """SELECT last_error, COUNT(*) as count FROM jobs
               WHERE last_error IS NOT NULL
               GROUP BY last_error ORDER BY count DESC""",
        ).fetchall()
        return [(row["last_error"], row["count"]) for row in rows]

    def search(self, package_name: str) -> list[Job]:
        """Search for jobs by package name (partial match)."""
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE package_name LIKE ? ORDER BY priority DESC",
            (f"%{package_name}%",),
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    def count(self) -> int:
        """Get total number of jobs."""
        row = self._conn.execute("SELECT COUNT(*) as count FROM jobs").fetchone()
        return row["count"]
