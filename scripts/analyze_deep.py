"""Deep analysis of build failure patterns."""
import sqlite3
import re
from collections import Counter

conn = sqlite3.connect("/root/.lazarus/queue.db")
c = conn.cursor()

# What are the setuptools build subprocess errors about?
c.execute(
    "SELECT last_error FROM jobs WHERE status=? AND last_error LIKE ? AND last_error LIKE ?",
    ("failed", "%Backend subprocess%", "%setuptools%"),
)
rows = c.fetchall()
print(f"=== Setuptools build errors ({len(rows)}) ===")
setuptools_cats = Counter()
for (err,) in rows:
    if "pkg_resources" in err:
        continue
    err_lower = err.lower()
    if "no module named" in err_lower:
        m = re.search(r"No module named '([^']+)'", err)
        mod = m.group(1) if m else "?"
        setuptools_cats[f"No module: {mod}"] += 1
    elif "invalid version" in err_lower:
        setuptools_cats["InvalidVersion"] += 1
    elif "filenotfounderror" in err_lower:
        setuptools_cats["FileNotFoundError"] += 1
    elif "syntaxerror" in err_lower:
        setuptools_cats["SyntaxError"] += 1
    elif "importerror" in err_lower:
        m = re.search(r"ImportError: ([^\n]+)", err)
        msg = m.group(1)[:60] if m else "?"
        setuptools_cats[f"ImportError: {msg}"] += 1
    elif "typeerror" in err_lower:
        m = re.search(r"TypeError: ([^\n]+)", err)
        msg = m.group(1)[:60] if m else "?"
        setuptools_cats[f"TypeError: {msg}"] += 1
    elif "attributeerror" in err_lower:
        m = re.search(r"AttributeError: ([^\n]+)", err)
        msg = m.group(1)[:60] if m else "?"
        setuptools_cats[f"AttributeError: {msg}"] += 1
    elif "keyerror" in err_lower:
        setuptools_cats["KeyError"] += 1
    elif "valueerror" in err_lower:
        m = re.search(r"ValueError: ([^\n]+)", err)
        msg = m.group(1)[:60] if m else "?"
        setuptools_cats[f"ValueError: {msg}"] += 1
    elif "oserror" in err_lower or "errno" in err_lower:
        setuptools_cats["OSError"] += 1
    elif "encoding" in err_lower or "codec" in err_lower or "unicode" in err_lower:
        setuptools_cats["Encoding error"] += 1
    elif "timeout" in err_lower:
        setuptools_cats["Timeout"] += 1
    else:
        lines = err.strip().split("\n")
        last_err = lines[-2] if len(lines) >= 2 else lines[-1] if lines else "?"
        setuptools_cats[last_err[:70]] += 1

for cat, count in setuptools_cats.most_common(30):
    print(f"  {cat}: {count}")

# pkg_resources errors
print()
c.execute(
    "SELECT package_name, last_error FROM jobs WHERE status=? AND last_error LIKE ? AND last_error LIKE ?",
    ("failed", "%Backend subprocess%", "%pkg_resources%"),
)
rows = c.fetchall()
print(f"=== pkg_resources build errors ({len(rows)}) ===")
pkg_res_cats = Counter()
for (pkg, err) in rows:
    if "No module named" in err and "pkg_resources" in err:
        pkg_res_cats["No module named pkg_resources"] += 1
    elif "DistributionNotFound" in err:
        pkg_res_cats["DistributionNotFound"] += 1
    elif "VersionConflict" in err:
        pkg_res_cats["VersionConflict"] += 1
    else:
        pkg_res_cats["other"] += 1

for cat, count in pkg_res_cats.most_common():
    print(f"  {cat}: {count}")

# Check updated_at for recent pkg_resources failures
c.execute(
    "SELECT package_name, updated_at FROM jobs WHERE status=? AND last_error LIKE ? ORDER BY updated_at DESC LIMIT 5",
    ("failed", "%No module named%pkg_resources%"),
)
rows = c.fetchall()
print("\n  Recent pkg_resources failures:")
for pkg, updated in rows:
    print(f"    {pkg} (updated: {updated})")

# requirements.txt FileNotFoundError - show some package names
print()
c.execute(
    "SELECT package_name, version FROM jobs WHERE status=? AND last_error LIKE ? AND last_error LIKE ? LIMIT 10",
    ("failed", "%FileNotFoundError%", "%requirements.txt%"),
)
rows = c.fetchall()
print(f"=== Sample requirements.txt failures ===")
for pkg, ver in rows:
    print(f"  {pkg}=={ver}")

# import pip failures
print()
c.execute(
    "SELECT package_name, last_error FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%No module named%pip%"),
)
rows = c.fetchall()
print(f"=== 'import pip' failures ({len(rows)}) ===")
for pkg, err in rows[:10]:
    m = re.search(r"No module named '([^']+)'", err)
    mod = m.group(1) if m else "?"
    print(f"  {pkg}: No module named {mod}")

conn.close()
