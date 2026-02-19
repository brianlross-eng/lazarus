"""Shared test fixtures."""

import pytest

from lazarus.db.queue import JobQueue


@pytest.fixture
def queue() -> JobQueue:
    """Create an in-memory job queue for testing."""
    q = JobQueue(":memory:")
    q.initialize()
    return q
