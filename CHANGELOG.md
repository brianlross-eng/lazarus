# Changelog

All notable changes to Lazarus will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [PEP 440](https://peps.python.org/pep-0440/) and [Semantic Versioning](https://semver.org/).

---

## [Unreleased] — toward 1.0.0a2

### Added
- **DevpiUploader** — full devpi upload support with native auth protocol
  (login → session token → X-Devpi-Auth header → multipart file upload)
- **Upload integration in pipeline** — fixed packages now get published to devpi
  after build, completing the fetch → analyze → fix → build → **publish** loop
- **`--upload` CLI flag** — `lazarus admin process --upload` enables publishing
- **`LAZARUS_UPLOAD` env var** — enable uploads via environment
- **`LAZARUS_DEVPI_INDEX` env var** — configure devpi index name
- **Token retry logic** — uploader re-authenticates on 401 (expired tokens)
- **13 new tests** for uploader (init, login, upload, retry, check_exists)

### Changed
- Config defaults: `devpi_url` → `http://localhost:3141`, `devpi_index` → `lazarus/packages`
- Config: added `upload_enabled` flag (default: off, requires explicit opt-in)
- Pipeline: `ProcessResult.dists_uploaded` tracks what was published

---

## [1.0.0a1] — 2026-02-20

First alpha release. End-to-end pipeline operational: fetch → analyze → fix → build,
with a live production server processing packages unattended.

### Added
- **Static analyzer** with 11 compatibility check types for Python 3.14 removals
  - `removed_ast_node` — ast.Num/Str/Bytes/NameConstant/Ellipsis
  - `removed_asyncio_watcher` — child watcher APIs
  - `removed_pkgutil_loader` — find_loader/get_loader
  - `removed_sqlite3_version` — sqlite3.version
  - `removed_urllib_class` — URLopener/FancyURLopener
  - `removed_importlib_abc` — ResourceReader/Traversable
  - `removed_shutil_onerror` — onerror parameter
  - `pathlib_extra_args` — multiple args to relative_to/is_relative_to
  - `removed_pty_function` — master_open/slave_open
  - `deprecated_pkg_resources` — pkg_resources imports
  - `invalid_escape_sequence` — unrecognized backslash escapes in strings
- **Auto-fixer** with 7 mechanical fix handlers (escape sequence fixer uses
  character-by-character state machine)
- **Claude AI fixer** for complex compatibility issues
- **Pipeline orchestrator** — fetch → analyze → fix → build flow with ProcessResult/BatchResult
- **Job queue** — SQLite-backed with WAL mode, atomic claiming, priority ordering
- **Schema migrations** — integer-versioned, forward-only
- **Watchdog supervisor** — monitors stale jobs, auto-restarts processor
- **CLI** — Click-based with `raise/remove/search/list/inspect/pray` + `admin` subcommands
- **PyPI client** — JSON API integration, sdist download/extract (httpx)
- **Top packages seeder** — fetches top-N from hugovk dataset
- **Version rewriter** — PEP 440 `.post314` suffixes
- **Package builder** — sdist/wheel via PEP 517
- **C-extension detection** — `SKIP_BUILD_PACKAGES` frozenset + `_has_c_extensions()` heuristic
- **needs_review workflow** — unfixed AI issues flagged instead of silently completed
- **Two-tier architecture** — server runs `--auto-only`, reviews pulled locally for AI fixing

### Infrastructure
- **Domain**: lazaruspy.org (Cloudflare Registrar)
- **Email**: admin@lazaruspy.org (Cloudflare Email Routing)
- **Server**: Hetzner CX33, Helsinki — Ubuntu 24.04, Python 3.14.3
- **Package index**: https://lazaruspy.org/simple/ (devpi + nginx + Let's Encrypt)
- **systemd services**: devpi, lazarus-processor, lazarus-watchdog, lazarus-seed.timer

### Fixed
- `CompatIssue.line` → `CompatIssue.line_number` attribute reference in pipeline.py

### Batch Results (Top 1,000 PyPI packages)
- 922 already compatible (92.2%)
- 35 auto-fixed (3.5%)
- 43 failed (no sdist / C-extension build issues)

---

## [0.1.0] — 2026-02-18

Initial development version. Core architecture and pipeline scaffolding.

[1.0.0a1]: https://github.com/brianlross-eng/lazarus/compare/1256768...v1.0.0a1
[0.1.0]: https://github.com/brianlross-eng/lazarus/commit/1256768
