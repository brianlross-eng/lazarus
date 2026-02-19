"""Pipeline orchestrator — ties all stages together for end-to-end processing."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from lazarus.compat.analyzer import CompatIssue, StaticAnalyzer
from lazarus.compat.failures import FailureType, classify_failure, is_auto_fixable
from lazarus.compat.tester import CompatTester, TestResult
from lazarus.config import LazarusConfig
from lazarus.db.models import FixMethod, Job, JobStatus
from lazarus.db.queue import JobQueue
from lazarus.fixer.auto import AutoFixer
from lazarus.fixer.patcher import Patcher
from lazarus.publisher.builder import PackageBuilder
from lazarus.publisher.versioning import lazarus_version, rewrite_version_in_source
from lazarus.pypi.client import PyPIClient

console = Console()


@dataclass
class ProcessResult:
    package_name: str
    version: str
    success: bool
    fix_method: FixMethod = FixMethod.NONE
    issues_found: int = 0
    issues_fixed: int = 0
    error: str | None = None
    dists_built: list[str] = field(default_factory=list)


@dataclass
class BatchResult:
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[ProcessResult] = field(default_factory=list)


class Pipeline:
    """End-to-end package resurrection pipeline."""

    def __init__(self, config: LazarusConfig) -> None:
        self.config = config
        config.ensure_dirs()
        self.queue = JobQueue(config.db_path)
        self.queue.initialize()
        self.pypi = PyPIClient(config.cache_dir)
        self.analyzer = StaticAnalyzer()
        self.tester = CompatTester(config.python_binary)
        self.auto_fixer = AutoFixer()
        self.patcher = Patcher()
        self.builder = PackageBuilder()

    def close(self) -> None:
        self.pypi.close()

    def process_one(self, job: Job) -> ProcessResult:
        """Run the full pipeline for a single package."""
        result = ProcessResult(
            package_name=job.package_name,
            version=job.version,
            success=False,
        )

        work_dir = Path(tempfile.mkdtemp(
            prefix=f"lazarus_{job.package_name}_",
            dir=str(self.config.work_dir),
        ))

        try:
            # 1. Fetch
            console.print(f"  [dim]Fetching {job.package_name}=={job.version}...[/]")
            sdist_path = self.pypi.download_sdist(job.package_name, job.version)
            source_dir = self.pypi.extract_sdist(sdist_path, work_dir / "source")

            # 2. Analyze
            console.print(f"  [dim]Analyzing for 3.14 compatibility...[/]")
            issues = self.analyzer.analyze_tree(source_dir)
            result.issues_found = len(issues)

            if not issues:
                # Package may already be compatible — mark complete
                console.print(f"  [green]No issues found — already compatible[/]")
                result.success = True
                result.fix_method = FixMethod.NONE
                return result

            console.print(f"  [yellow]Found {len(issues)} issue(s)[/]")

            # 3. Backup
            backup_path = self.patcher.backup_original(source_dir)

            # 4. Auto-fix what we can
            auto_fixable = [i for i in issues if i.auto_fixable]
            needs_ai = [i for i in issues if not i.auto_fixable]

            if auto_fixable:
                console.print(f"  [dim]Auto-fixing {len(auto_fixable)} issue(s)...[/]")
                fix_result = self.auto_fixer.apply_all(source_dir, auto_fixable)
                result.issues_fixed += fix_result.issues_fixed

            # 5. AI fix remaining issues (if configured and needed)
            if needs_ai and self.config.anthropic_api_key:
                console.print(f"  [dim]Sending {len(needs_ai)} issue(s) to Claude...[/]")
                try:
                    from lazarus.fixer.claude import ClaudeFixer
                    claude = ClaudeFixer(
                        api_key=self.config.anthropic_api_key,
                        model=self.config.claude_model,
                        max_tokens=self.config.max_tokens_per_fix,
                    )
                    attempts = claude.fix_package(source_dir, needs_ai)
                    for attempt in attempts:
                        if attempt.fixed_code != attempt.original_code:
                            result.issues_fixed += len(attempt.issues_addressed)
                    result.fix_method = FixMethod.AI
                except Exception as e:
                    console.print(f"  [red]Claude fix failed: {e}[/]")
                    result.fix_method = FixMethod.AUTO if auto_fixable else FixMethod.NONE
            elif needs_ai:
                # No API key — mark for review
                console.print(f"  [yellow]{len(needs_ai)} issue(s) need AI/manual fix[/]")
                result.fix_method = FixMethod.AUTO if auto_fixable else FixMethod.NONE
            else:
                result.fix_method = FixMethod.AUTO

            # 6. Rewrite version
            python_target = job.python_target.replace(".", "")
            new_ver = lazarus_version(job.version, python_target)
            rewrite_version_in_source(source_dir, new_ver)

            # 7. Build
            console.print(f"  [dim]Building distributions...[/]")
            output_dir = work_dir / "dist"
            try:
                dists = self.builder.build_all(source_dir, output_dir)
                result.dists_built = [p.name for p in dists]
                result.success = True
            except Exception as e:
                console.print(f"  [red]Build failed: {e}[/]")
                result.error = str(e)

            # Cleanup backup
            self.patcher.cleanup_backup(backup_path)

        except Exception as e:
            result.error = str(e)
            console.print(f"  [red]Error: {e}[/]")
        finally:
            # Clean up work directory
            shutil.rmtree(work_dir, ignore_errors=True)

        return result

    def run_batch(self, max_jobs: int = 0, auto_only: bool = False) -> BatchResult:
        """Process jobs from the queue.

        Args:
            max_jobs: Maximum number of jobs to process (0 = unlimited).
            auto_only: If True, only apply auto-fixes (no Claude API calls).
        """
        batch = BatchResult()

        # Reset any stale in-progress jobs
        reset = self.queue.reset_stale_jobs()
        if reset:
            console.print(f"[yellow]Reset {reset} stale job(s)[/]")

        original_api_key = self.config.anthropic_api_key
        if auto_only:
            self.config.anthropic_api_key = ""

        try:
            while True:
                if max_jobs > 0 and batch.processed >= max_jobs:
                    break

                job = self.queue.claim_next()
                if job is None:
                    break

                console.print(
                    f"\n[bold]Processing [{batch.processed + 1}] "
                    f"{job.package_name}=={job.version}[/]"
                )

                result = self.process_one(job)
                batch.results.append(result)
                batch.processed += 1

                if result.success:
                    self.queue.complete(job.id, result.fix_method)
                    batch.succeeded += 1
                    console.print(f"  [green]Success ({result.fix_method})[/]")
                elif result.error and is_auto_fixable(
                    classify_failure(result.error)
                ):
                    # Potentially fixable — retry later
                    if not self.queue.retry(job.id):
                        self.queue.fail(job.id, result.error)
                        batch.failed += 1
                    else:
                        batch.skipped += 1
                else:
                    self.queue.fail(job.id, result.error or "Unknown error")
                    batch.failed += 1
                    console.print(f"  [red]Failed: {result.error}[/]")

        finally:
            self.config.anthropic_api_key = original_api_key

        console.print(f"\n[bold]Batch complete:[/] "
                      f"{batch.succeeded} succeeded, {batch.failed} failed, "
                      f"{batch.skipped} skipped")
        return batch
