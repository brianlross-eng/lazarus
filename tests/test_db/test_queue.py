"""Tests for the job queue."""

from lazarus.db.models import FixMethod, JobStatus
from lazarus.db.queue import JobQueue


class TestJobQueueAdd:
    def test_add_single_job(self, queue: JobQueue) -> None:
        job = queue.add("requests", "2.31.0", priority=100)
        assert job.package_name == "requests"
        assert job.version == "2.31.0"
        assert job.status == JobStatus.PENDING
        assert job.priority == 100
        assert job.attempts == 0
        assert job.id is not None

    def test_add_duplicate_returns_existing(self, queue: JobQueue) -> None:
        job1 = queue.add("requests", "2.31.0")
        job2 = queue.add("requests", "2.31.0")
        assert job1.id == job2.id

    def test_add_different_versions_are_separate(self, queue: JobQueue) -> None:
        job1 = queue.add("requests", "2.31.0")
        job2 = queue.add("requests", "2.32.0")
        assert job1.id != job2.id

    def test_add_different_python_targets_are_separate(self, queue: JobQueue) -> None:
        job1 = queue.add("requests", "2.31.0", python_target="3.14")
        job2 = queue.add("requests", "2.31.0", python_target="3.13")
        assert job1.id != job2.id

    def test_add_batch(self, queue: JobQueue) -> None:
        jobs = [
            ("requests", "2.31.0", 100),
            ("flask", "3.0.0", 90),
            ("django", "5.0.0", 80),
        ]
        added = queue.add_batch(jobs)
        assert added == 3
        assert queue.count() == 3

    def test_add_batch_skips_duplicates(self, queue: JobQueue) -> None:
        queue.add("requests", "2.31.0")
        jobs = [
            ("requests", "2.31.0", 100),
            ("flask", "3.0.0", 90),
        ]
        added = queue.add_batch(jobs)
        assert added == 1
        assert queue.count() == 2


class TestJobQueueClaim:
    def test_claim_next_returns_highest_priority(self, queue: JobQueue) -> None:
        queue.add("low-priority", "1.0.0", priority=10)
        queue.add("high-priority", "1.0.0", priority=100)
        queue.add("mid-priority", "1.0.0", priority=50)

        job = queue.claim_next()
        assert job is not None
        assert job.package_name == "high-priority"
        assert job.status == JobStatus.IN_PROGRESS
        assert job.attempts == 1

    def test_claim_next_returns_none_when_empty(self, queue: JobQueue) -> None:
        assert queue.claim_next() is None

    def test_claim_next_skips_non_pending(self, queue: JobQueue) -> None:
        job = queue.add("pkg", "1.0.0")
        claimed = queue.claim_next()
        assert claimed is not None
        # Second claim should return None — no more pending jobs
        assert queue.claim_next() is None

    def test_claim_increments_attempts(self, queue: JobQueue) -> None:
        queue.add("pkg", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        assert job.attempts == 1


class TestJobQueueStatusTransitions:
    def test_complete(self, queue: JobQueue) -> None:
        queue.add("pkg", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        queue.complete(job.id, FixMethod.AUTO)
        updated = queue.get(job.id)
        assert updated is not None
        assert updated.status == JobStatus.COMPLETE
        assert updated.fix_method == FixMethod.AUTO
        assert updated.last_error is None

    def test_fail(self, queue: JobQueue) -> None:
        queue.add("pkg", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        queue.fail(job.id, "C extension build failed")
        updated = queue.get(job.id)
        assert updated is not None
        assert updated.status == JobStatus.FAILED
        assert updated.last_error == "C extension build failed"

    def test_mark_review(self, queue: JobQueue) -> None:
        queue.add("pkg", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        queue.mark_review(job.id, "Complex rewrite needed")
        updated = queue.get(job.id)
        assert updated is not None
        assert updated.status == JobStatus.NEEDS_REVIEW
        assert updated.last_error == "Complex rewrite needed"

    def test_retry_resets_to_pending(self, queue: JobQueue) -> None:
        queue.add("pkg", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        queue.fail(job.id, "temporary error")
        assert queue.retry(job.id) is True
        updated = queue.get(job.id)
        assert updated is not None
        assert updated.status == JobStatus.PENDING

    def test_retry_fails_at_max_attempts(self, queue: JobQueue) -> None:
        queue.add("pkg", "1.0.0")
        # Exhaust all 3 attempts
        for _ in range(3):
            job = queue.claim_next()
            assert job is not None
            queue.fail(job.id, "error")
            if job.attempts < 3:
                queue.retry(job.id)
        # Now retry should fail
        assert queue.retry(job.id) is False


class TestJobQueueResetStale:
    def test_reset_stale_jobs(self, queue: JobQueue) -> None:
        queue.add("pkg1", "1.0.0")
        queue.add("pkg2", "1.0.0")
        queue.claim_next()  # pkg1 is now in_progress
        queue.claim_next()  # pkg2 is now in_progress

        reset_count = queue.reset_stale_jobs()
        assert reset_count == 2

        # Both should be pending again
        status = queue.get_status()
        assert status.get("pending", 0) == 2
        assert status.get("in_progress", 0) == 0

    def test_reset_does_not_touch_complete(self, queue: JobQueue) -> None:
        queue.add("pkg1", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        queue.complete(job.id, FixMethod.AUTO)

        reset_count = queue.reset_stale_jobs()
        assert reset_count == 0

        status = queue.get_status()
        assert status.get("complete", 0) == 1


class TestJobQueueQueries:
    def test_get_status(self, queue: JobQueue) -> None:
        queue.add("pkg1", "1.0.0")
        queue.add("pkg2", "1.0.0")
        queue.add("pkg3", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        queue.complete(job.id, FixMethod.AUTO)

        status = queue.get_status()
        assert status["pending"] == 2
        assert status["complete"] == 1

    def test_get_failures(self, queue: JobQueue) -> None:
        queue.add("pkg1", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        queue.fail(job.id, "build error")

        failures = queue.get_failures()
        assert len(failures) == 1
        assert failures[0].package_name == "pkg1"

    def test_get_reviews(self, queue: JobQueue) -> None:
        queue.add("pkg1", "1.0.0")
        job = queue.claim_next()
        assert job is not None
        queue.mark_review(job.id, "needs human")

        reviews = queue.get_reviews()
        assert len(reviews) == 1
        assert reviews[0].package_name == "pkg1"

    def test_get_error_patterns(self, queue: JobQueue) -> None:
        for i in range(5):
            queue.add(f"pkg{i}", "1.0.0")
            job = queue.claim_next()
            assert job is not None
            queue.fail(job.id, "C extension" if i < 3 else "import error")

        patterns = queue.get_error_patterns()
        assert patterns[0] == ("C extension", 3)
        assert patterns[1] == ("import error", 2)

    def test_search(self, queue: JobQueue) -> None:
        queue.add("flask", "3.0.0")
        queue.add("flask-cors", "4.0.0")
        queue.add("django", "5.0.0")

        results = queue.search("flask")
        assert len(results) == 2

    def test_count(self, queue: JobQueue) -> None:
        assert queue.count() == 0
        queue.add("pkg1", "1.0.0")
        queue.add("pkg2", "1.0.0")
        assert queue.count() == 2

    def test_get_nonexistent(self, queue: JobQueue) -> None:
        assert queue.get(999) is None
