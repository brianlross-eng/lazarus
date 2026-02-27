# Lazarus Project — Claude Memory

## What This Project Is
PyPI-compatible proxy repository that automatically resurrects Python packages broken by Python 3.14 incompatibility. Pulls packages from PyPI, detects compatibility issues (AST-based static analysis), fixes them (auto-fix or Claude AI), rebuilds, and republishes with `.post314` version suffixes.

## Version
- **Current**: 1.0.0a1 (Alpha)
- **Versioning**: PEP 440 + SemVer — track changes in `CHANGELOG.md`
- **Tags**: `v1.0.0a1`, etc.

## Repository
- GitHub: https://github.com/brianlross-eng/lazarus
- Branch: `master`
- Python: 3.14 (the target platform)
- Package layout: `src/lazarus/` with `pyproject.toml`

## Key Commands
```bash
# Run all tests (175 tests, should all pass)
python -m pytest -v

# CLI (must use python -m until pip install -e . is done)
python -m lazarus admin status          # Queue stats
python -m lazarus admin errors           # Show common error patterns from failed jobs
python -m lazarus admin reviews         # Show packages needing AI/manual fix
python -m lazarus admin process --auto-only  # Process queue (auto-fixes only)
python -m lazarus admin watchdog        # Supervisor process
python -m lazarus admin seed --count 1000    # Seed queue from top PyPI packages
python -m lazarus admin seed --deep -n 5000  # Seed from full PyPI index (long tail)
python -m lazarus admin retry-failures --dry-run  # Preview fixable failed packages
python -m lazarus admin retry-failures --pattern SyntaxError --limit 10  # Retry specific pattern

# Useful direct DB queries
python -c "from lazarus.config import LazarusConfig; from lazarus.db.queue import JobQueue; q = JobQueue(LazarusConfig().db_path); q.initialize(); print(q.get_status()); q.close()"
```

## Architecture
```
src/lazarus/
├── cli.py              # Click CLI with raise/remove/search/list/inspect/pray + admin commands
├── config.py           # LazarusConfig dataclass, paths, API keys
├── pipeline.py         # Orchestrator: fetch → analyze → fix → build (ProcessResult, BatchResult)
├── watchdog.py         # Supervisor: monitors stale jobs, auto-restarts processor
├── db/
│   ├── models.py       # Job, JobStatus enum, FixMethod enum
│   ├── queue.py        # JobQueue: SQLite CRUD, claim_next, status transitions
│   └── migrations.py   # Integer-versioned schema migrations
├── pypi/
│   ├── client.py       # PyPI JSON API, download/extract sdists (httpx)
│   ├── top_packages.py # Fetch top-N from hugovk dataset
│   └── metadata.py     # PackageMetadata, VersionMetadata dataclasses
├── compat/
│   ├── analyzer.py     # AST-based static analysis (14 check types)
│   ├── tester.py       # Run tests in isolated 3.14 venvs
│   └── failures.py     # Failure classification
├── fixer/
│   ├── auto.py         # Mechanical fixes (14 fix types including escape sequences)
│   ├── claude.py       # Claude API for complex fixes
│   └── patcher.py      # Backup/restore for safe patching
├── publisher/
│   ├── versioning.py   # PEP 440 .post314 version rewriting
│   ├── builder.py      # Build sdist/wheel via PEP 517
│   └── uploader.py     # Push to devpi server
└── server/
    ├── config.py       # Generate devpi/nginx configs
    └── deploy.py       # Hetzner setup scripts
```

## Analyzer Checks (14 types in compat/analyzer.py)
1. `removed_ast_node` — ast.Num/Str/Bytes/NameConstant/Ellipsis → ast.Constant ✅ auto-fixable
2. `removed_asyncio_watcher` — child watcher APIs removed ❌ needs AI
3. `removed_pkgutil_loader` — find_loader/get_loader → importlib.util.find_spec ✅ auto-fixable
4. `removed_sqlite3_version` — sqlite3.version → sqlite3.sqlite_version ✅ auto-fixable
5. `removed_urllib_class` — URLopener/FancyURLopener removed ❌ needs AI
6. `removed_importlib_abc` — ResourceReader/Traversable → importlib.resources.abc ✅ auto-fixable
7. `removed_shutil_onerror` — onerror → onexc ✅ auto-fixable
8. `pathlib_extra_args` — multiple args to relative_to/is_relative_to ❌ needs AI
9. `removed_pty_function` — master_open/slave_open → openpty ✅ auto-fixable
10. `deprecated_pkg_resources` — pkg_resources imports ✅ auto-fixable (common patterns)
11. `invalid_escape_sequence` — \p, \/, \d etc. in non-raw strings ✅ auto-fixable
12. `python2_builtin_*` — execfile(), raw_input() → exec(open().read()), input() ✅ auto-fixable (text-based)
13. `removed_module_*` — urllib2, Queue, commands → Python 3 equivalents ✅ auto-fixable (text-based)
14. `removed_ast_constant_attr` — ast.Constant.s/.n → .value ✅ auto-fixable (AST-based)

## Auto-Fixer Handlers (14 types in fixer/auto.py)
Matching the auto-fixable analyzer checks above. The escape sequence fixer uses a character-by-character state machine to double invalid backslashes while preserving valid escapes and raw strings. The pkg_resources fixer handles get_distribution().version, require(), and resource_filename() patterns via regex replacement. Python 2 builtin/module fixers use regex-based text replacement (works even on files with SyntaxError).

## Pipeline Behavior
- Full loop: fetch → analyze → fix → build → **upload to devpi** → installable via pip
- **Cache cleanup**: cached sdists are deleted after each job completes (prevents disk exhaustion)
- **Missing build files**: `_ensure_build_files()` creates empty stubs for requirements.txt, README, VERSION etc. referenced in setup.py but missing from sdist (fixes ~260 packages)
- `SKIP_BUILD_PACKAGES` frozenset: 26 C-extension packages that hang during build
- `_has_c_extensions()` heuristic: detects .c/.cpp/.pyx files and ext_modules in setup.py
- `needs_review` workflow: packages with unfixed AI issues get flagged instead of silently completed
- Two-tier design: server runs `--auto-only` (no API key), reviews pulled locally for Claude fixing
- Upload requires `--upload` flag or `LAZARUS_UPLOAD=1` + `LAZARUS_DEVPI_PASSWORD`
- DevpiUploader uses native devpi auth: login → base64(user:token) X-Devpi-Auth header
- **Version override strategy** (four layers):
  1. `dynamic = ["version"]` → removed from list (any position), set static version in pyproject.toml
  2. `SETUPTOOLS_SCM_PRETEND_VERSION` env var for git-tag-based versions
  3. PKG-INFO rewrite as universal sdist fallback
  4. Regex rewrites for setup.py, setup.cfg, __init__.py with `__version__ = "..."`
  5. Version regexes use `(?!\.)` negative lookahead (prevents `".".join()` corruption) and `\b` word boundary (prevents `minversion`/`local_version` matches)
- **Build environment**: `PIP_CONSTRAINT=setuptools<82` ensures pkg_resources remains available in isolated build venvs

## Batch Processing Results
### Batch 1+2: 149,053 packages — COMPLETE
- 132,302 complete (88.8%), ~15,500 auto-fixed
- 16,751 failed (~15,300 no sdist, ~1,450 other)
- Retry pass recovered 18 additional packages via expanded fixers

## Database
- SQLite at `~/.lazarus/queue.db`
- WAL mode, 5s busy timeout
- Job statuses: pending, in_progress, complete, failed, needs_review
- Fix methods: none, auto, ai, manual

## Important Gotchas
- Background tasks in Claude conversation sandbox die between turns — use real terminal sessions
- Server was running old 0.1.0 package until 2026-02-25 — now 1.0.0a1 via `pip install -e .`
- Version rewrite can accidentally affect build dependency version checks (seen with scikit-build-core)
- The `re` import in analyzer.py is currently unused (was imported for escape sequence work but state machine approach was used instead)
- **Disk space**: work dir can grow to 20GB+ from OOM kills/crashes — watchdog now auto-cleans orphaned dirs >30min old
- `cosmowap` package causes OOM kills — manually failed in DB

## Domain & Infrastructure
- **Domain**: lazaruspy.org (Cloudflare Registrar)
- **Email**: admin@lazaruspy.org (Cloudflare Email Routing → personal email)
- **DNS**: Cloudflare — A record → 89.167.40.82, CNAME www → lazaruspy.org
- **Server**: Hetzner CX33 (4 vCPU, 8 GB RAM, 80 GB SSD) — Helsinki, Ubuntu 24.04
- **Server IP**: 89.167.40.82 (hostname: lazarus-prod)
- **Package index URL**: https://lazaruspy.org/simple/
- **SSL**: Let's Encrypt (auto-renew via certbot)

## Server Stack
- **devpi-server 6.19.1** on port 3141 (localhost only), proxied by nginx
- **devpi user**: `lazarus` (password: `lazarus314prod`)
- **devpi index**: `lazarus/packages` (inherits from `root/pypi`)
- **nginx**: reverse proxy, `/simple/` → devpi `lazarus/packages/+simple/`
- **Python**: 3.14.3 (deadsnakes PPA) at `/opt/lazarus-venv/`
- **Lazarus**: 1.0.0a1 installed from `/opt/lazarus/` (git clone, `pip install -e .`)

## Server Services (systemd)
- `devpi.service` — devpi-server on 127.0.0.1:3141 (enabled, running)
- `lazarus-processor.service` — `admin process --auto-only --upload` (enabled, running)
- `lazarus-watchdog.service` — `admin watchdog` (enabled, running)
- `lazarus-seed.timer` — weekly seed of top 5,000 packages

## Server SSH Access
```bash
ssh -i ~/.ssh/id_ed25519 root@89.167.40.82
```

## Published Packages (on lazaruspy.org)
- `pip-26.0.1.post314` — auto-fixed
- `pyparsing-3.3.2.post314` — auto-fixed (flit dynamic version)
- `zipp-3.23.0.post314` — auto-fixed (setuptools_scm dynamic version)
- Install: `pip install --extra-index-url https://lazaruspy.org/simple/ <package>`

## What's Next (toward 1.0.0a2)
- ~~Seed larger batch~~ Done: 129,821 packages (top-15k + 115k deep seed)
- ~~Add pkg_resources auto-fixer~~ Done: 8th fix type
- ~~Cache cleanup~~ Done: sdists deleted after processing, prevents disk fill
- Implement `server/config.py` and `server/deploy.py` for reproducible deployment
- Add `/status/<package>` API endpoint for verified compatibility checks
- Add skip/ignore mechanism for acknowledged-but-won't-fix issues
- Set up monitoring/alerting for server health
- Consider Cloudflare proxy (orange cloud) after SSL is stable
- Reduce processor idle churn (currently restarts every 60s even when queue empty)
- Monitor disk usage as devpi store grows (~0.4MB per fixed package)
- **After first pass**: revisit C-extension packages (numpy, pandas, etc.) — analyze failure reasons, consider build agent with compilers or sourcing pre-built 3.14 wheels
