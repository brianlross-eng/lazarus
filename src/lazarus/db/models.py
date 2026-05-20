"""Data models for the job queue."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class FixMethod(StrEnum):
    NONE = "none"
    AUTO = "auto"
    AI = "ai"
    MANUAL = "manual"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    package_name: str
    version: str
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    fix_method: FixMethod = FixMethod.NONE
    priority: int = 0
    python_target: str = "3.14"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    id: int | None = None


SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_name TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    fix_method TEXT NOT NULL DEFAULT 'none',
    priority INTEGER NOT NULL DEFAULT 0,
    python_target TEXT NOT NULL DEFAULT '3.14',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(package_name, version, python_target)
);

CREATE INDEX IF NOT EXISTS idx_status_priority ON jobs(status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_package ON jobs(package_name);
"""

SCHEMA_VERSION_SQL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""
