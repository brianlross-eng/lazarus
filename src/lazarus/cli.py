"""Lazarus CLI — Bringing dead packages back to life."""

from __future__ import annotations

import subprocess
import sys

import click
from rich.console import Console
from rich.table import Table

from lazarus import __version__
from lazarus.config import LazarusConfig

console = Console()

HELP_TEXT = """\
LAZARUS(1)                       User Commands                      LAZARUS(1)

NAME
    lazarus - Bringing dead packages back to life

SYNOPSIS
    lazarus <command> [options] [arguments]
    lazarus admin <command> [options] [arguments]

DESCRIPTION
    Lazarus is a PyPI-compatible package index that automatically resurrects
    Python packages broken by version incompatibility. It pulls packages from
    PyPI, identifies compatibility issues via static analysis, applies fixes
    (both mechanical and AI-powered), verifies the results, and republishes
    them with PEP 440 compliant version tags.

    When you install a package through Lazarus, it checks its own index first.
    If a resurrected version exists, you get that. Otherwise, the request is
    transparently proxied to PyPI. Lazarus only stores what it uniquely
    provides.

COMMANDS
    raise <package> [-v VERSION]
        Install a package from the Lazarus index. If a resurrected version
        exists, it will be preferred over the upstream PyPI release. If not,
        the package is installed directly from PyPI.

            lazarus raise requests
            lazarus raise flask -v 3.0.0

    remove <package>
        Uninstall a previously installed package.

            lazarus remove old-package

    search <query>
        Search the Lazarus job queue for packages by name. Shows current
        resurrection status, version, and fix method for each match.

            lazarus search flask

    list
        List all currently installed Python packages (wraps pip list).

            lazarus list

    inspect <package>
        Show detailed compatibility status for a package, including
        resurrection status, fix method, Python target, attempt count,
        and any recorded errors.

            lazarus inspect numpy

    pray <package>
        Request that a package be added to the Lazarus resurrection queue.
        Looks up the latest version on PyPI and adds it as a pending job.

            lazarus pray old-package

    help
        Show this help page.

ADMIN COMMANDS
    lazarus admin seed [-n COUNT]
        Seed the job queue with the top N most downloaded packages from
        PyPI (default: 1000). Downloads are ranked using the previous
        30 days of PyPI download statistics.

            lazarus admin seed
            lazarus admin seed -n 500

    lazarus admin status
        Show a summary of the job queue: counts by status (pending,
        in progress, complete, failed, needs review).

            lazarus admin status

    lazarus admin process [-n MAX_JOBS] [--auto-only]
        Run batch processing on the job queue. Claims pending jobs and
        runs each through the full pipeline: fetch, analyze, fix, build.

        --auto-only restricts processing to mechanical fixes only (no
        Claude API calls). Use this for unattended server-side runs.

            lazarus admin process
            lazarus admin process -n 50 --auto-only

    lazarus admin reviews
        List all packages flagged as needing manual review. These are
        packages where automated fixes were insufficient or where the
        fix was too complex for the auto-fixer.

            lazarus admin reviews

    lazarus admin errors
        Show the most common error patterns from failed packages, grouped
        by frequency. Useful for identifying systemic issues worth
        automating.

            lazarus admin errors

    lazarus admin watchdog [-i INTERVAL] [-s STALE_MINUTES] [--no-restart]
        Start the pipeline watchdog. Runs in the foreground, monitoring the
        job queue for stale jobs and crashed processors.

        The watchdog checks every INTERVAL seconds (default: 60) for jobs
        stuck in 'in_progress' longer than STALE_MINUTES (default: 10).
        When found, it resets them back to pending. If the batch processor
        has exited, it automatically restarts it.

        All activity is logged to ~/.lazarus/watchdog.log.

            lazarus admin watchdog
            lazarus admin watchdog -i 30 -s 5
            lazarus admin watchdog --no-restart

ENVIRONMENT VARIABLES
    LAZARUS_HOME
        Base directory for Lazarus data (default: ~/.lazarus). Contains
        the job queue database, working directories, and download cache.

    ANTHROPIC_API_KEY
        API key for Claude. Required for AI-powered fixes. If not set,
        only mechanical auto-fixes are applied.

    LAZARUS_DEVPI_URL
        URL of the Lazarus devpi server (default: https://lazarus.dev).

    LAZARUS_DEVPI_PASSWORD
        Password for uploading packages to the devpi index.

    LAZARUS_PYTHON_TARGET
        Python version to target for compatibility (default: 3.14).

    LAZARUS_PYTHON_BINARY
        Path to the target Python interpreter (default: python3.14).

    LAZARUS_CLAUDE_MODEL
        Claude model to use for AI fixes (default: claude-sonnet-4-5-20241022).

FILES
    ~/.lazarus/queue.db     SQLite job queue database
    ~/.lazarus/work/        Temporary working directory for package processing
    ~/.lazarus/cache/       Downloaded source distribution cache
    ~/.lazarus/watchdog.log Watchdog activity log

VERSIONING
    Lazarus uses PEP 440 post-releases to tag fixed packages:

        requests 2.31.0             Original PyPI release
        requests 2.31.0.post314     Lazarus fix for Python 3.14
        requests 2.31.0.post3141    Revision 1 of the 3.14 fix

    Post-releases sort higher than the base version, so pip will
    automatically prefer the Lazarus version when using the Lazarus index.

EXAMPLES
    Resurrect and install a package:
        $ lazarus raise old-package

    Request a package be fixed:
        $ lazarus pray broken-lib

    Check what Lazarus knows about a package:
        $ lazarus inspect numpy

    Seed the queue and process the top 100 packages (auto-fix only):
        $ lazarus admin seed -n 100
        $ lazarus admin process -n 100 --auto-only

    Check processing progress:
        $ lazarus admin status

    Run the watchdog to keep processing alive:
        $ lazarus admin watchdog

    Review packages that need manual attention:
        $ lazarus admin reviews

VERSION
    lazarus {version}

PROJECT
    https://github.com/lazarus-py/lazarus

LAZARUS(1)                       User Commands                      LAZARUS(1)
""".format(version=__version__)


def get_config() -> LazarusConfig:
    config = LazarusConfig.from_env()
    config.ensure_dirs()
    return config


@click.group()
@click.version_option(package_name="lazarus")
def cli() -> None:
    """Lazarus - Bringing dead packages back to life.

    A PyPI-compatible package index that resurrects Python packages broken
    by version incompatibility. Run 'lazarus help' for full documentation.
    """


# ── Help Command ────────────────────────────────────────────────


@cli.command()
@click.argument("topic", required=False, default=None)
def help(topic: str | None) -> None:
    """Show detailed help. Optionally specify a command name for targeted help."""
    if topic is None:
        click.echo_via_pager(HELP_TEXT)
        return

    # Look up the topic as a command name
    cmd = cli.get_command(None, topic)  # type: ignore[arg-type]
    if cmd is not None:
        with click.Context(cmd, info_name=f"lazarus {topic}") as sub_ctx:
            click.echo(cmd.get_help(sub_ctx))
        return

    # Check admin subgroup
    admin_group = cli.get_command(None, "admin")  # type: ignore[arg-type]
    if isinstance(admin_group, click.Group):
        admin_cmd = admin_group.get_command(None, topic)  # type: ignore[arg-type]
        if admin_cmd is not None:
            with click.Context(admin_cmd, info_name=f"lazarus admin {topic}") as sub_ctx:
                click.echo(admin_cmd.get_help(sub_ctx))
            return

    console.print(f"[yellow]Unknown topic: '{topic}'. Run 'lazarus help' for full documentation.[/]")


# ── User Commands ───────────────────────────────────────────────


@cli.command("raise")
@click.argument("package")
@click.option("--version", "-v", default=None, help="Specific version to install")
def raise_(package: str, version: str | None) -> None:
    """Resurrect and install a package."""
    config = get_config()
    index_url = f"{config.devpi_url}/{config.devpi_index}/+simple/"

    cmd = [sys.executable, "-m", "pip", "install", "--index-url", index_url]
    if version:
        cmd.append(f"{package}=={version}")
    else:
        cmd.append(package)

    console.print(f"[bold]Raising {package}...[/]")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        console.print(f"[green]Successfully raised {package}[/]")
    else:
        console.print(f"[red]Failed to raise {package}[/]")
        sys.exit(result.returncode)


@cli.command()
@click.argument("package")
def remove(package: str) -> None:
    """Uninstall a package."""
    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        console.print(f"[green]Removed {package}[/]")
    else:
        console.print(f"[red]Failed to remove {package}[/]")
        sys.exit(result.returncode)


@cli.command()
@click.argument("query")
def search(query: str) -> None:
    """Search for packages in the Lazarus index."""
    from lazarus.db.queue import JobQueue

    config = get_config()
    queue = JobQueue(config.db_path)
    queue.initialize()
    jobs = queue.search(query)

    if not jobs:
        console.print(f"[yellow]No results for '{query}'[/]")
        return

    table = Table(title=f"Search: {query}")
    table.add_column("Package", style="bold")
    table.add_column("Version")
    table.add_column("Status")
    table.add_column("Fix Method")

    for job in jobs:
        status_style = {
            "complete": "green",
            "pending": "yellow",
            "in_progress": "blue",
            "failed": "red",
            "needs_review": "magenta",
        }.get(job.status, "")
        table.add_row(
            job.package_name,
            job.version,
            f"[{status_style}]{job.status}[/]",
            job.fix_method,
        )

    console.print(table)


@cli.command("list")
def list_() -> None:
    """List installed packages."""
    cmd = [sys.executable, "-m", "pip", "list"]
    subprocess.run(cmd)


@cli.command()
@click.argument("package")
def inspect(package: str) -> None:
    """Check compatibility status of a package."""
    from lazarus.db.queue import JobQueue

    config = get_config()
    queue = JobQueue(config.db_path)
    queue.initialize()
    jobs = queue.search(package)

    if not jobs:
        console.print(f"[yellow]{package} has not yet been resurrected[/]")
        return

    for job in jobs:
        console.print(f"\n[bold]{job.package_name} {job.version}[/]")
        console.print(f"  Status: {job.status}")
        console.print(f"  Fix method: {job.fix_method}")
        console.print(f"  Target: Python {job.python_target}")
        console.print(f"  Attempts: {job.attempts}")
        if job.last_error:
            console.print(f"  Last error: [red]{job.last_error}[/]")


@cli.command()
@click.argument("package")
def pray(package: str) -> None:
    """Request a package be added to Lazarus for resurrection."""
    from lazarus.db.queue import JobQueue
    from lazarus.pypi.client import PyPIClient

    config = get_config()
    queue = JobQueue(config.db_path)
    queue.initialize()

    console.print(f"[dim]Looking up {package} on PyPI...[/]")
    try:
        client = PyPIClient(config.cache_dir)
        version = client.get_latest_version(package)
        client.close()
    except Exception as e:
        console.print(f"[red]Could not find {package} on PyPI: {e}[/]")
        return

    job = queue.add(package, version, priority=50)
    if job.status == "complete":
        console.print(f"[green]{package} {version} has already been resurrected[/]")
    elif job.status == "pending":
        console.print(f"[green]Prayer received. {package} {version} added to the queue.[/]")
    else:
        console.print(f"[yellow]{package} {version} is already in the queue ({job.status})[/]")


# ── Admin Commands ──────────────────────────────────────────────


@cli.group()
def admin() -> None:
    """Administrative commands for managing the Lazarus pipeline."""


@admin.command()
@click.option("--count", "-n", default=1000, help="Number of top packages to seed")
def seed(count: int) -> None:
    """Seed the job queue with the top N packages from PyPI."""
    from lazarus.db.queue import JobQueue
    from lazarus.pypi.top_packages import seed_queue as do_seed

    config = get_config()
    queue = JobQueue(config.db_path)
    queue.initialize()

    console.print(f"[bold]Seeding queue with top {count} packages...[/]")
    added = do_seed(queue, count=count, python_target=config.python_target)
    total = queue.count()
    console.print(f"[green]Added {added} new packages. Total in queue: {total}[/]")


@admin.command()
def status() -> None:
    """Show job queue status."""
    from lazarus.db.queue import JobQueue

    config = get_config()
    queue = JobQueue(config.db_path)
    queue.initialize()

    stats = queue.get_status()
    total = queue.count()

    table = Table(title="Queue Status")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    style_map = {
        "pending": "yellow",
        "in_progress": "blue",
        "complete": "green",
        "failed": "red",
        "needs_review": "magenta",
    }

    for status_name, count in sorted(stats.items()):
        style = style_map.get(status_name, "")
        table.add_row(f"[{style}]{status_name}[/]", str(count))

    table.add_row("[bold]Total[/]", f"[bold]{total}[/]")
    console.print(table)


@admin.command()
@click.option("--max-jobs", "-n", default=0, help="Max jobs to process (0 = all)")
@click.option("--auto-only", is_flag=True, help="Only apply auto-fixes (no AI)")
def process(max_jobs: int, auto_only: bool) -> None:
    """Run batch processing on the queue."""
    from lazarus.pipeline import Pipeline

    config = get_config()
    pipeline = Pipeline(config)

    try:
        result = pipeline.run_batch(max_jobs=max_jobs, auto_only=auto_only)
        console.print(f"\n[bold]Processed {result.processed} package(s)[/]")
    finally:
        pipeline.close()


@admin.command()
def reviews() -> None:
    """List packages needing manual review."""
    from lazarus.db.queue import JobQueue

    config = get_config()
    queue = JobQueue(config.db_path)
    queue.initialize()

    jobs = queue.get_reviews()
    if not jobs:
        console.print("[green]No packages need review[/]")
        return

    table = Table(title="Needs Review")
    table.add_column("Package", style="bold")
    table.add_column("Version")
    table.add_column("Reason")
    table.add_column("Attempts", justify="right")

    for job in jobs:
        table.add_row(
            job.package_name,
            job.version,
            job.last_error or "—",
            str(job.attempts),
        )

    console.print(table)


@admin.command()
def errors() -> None:
    """Show common error patterns from failed packages."""
    from lazarus.db.queue import JobQueue

    config = get_config()
    queue = JobQueue(config.db_path)
    queue.initialize()

    patterns = queue.get_error_patterns()
    if not patterns:
        console.print("[green]No errors recorded[/]")
        return

    table = Table(title="Error Patterns")
    table.add_column("Error", style="red")
    table.add_column("Count", justify="right")

    for error, count in patterns[:20]:
        table.add_row(error, str(count))

    console.print(table)


@admin.command()
@click.option("--interval", "-i", default=60,
              help="Seconds between checks (default: 60)")
@click.option("--stale-minutes", "-s", default=10,
              help="Minutes before a job is considered stale (default: 10)")
@click.option("--no-restart", is_flag=True,
              help="Don't auto-restart the processor")
@click.option("--auto-only", is_flag=True, default=True,
              help="Only use auto-fixes when restarting (default: True)")
def watchdog(interval: int, stale_minutes: int, no_restart: bool,
             auto_only: bool) -> None:
    """Start the watchdog to monitor and recover stale jobs.

    The watchdog runs in the foreground, checking the queue every INTERVAL
    seconds. If it finds jobs stuck in 'in_progress' for longer than
    STALE_MINUTES, it resets them back to pending. If the batch processor
    has died, it automatically restarts it.

    Logs are written to ~/.lazarus/watchdog.log.

    \b
    Examples:
        lazarus admin watchdog
        lazarus admin watchdog -i 30 -s 5
        lazarus admin watchdog --no-restart
    """
    from lazarus.watchdog import Watchdog

    config = get_config()
    dog = Watchdog(
        config=config,
        interval=interval,
        stale_minutes=stale_minutes,
        auto_restart=not no_restart,
        auto_only=auto_only,
    )

    console.print(f"[bold]Watchdog starting[/]")
    console.print(f"  Check interval: {interval}s")
    console.print(f"  Stale threshold: {stale_minutes}m")
    console.print(f"  Auto-restart: {'off' if no_restart else 'on'}")
    console.print(f"  Log: {config.base_dir / 'watchdog.log'}")
    console.print(f"  Press Ctrl+C to stop\n")

    dog.run()
