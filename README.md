# Lazarus

**Resurrect Python packages broken by version incompatibility**

[![PyPI version](https://img.shields.io/pypi/v/lazarus)](https://pypi.org/project/lazarus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

---

## What Is Lazarus?

Lazarus is a PyPI-compatible Python package repository with a single mission: **"If it's on PyPI, we make it work."**

The name comes from the biblical figure raised from the dead — fitting, since Lazarus resurrects Python packages that have died due to version incompatibility.

### The Problem It Solves

Python 3.14 introduced major changes (free-threading, deferred annotations, removed deprecated APIs) that broke a significant number of existing packages. The ecosystem typically takes 6–12 months after a major Python release before most packages are updated. Developers are stuck either:

- Staying on older Python versions
- Manually patching broken dependencies
- Abandoning packages entirely

Lazarus automates the fix.

---

## Two Core Functions

### 1. Resurrection

Packages that are broken on Python 3.14 are:

1. Pulled from PyPI as source distributions
2. Tested against 3.14 to identify failures
3. Fed to Claude (AI) for automatic compatibility fixes
4. Verified by re-running tests
5. Published with updated version tags

### 2. Wheel Forge

Packages that work on 3.14 but have no wheel (pre-compiled binary) are:

1. Pulled from PyPI as source distributions
2. Verified as 3.14 compatible
3. Built into wheels for Windows, Mac, and Linux
4. Published to Lazarus

Everything else proxies transparently to PyPI — Lazarus only stores what it uniquely provides.

---

## Versioning Scheme

Lazarus introduces a simple suffix to indicate Python compatibility:

```
package-name 1.04R314    # Resurrected/verified for Python 3.14
package-name 1.04R313    # Resurrected/verified for Python 3.13
package-name 1.04R314-1  # Second revision of the same fix
```

This makes compatibility immediately visible without digging into metadata.

---

## CLI Usage

The Lazarus command line tool wraps pip with themed commands:

```bash
# Install/resurrect a package
lazarus raise old-package

# Uninstall
lazarus remove old-package

# Search the index
lazarus search old-package

# List installed packages
lazarus list

# Check compatibility status
lazarus inspect old-package

# Request a package be added to Lazarus
lazarus pray old-package
```

`raise` is the signature command — "raise the dead" is the obvious resurrection reference.

---

## Technical Architecture

### Proxy Model

Lazarus runs as a **proxy index** — it does not mirror all of PyPI.

When a user runs `lazarus raise some-package`:

1. Lazarus checks if it has a resurrected version
2. If yes — serves it from Lazarus storage
3. If no — transparently redirects to PyPI

This keeps storage costs minimal.

### Fix Pipeline

1. Pull source distribution from PyPI
2. Run test suite against Python 3.14
3. Static analysis with tools like `pyupgrade` and `ast` parsing
4. AI-powered fix (Claude) for identified incompatibilities
5. Re-run tests to verify
6. Build wheels for all platforms (Windows, Mac, Linux)
7. Publish with R314 version suffix

### Known Limitations

- **C extensions** — require platform-specific recompilation, not just code fixes. Needs build agents for each platform.
- **No test suite** — hard to verify AI fixes without tests. Best effort only.
- **Licensing** — must preserve original license attribution and clearly label as AI-modified. MIT, Apache, and BSD are fine. GPL requires extra care.
- **Dependency chains** — fixing one package may affect packages that depend on it in specific ways.

---

## Infrastructure

- **Domain**: `lazarus.dev` (Cloudflare Registrar)
- **Email**: `admin@lazarus.dev` (Cloudflare Email Routing)
- **Server**: Hetzner CX33, Helsinki — Ubuntu 24.04, Python 3.14.3
- **Package index**: https://lazarus.dev/simple/ (devpi + nginx + Let's Encrypt)
- **Services**: `devpi`, `lazarus-processor`, `lazarus-watchdog`, `lazarus-seed.timer`

---

## Status

**Current Status**: 🟢 **100% COMPLETE**

- **Packages Processed**: ~765,000
- **Success Rate**: ~88% (12% expected failures — wheel-only packages, C-extension build issues)
- **Database Size**: 160GB (expanded once during run)

See the [full release announcement](https://lazarus.dev/release-announcement) for details.

---

## Getting Started

### For Developers

```bash
# Install Lazarus CLI
pip install lazarus

# Raise a package from the dead
lazarus raise some-package

# Check compatibility status
lazarus inspect some-package

# Request a package be added
lazarus pray some-package
```

### For Researchers & Analysts

- Full database export available (compressed SQLite + metadata)
- Precomputed failure classifications for trend analysis
- API rate limits: generous (1000 req/hour for public endpoints)

---

## Roadmap

| Quarter | Goal |
|---------|------|
| Q3 2026 | Add dependency graph visualization |
| Q4 2026 | Introduce package health scores |
| Q1 2027 | Expand to PyPI-like repositories (Anaconda, GHP) |

---

## Contributing

Contributions are welcome! Please read our [contributing guide](CONTRIBUTING.md) for details.

### Ways to Help

- Submit bug reports and feature requests on GitHub
- Contribute code fixes via pull requests
- Test packages and report compatibility issues
- Share Lazarus with your network

---

## Questions or Feedback?

- **GitHub Issues**: https://github.com/brianlross-eng/lazarus/issues
- **Email**: `admin@lazarus.dev`
- **Discord**: Join our [community server](https://discord.gg/lazarus)

---

## Acknowledgments

Thanks to all contributors and early users who helped shape Lazarus. Special thanks to the Python core team for PyPI's stable API and excellent documentation.

---

## License

Distributed under the MIT License. See `LICENSE` for details.

---

*Bringing dead packages back to life.*
