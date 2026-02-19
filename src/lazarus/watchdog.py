"""Watchdog — monitors the pipeline and restarts stale jobs automatically.

Runs on a configurable loop, checking for jobs stuck in 'in_progress' longer
than a timeout threshold. When found, it resets them and optionally restarts
processing.  Also keeps a log so you can see what happened while you were away.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from lazarus.config import LazarusConfig
from lazarus.db.queue import JobQueue

logger = logging.getLogger("lazarus.watchdog")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _setup_logging(log_path: Path) -> None:
    """Configure file + console logging."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.setLevel(logging.INFO)


def _get_stale_jobs(queue: JobQueue, stale_minutes: int) -> list[dict]:
    """Find in_progress jobs older than stale_minutes."""
    import sqlite3

    cutoff = _utcnow().timestamp() - (stale_minutes * 60)
    conn = sqlite3.connect(str(queue._db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, package_name, version, updated_at
           FROM jobs WHERE status = 'in_progress'"""
    ).fetchall()
    conn.close()

    stale = []
    for row in rows:
        try:
            updated = datetime.fromisoformat(row["updated_at"]).timestamp()
        except (ValueError, TypeError):
            updated = 0
        if updated < cutoff:
            stale.append({
                "id": row["id"],
                "package_name": row["package_name"],
                "version": row["version"],
                "updated_at": row["updated_at"],
            })
    return stale


def _is_processor_running() -> bool:
    """Check if a lazarus process command is already running."""
    import psutil  # optional dependency

    try:
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmdline = proc.info.get("cmdline") or []
            joined = " ".join(cmdline).lower()
            if "lazarus" in joined and "process" in joined:
                return True
    except Exception:
        pass
    return False


def _start_processor(auto_only: bool = True) -> subprocess.Popen | None:
    """Spawn a new batch processor in the background."""
    cmd = [sys.executable, "-m", "lazarus", "admin", "process", "--auto-only"]
    if not auto_only:
        cmd.remove("--auto-only")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except Exception as e:
        logger.error(f"Failed to start processor: {e}")
        return None


class Watchdog:
    """Monitors the Lazarus pipeline and recovers from failures.

    Features:
        - Detects jobs stuck in 'in_progress' and resets them
        - Optionally restarts the batch processor when it dies
        - Logs everything to ~/.lazarus/watchdog.log
        - Handles graceful shutdown via SIGINT/SIGTERM
    """

    def __init__(
        self,
        config: LazarusConfig,
        interval: int = 60,
        stale_minutes: int = 10,
        auto_restart: bool = True,
        auto_only: bool = True,
    ) -> None:
        self.config = config
        self.interval = interval
        self.stale_minutes = stale_minutes
        self.auto_restart = auto_restart
        self.auto_only = auto_only
        self._running = False
        self._processor: subprocess.Popen | None = None

        log_path = config.base_dir / "watchdog.log"
        _setup_logging(log_path)

    def _handle_signal(self, signum: int, frame: object) -> None:
        """Graceful shutdown on SIGINT/SIGTERM."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False

    def _check_stale_jobs(self, queue: JobQueue) -> int:
        """Reset stale in_progress jobs. Returns count reset."""
        stale = _get_stale_jobs(queue, self.stale_minutes)
        if not stale:
            return 0

        for job in stale:
            logger.warning(
                f"Stale job detected: {job['package_name']}=={job['version']} "
                f"(id={job['id']}, last updated {job['updated_at']})"
            )

        reset = queue.reset_stale_jobs()
        if reset:
            logger.info(f"Reset {reset} stale job(s) back to pending")
        return reset

    def _check_processor(self) -> None:
        """Ensure the batch processor is running (if auto_restart is on)."""
        if not self.auto_restart:
            return

        # Check if our spawned process is still alive
        if self._processor is not None:
            retcode = self._processor.poll()
            if retcode is not None:
                logger.info(
                    f"Processor exited with code {retcode}"
                )
                self._processor = None

        # If no processor is running, check if there's work to do
        if self._processor is None:
            queue = JobQueue(self.config.db_path)
            queue.initialize()
            stats = queue.get_status()
            queue.close()

            pending = stats.get("pending", 0)
            if pending > 0:
                logger.info(
                    f"{pending} pending job(s) — starting processor"
                )
                self._processor = _start_processor(self.auto_only)
                if self._processor:
                    logger.info(
                        f"Processor started (PID {self._processor.pid})"
                    )

    def _log_status(self, queue: JobQueue) -> None:
        """Log current queue stats."""
        stats = queue.get_status()
        total = queue.count()
        parts = [f"{k}={v}" for k, v in sorted(stats.items())]
        logger.info(f"Queue: {', '.join(parts)} (total={total})")

    def run(self) -> None:
        """Main loop — runs until signaled to stop."""
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._running = True
        logger.info(
            f"Watchdog started (interval={self.interval}s, "
            f"stale_threshold={self.stale_minutes}m, "
            f"auto_restart={self.auto_restart})"
        )

        queue = JobQueue(self.config.db_path)
        queue.initialize()

        try:
            while self._running:
                try:
                    self._log_status(queue)
                    self._check_stale_jobs(queue)
                    self._check_processor()
                except Exception as e:
                    logger.error(f"Watchdog check failed: {e}")

                # Sleep in small increments so we can respond to signals
                for _ in range(self.interval):
                    if not self._running:
                        break
                    time.sleep(1)
        finally:
            # Clean up processor if we spawned one
            if self._processor is not None:
                logger.info("Terminating processor...")
                self._processor.terminate()
                try:
                    self._processor.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._processor.kill()
            queue.close()
            logger.info("Watchdog stopped")
