"""Tests for the Lazarus watchdog."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lazarus.config import LazarusConfig
from lazarus.db.models import JobStatus
from lazarus.db.queue import JobQueue
from lazarus.watchdog import Watchdog, _get_stale_jobs


@pytest.fixture
def config(tmp_path: Path) -> LazarusConfig:
    cfg = LazarusConfig(base_dir=tmp_path)
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def queue(config: LazarusConfig) -> JobQueue:
    q = JobQueue(config.db_path)
    q.initialize()
    return q


class TestStaleJobDetection:
    """Test that stale jobs are correctly identified."""

    def test_no_stale_jobs(self, queue: JobQueue) -> None:
        queue.add("fresh-pkg", "1.0.0", priority=10)
        stale = _get_stale_jobs(queue, stale_minutes=10)
        assert stale == []

    def test_in_progress_not_stale_yet(self, queue: JobQueue) -> None:
        queue.add("working-pkg", "1.0.0", priority=10)
        job = queue.claim_next()
        assert job is not None
        # Just claimed — should not be stale with 10 minute threshold
        stale = _get_stale_jobs(queue, stale_minutes=10)
        assert stale == []

    def test_in_progress_is_stale(self, queue: JobQueue) -> None:
        queue.add("stuck-pkg", "1.0.0", priority=10)
        job = queue.claim_next()
        assert job is not None

        # Manually backdate the updated_at to make it stale
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        conn = sqlite3.connect(str(queue._db_path))
        conn.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ?",
            (old_time, job.id),
        )
        conn.commit()
        conn.close()

        stale = _get_stale_jobs(queue, stale_minutes=10)
        assert len(stale) == 1
        assert stale[0]["package_name"] == "stuck-pkg"

    def test_stale_threshold_respected(self, queue: JobQueue) -> None:
        queue.add("borderline-pkg", "1.0.0", priority=10)
        job = queue.claim_next()
        assert job is not None

        # Set to 4 minutes ago
        recent = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
        conn = sqlite3.connect(str(queue._db_path))
        conn.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ?",
            (recent, job.id),
        )
        conn.commit()
        conn.close()

        # 5 minute threshold — should be stale
        stale = _get_stale_jobs(queue, stale_minutes=5)
        assert len(stale) == 0

        # 3 minute threshold — should be stale
        stale = _get_stale_jobs(queue, stale_minutes=3)
        assert len(stale) == 1


class TestWatchdogCheckStale:
    """Test the watchdog's stale job reset behavior."""

    def test_resets_stale_jobs(self, config: LazarusConfig,
                               queue: JobQueue) -> None:
        dog = Watchdog(config, interval=1, stale_minutes=1, auto_restart=False)

        queue.add("dead-pkg", "2.0.0", priority=5)
        job = queue.claim_next()
        assert job is not None

        # Backdate to make stale
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        conn = sqlite3.connect(str(queue._db_path))
        conn.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ?",
            (old_time, job.id),
        )
        conn.commit()
        conn.close()

        reset_count = dog._check_stale_jobs(queue)
        assert reset_count == 1

        # Verify job is back to pending
        refreshed = queue.get(job.id)
        assert refreshed is not None
        assert refreshed.status == JobStatus.PENDING

    def test_no_reset_when_fresh(self, config: LazarusConfig,
                                  queue: JobQueue) -> None:
        dog = Watchdog(config, interval=1, stale_minutes=10, auto_restart=False)

        queue.add("active-pkg", "1.0.0", priority=5)
        queue.claim_next()

        reset_count = dog._check_stale_jobs(queue)
        assert reset_count == 0


class TestWatchdogLogStatus:
    """Test status logging."""

    def test_logs_queue_stats(self, config: LazarusConfig,
                               queue: JobQueue) -> None:
        dog = Watchdog(config, interval=1, stale_minutes=10, auto_restart=False)

        queue.add("pkg-a", "1.0.0", priority=10)
        queue.add("pkg-b", "1.0.0", priority=5)

        # Should not raise
        dog._log_status(queue)


class TestWatchdogSignalHandling:
    """Test graceful shutdown."""

    def test_signal_stops_loop(self, config: LazarusConfig) -> None:
        dog = Watchdog(config, interval=1, stale_minutes=10, auto_restart=False)
        dog._running = True
        dog._handle_signal(2, None)  # SIGINT
        assert dog._running is False
