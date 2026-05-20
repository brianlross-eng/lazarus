"""Identify which failure categories can be fixed by Lazarus pipeline changes."""
import sqlite3
import re
from collections import Counter

conn = sqlite3.connect("/root/.lazarus/queue.db")
c = conn.cursor()

# 1. requirements.txt missing (201 packages) - can we create empty file?
print("=" * 60)
print("1. REQUIREMENTS.TXT MISSING (potential fix: create empty file)")
print("=" * 60)
c.execute(
    "SELECT package_name, last_error FROM jobs WHERE status=? AND last_error LIKE ? AND last_error LIKE ?",
    ("failed", "%FileNotFoundError%", "%requirements.txt%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages")
# Check if these are during build_sdist or get_requires
build_phase = Counter()
for pkg, err in rows:
    if "get_requires_for_build_sdist" in err:
        build_phase["get_requires_for_build_sdist"] += 1
    elif "build_sdist" in err:
        build_phase["build_sdist"] += 1
    elif "get_requires_for_build_wheel" in err:
        build_phase["get_requires_for_build_wheel"] += 1
    else:
        build_phase["other"] += 1
for phase, count in build_phase.most_common():
    print(f"   Phase: {phase}: {count}")

# 2. Missing README files (33+11+8+4+4+3+2+2 = 67)
print()
print("=" * 60)
print("2. MISSING README/DOCS FILES (potential fix: create empty file)")
print("=" * 60)
readme_patterns = ["%README%", "%HISTORY%", "%CHANGELOG%"]
total = 0
for pat in readme_patterns:
    c.execute(
        "SELECT COUNT(*) FROM jobs WHERE status=? AND last_error LIKE ? AND last_error LIKE ?",
        ("failed", "%FileNotFoundError%", pat),
    )
    count = c.fetchone()[0]
    total += count
    print(f"   {pat}: {count}")
print(f"   Total: {total}")

# 3. VERSION file missing (17+6 = 23)
print()
print("=" * 60)
print("3. MISSING VERSION FILE (potential fix: create with our version)")
print("=" * 60)
c.execute(
    "SELECT COUNT(*) FROM jobs WHERE status=? AND last_error LIKE ? AND (last_error LIKE ? OR last_error LIKE ?)",
    ("failed", "%FileNotFoundError%", "%VERSION%", "%version.txt%"),
)
count = c.fetchone()[0]
print(f"   Count: {count}")

# 4. NameError: name 'imp' is not defined (11) - this is a Python 3.14 compat issue!
print()
print("=" * 60)
print("4. NAME 'imp' NOT DEFINED (Python 3.14 removed imp module!)")
print("=" * 60)
c.execute(
    "SELECT package_name FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%name 'imp' is not defined%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages")
for (pkg,) in rows[:15]:
    print(f"   - {pkg}")

# 5. ast.Constant.s attribute removed in 3.14
print()
print("=" * 60)
print("5. 'Constant' object has no attribute 's' (ast.Constant.s removed!)")
print("=" * 60)
c.execute(
    "SELECT package_name FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%Constant%attribute%s%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages")
for (pkg,) in rows[:15]:
    print(f"   - {pkg}")

# 6. NameError: execfile (Python 2 leftover)
print()
print("=" * 60)
print("6. NAME 'execfile' NOT DEFINED (Python 2 leftover)")
print("=" * 60)
c.execute(
    "SELECT package_name FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%name 'execfile' is not defined%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages")
for (pkg,) in rows[:15]:
    print(f"   - {pkg}")

# 7. NameError: name 'file' not defined (Python 2 leftover)
print()
print("=" * 60)
print("7. NAME 'file' NOT DEFINED (Python 2 builtin removed)")
print("=" * 60)
c.execute(
    "SELECT package_name FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%name 'file' is not defined%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages")
for (pkg,) in rows[:15]:
    print(f"   - {pkg}")

# 8. import pip in setup.py
print()
print("=" * 60)
print("8. IMPORT PIP IN SETUP.PY (deprecated practice)")
print("=" * 60)
c.execute(
    "SELECT package_name FROM jobs WHERE status=? AND last_error LIKE ? AND last_error NOT LIKE ?",
    ("failed", "%No module named%pip%", "%pipreqs%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages (excluding pipreqs)")
for (pkg,) in rows[:10]:
    print(f"   - {pkg}")

# 9. pyproject.toml version validation errors
print()
print("=" * 60)
print("9. PYPROJECT.TOML VERSION VALIDATION (our rewrite may cause this)")
print("=" * 60)
c.execute(
    "SELECT package_name, last_error FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%invalid pyproject.toml config%version%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages")
for pkg, err in rows[:5]:
    m = re.search(r"ValueError: ([^\n]+)", err)
    msg = m.group(1)[:80] if m else "?"
    print(f"   - {pkg}: {msg}")

# 10. 'NoneType' object has no attribute 'group' - likely regex match failure from our rewrite?
print()
print("=" * 60)
print("10. 'NoneType' has no attribute 'group' (possible rewrite issue)")
print("=" * 60)
c.execute(
    "SELECT package_name, last_error FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%NoneType%attribute%group%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages")
for pkg, err in rows[:5]:
    # Find what file the error is in
    m = re.search(r'File "([^"]+)", line \d+', err)
    fpath = m.group(1) if m else "?"
    print(f"   - {pkg}: {fpath.split('/')[-1]}")

# 11. Missing importlib
print()
print("=" * 60)
print("11. NAME 'importlib' NOT DEFINED (missing import)")
print("=" * 60)
c.execute(
    "SELECT package_name FROM jobs WHERE status=? AND last_error LIKE ?",
    ("failed", "%name 'importlib' is not defined%"),
)
rows = c.fetchall()
print(f"   Count: {len(rows)} packages")
for (pkg,) in rows[:10]:
    print(f"   - {pkg}")

# Summary of potentially fixable
print()
print("=" * 60)
print("SUMMARY OF POTENTIALLY FIXABLE CATEGORIES")
print("=" * 60)
fixable = {
    "requirements.txt missing → create empty": 201,
    "README/docs missing → create empty": 67,
    "VERSION file missing → create with version": 23,
    "import pip → remove/wrap": 48,
    "'imp' not defined → 3.14 compat issue": 11,
    "ast.Constant.s removed → 3.14 compat": 10,
    "'execfile' not defined → Python 2": 9,
    "'file' not defined → Python 2": 5,
    "pyproject.toml version → rewrite issue?": 11,
    "'importlib' not defined → missing import": 4,
}
total = sum(fixable.values())
for desc, count in sorted(fixable.items(), key=lambda x: -x[1]):
    print(f"  {count:4d}  {desc}")
print(f"  ----")
print(f"  {total:4d}  TOTAL potentially fixable")

conn.close()
