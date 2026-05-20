"""Analyze failure patterns in the Lazarus queue DB."""
import sqlite3
import re
import sys
from collections import Counter


def analyze(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # FileNotFoundError analysis
    c.execute(
        "SELECT last_error FROM jobs WHERE status=? AND last_error LIKE ?",
        ("failed", "%FileNotFoundError%"),
    )
    rows = c.fetchall()
    missing_files = Counter()
    for (err,) in rows:
        m = re.search(r"No such file or directory: '([^']+)'", err)
        if m:
            path = m.group(1)
            fname = path.rstrip("/").split("/")[-1]
            missing_files[fname] += 1
        elif "Forced include not found" in err:
            missing_files["Forced include (airflow etc)"] += 1
        else:
            missing_files["other"] += 1

    print(f"=== FileNotFoundError ({len(rows)} packages) ===")
    for fname, count in missing_files.most_common(25):
        print(f"  {fname}: {count}")

    # ModuleNotFoundError analysis
    c.execute(
        "SELECT last_error FROM jobs WHERE status=? AND last_error LIKE ?",
        ("failed", "%ModuleNotFoundError%"),
    )
    rows = c.fetchall()
    missing_modules = Counter()
    for (err,) in rows:
        m = re.search(r"No module named '([^']+)'", err)
        if m:
            mod = m.group(1).split(".")[0]
            missing_modules[mod] += 1
        else:
            missing_modules["other"] += 1

    print(f"\n=== ModuleNotFoundError ({len(rows)} packages) ===")
    for mod, count in missing_modules.most_common(25):
        print(f"  {mod}: {count}")

    # Build subprocess errors
    c.execute(
        "SELECT last_error FROM jobs WHERE status=? AND last_error LIKE ?",
        ("failed", "%Backend subprocess%"),
    )
    rows = c.fetchall()
    build_errors = Counter()
    for (err,) in rows:
        if "maturin" in err.lower() or "rust" in err.lower() or "cargo" in err.lower():
            build_errors["maturin/Rust"] += 1
        elif "hatchling" in err.lower() or "hatch" in err.lower():
            build_errors["hatchling"] += 1
        elif "flit" in err.lower():
            build_errors["flit"] += 1
        elif "cmake" in err.lower() or "scikit-build" in err.lower():
            build_errors["cmake/scikit-build"] += 1
        elif "mesonpy" in err.lower() or "meson" in err.lower():
            build_errors["meson"] += 1
        elif "poetry" in err.lower():
            build_errors["poetry"] += 1
        elif "pdm" in err.lower():
            build_errors["pdm"] += 1
        elif "pkg_resources" in err:
            build_errors["pkg_resources"] += 1
        elif "setuptools" in err:
            build_errors["setuptools"] += 1
        else:
            build_errors["other"] += 1

    print(f"\n=== Build subprocess errors ({len(rows)} packages) ===")
    for cat, count in build_errors.most_common(25):
        print(f"  {cat}: {count}")

    # SyntaxError analysis
    c.execute(
        "SELECT package_name, last_error FROM jobs WHERE status=? AND last_error LIKE ?",
        ("failed", "%SyntaxError%"),
    )
    rows = c.fetchall()
    print(f"\n=== SyntaxError ({len(rows)} packages) ===")
    for pkg, err in rows[:10]:
        # Find the SyntaxError line
        m = re.search(r"SyntaxError: (.+)", err)
        reason = m.group(1)[:80] if m else "unknown"
        print(f"  {pkg}: {reason}")

    # ImportError analysis
    c.execute(
        "SELECT last_error FROM jobs WHERE status=? AND last_error LIKE ? AND last_error NOT LIKE ?",
        ("failed", "%ImportError%", "%ModuleNotFoundError%"),
    )
    rows = c.fetchall()
    import_errors = Counter()
    for (err,) in rows:
        m = re.search(r"ImportError: (.+?)(?:\n|$)", err)
        if m:
            import_errors[m.group(1)[:60]] += 1
        else:
            import_errors["other"] += 1

    print(f"\n=== ImportError (not ModuleNotFoundError) ({len(rows)} packages) ===")
    for msg, count in import_errors.most_common(15):
        print(f"  {msg}: {count}")

    # InvalidVersion analysis
    c.execute(
        "SELECT package_name, last_error FROM jobs WHERE status=? AND last_error LIKE ?",
        ("failed", "%InvalidVersion%"),
    )
    rows = c.fetchall()
    print(f"\n=== InvalidVersion ({len(rows)} packages) ===")
    for pkg, err in rows[:10]:
        m = re.search(r"InvalidVersion\(.(.+?).\)", err)
        ver = m.group(1)[:40] if m else "unknown"
        print(f"  {pkg}: {ver}")

    # Overall failure summary (excluding no-sdist)
    c.execute(
        "SELECT COUNT(*) FROM jobs WHERE status=? AND last_error NOT LIKE ?",
        ("failed", "%No sdist%"),
    )
    non_sdist_failures = c.fetchone()[0]

    c.execute(
        "SELECT COUNT(*) FROM jobs WHERE status=? AND last_error LIKE ?",
        ("failed", "%No sdist%"),
    )
    no_sdist = c.fetchone()[0]

    print(f"\n=== Summary ===")
    print(f"  No sdist available: {no_sdist}")
    print(f"  Other failures: {non_sdist_failures}")

    conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/root/.lazarus/queue.db"
    analyze(db_path)
