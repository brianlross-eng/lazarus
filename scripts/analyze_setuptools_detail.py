"""Break down the 859 setuptools build errors to find fixable ones."""
import sqlite3
import re
from collections import Counter

conn = sqlite3.connect("/root/.lazarus/queue.db")
c = conn.cursor()

c.execute(
    "SELECT last_error FROM jobs WHERE status=? AND last_error LIKE ? AND last_error LIKE ? AND last_error NOT LIKE ?",
    ("failed", "%Backend subprocess%", "%setuptools%", "%pkg_resources%"),
)
rows = c.fetchall()

cats = Counter()
for (err,) in rows:
    err_lower = err.lower()
    if "filenotfounderror" in err_lower:
        cats["FileNotFoundError (in build)"] += 1
    elif "no module named" in err_lower:
        m = re.search(r"No module named '([^']+)'", err)
        mod = m.group(1).split(".")[0] if m else "?"
        cats[f"No module: {mod}"] += 1
    elif "invalid version" in err_lower:
        cats["InvalidVersion"] += 1
    elif "syntaxerror" in err_lower:
        cats["SyntaxError"] += 1
    elif "importerror" in err_lower:
        m = re.search(r"ImportError: ([^\n]+)", err)
        msg = m.group(1)[:50] if m else "?"
        cats[f"ImportError: {msg}"] += 1
    elif "nameerror" in err_lower:
        m = re.search(r"NameError: ([^\n]+)", err)
        msg = m.group(1)[:50] if m else "?"
        cats[f"NameError: {msg}"] += 1
    elif "typeerror" in err_lower:
        m = re.search(r"TypeError: ([^\n]+)", err)
        msg = m.group(1)[:50] if m else "?"
        cats[f"TypeError: {msg}"] += 1
    elif "attributeerror" in err_lower:
        m = re.search(r"AttributeError: ([^\n]+)", err)
        msg = m.group(1)[:50] if m else "?"
        cats[f"AttributeError: {msg}"] += 1
    elif "valueerror" in err_lower:
        m = re.search(r"ValueError: ([^\n]+)", err)
        msg = m.group(1)[:50] if m else "?"
        cats[f"ValueError: {msg}"] += 1
    elif "encoding" in err_lower or "codec" in err_lower or "unicode" in err_lower:
        cats["Encoding error"] += 1
    elif "keyerror" in err_lower:
        cats["KeyError"] += 1
    elif "oserror" in err_lower:
        cats["OSError"] += 1
    elif "timeout" in err_lower:
        cats["Timeout"] += 1
    else:
        lines = err.strip().split("\n")
        last_line = lines[-2] if len(lines) >= 2 else lines[-1]
        cats[last_line.strip()[:60]] += 1

print(f"=== Setuptools build errors breakdown ({len(rows)} total) ===")
for cat, count in cats.most_common(40):
    print(f"  {count:4d}  {cat}")

# pkg_resources specifically
print()
c.execute(
    "SELECT last_error FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%pkg_resources%"),
)
rows = c.fetchall()
pkg_cats = Counter()
for (err,) in rows:
    if "No module named" in err and "pkg_resources" in err:
        pkg_cats["No module named pkg_resources"] += 1
    elif "DistributionNotFound" in err:
        pkg_cats["DistributionNotFound"] += 1
    elif "VersionConflict" in err:
        pkg_cats["VersionConflict"] += 1
    elif "cannot import name" in err:
        m = re.search(r"cannot import name '([^']+)'", err)
        name = m.group(1) if m else "?"
        pkg_cats[f"cannot import name '{name}'"] += 1
    else:
        pkg_cats["other pkg_resources"] += 1

print(f"=== pkg_resources errors ({len(rows)} total) ===")
for cat, count in pkg_cats.most_common():
    print(f"  {count:4d}  {cat}")

# requirements.txt still failing - why?
print()
c.execute(
    "SELECT package_name, last_error FROM jobs WHERE status=? AND last_error LIKE ? AND last_error LIKE ?",
    ("failed", "%FileNotFoundError%", "%requirements.txt%"),
)
rows = c.fetchall()
print(f"=== requirements.txt still failing ({len(rows)}) - samples ===")
for pkg, err in rows[:5]:
    # Find the file path
    m = re.search(r"No such file or directory: '([^']+)'", err)
    path = m.group(1) if m else "?"
    print(f"  {pkg}: {path}")

conn.close()
