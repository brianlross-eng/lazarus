"""Analyze remaining failures for fixability."""
import sqlite3
conn = sqlite3.connect("/root/.lazarus/queue.db")

# 1. ImportError inside build:sdist_failed — what modules?
print("=== build:sdist_failed + ImportError (424) — specific modules ===")
rows = conn.execute("""
    SELECT
        CASE
            WHEN last_error LIKE '%No module named ''pip''%' THEN 'pip'
            WHEN last_error LIKE '%No module named ''setuptools%' THEN 'setuptools'
            WHEN last_error LIKE '%pkg_resources%' THEN 'pkg_resources'
            WHEN last_error LIKE '%No module named ''_version''%' THEN '_version'
            WHEN last_error LIKE '%No module named ''versioneer''%' THEN 'versioneer'
            WHEN last_error LIKE '%No module named ''numpy''%' THEN 'numpy'
            WHEN last_error LIKE '%No module named ''Cython''%' OR last_error LIKE '%No module named ''cython''%' THEN 'cython'
            WHEN last_error LIKE '%No module named ''scipy''%' THEN 'scipy'
            WHEN last_error LIKE '%No module named ''torch''%' THEN 'torch'
            WHEN last_error LIKE '%No module named ''sklearn''%' THEN 'sklearn'
            WHEN last_error LIKE '%No module named ''pandas''%' THEN 'pandas'
            WHEN last_error LIKE '%No module named ''pybind11''%' THEN 'pybind11'
            WHEN last_error LIKE '%No module named ''skbuild''%' THEN 'scikit-build'
            WHEN last_error LIKE '%No module named ''distutils''%' THEN 'distutils'
            WHEN last_error LIKE '%No module named ''imp''%' THEN 'imp'
            WHEN last_error LIKE '%No module named ''ConfigParser''%' THEN 'ConfigParser'
            WHEN last_error LIKE '%cannot import name%' THEN 'cannot_import_name'
            ELSE 'other_module'
        END as sub,
        COUNT(*) as cnt
    FROM jobs WHERE status='failed' AND last_error LIKE '%sdist build failed%'
    AND (last_error LIKE '%ImportError%' OR last_error LIKE '%ModuleNotFoundError%')
    GROUP BY sub ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[1]:>4}  {r[0]}")

# 2. What are the "other_module" imports?
print("\n=== other_module samples ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status='failed' AND last_error LIKE '%sdist build failed%'
    AND (last_error LIKE '%ImportError%' OR last_error LIKE '%ModuleNotFoundError%')
    AND last_error NOT LIKE '%pip%'
    AND last_error NOT LIKE '%setuptools%'
    AND last_error NOT LIKE '%pkg_resources%'
    AND last_error NOT LIKE '%_version%'
    AND last_error NOT LIKE '%versioneer%'
    AND last_error NOT LIKE '%numpy%'
    AND last_error NOT LIKE '%Cython%'
    AND last_error NOT LIKE '%cython%'
    AND last_error NOT LIKE '%scipy%'
    AND last_error NOT LIKE '%torch%'
    AND last_error NOT LIKE '%sklearn%'
    AND last_error NOT LIKE '%pandas%'
    AND last_error NOT LIKE '%pybind11%'
    AND last_error NOT LIKE '%skbuild%'
    AND last_error NOT LIKE '%distutils%'
    AND last_error NOT LIKE '%imp%'
    AND last_error NOT LIKE '%ConfigParser%'
    AND last_error NOT LIKE '%cannot import name%'
    ORDER BY RANDOM() LIMIT 10
""").fetchall()
for r in rows:
    # Extract the "No module named 'X'" part
    err = r[2] or ""
    import re
    m = re.search(r"No module named '([^']+)'", err)
    mod = m.group(1) if m else err[-100:]
    print(f"  {r[0]}=={r[1]}: {mod}")

# 3. FileNotFoundError (108) — what files?
print("\n=== build:sdist_failed + FileNotFoundError (108) — samples ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status='failed' AND last_error LIKE '%sdist build failed%'
    AND last_error LIKE '%FileNotFoundError%'
    ORDER BY RANDOM() LIMIT 10
""").fetchall()
for r in rows:
    err = r[2] or ""
    import re
    m = re.search(r"FileNotFoundError.*?'([^']+)'", err)
    if not m:
        m = re.search(r"No such file or directory: '([^']+)'", err)
    fname = m.group(1) if m else err[-100:]
    print(f"  {r[0]}=={r[1]}: {fname}")

# 4. AttributeError (87) — what attrs?
print("\n=== build:sdist_failed + AttributeError (87) — samples ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status='failed' AND last_error LIKE '%sdist build failed%'
    AND last_error LIKE '%AttributeError%'
    ORDER BY RANDOM() LIMIT 10
""").fetchall()
for r in rows:
    err = r[2] or ""
    # Get last 200 chars
    print(f"  {r[0]}=={r[1]}: {err[-150:]}")
    print()

# 5. The "other" 285 — categorize
print("=== 'other' failures sub-breakdown ===")
rows = conn.execute("""
    SELECT
        CASE
            WHEN last_error LIKE '%No such file or directory%cache%' THEN 'cache_miss'
            WHEN last_error LIKE '%is a link to an absolute path%' THEN 'absolute_symlink'
            WHEN last_error LIKE '%Unknown archive format%' THEN 'unknown_archive'
            WHEN last_error LIKE '%Version not found%' THEN 'version_not_found'
            WHEN last_error LIKE '%No sdist%' THEN 'no_sdist'
            WHEN last_error LIKE '%Max attempts%' THEN 'max_attempts'
            ELSE 'misc'
        END as sub,
        COUNT(*) as cnt
    FROM jobs WHERE status='failed'
    AND last_error NOT LIKE '%No sdist%'
    AND last_error NOT LIKE '%unfixed%'
    AND last_error NOT LIKE '%sdist build failed%'
    AND last_error NOT LIKE '%SyntaxError%'
    AND last_error NOT LIKE '%NameError%'
    AND last_error NOT LIKE '%ImportError%'
    AND last_error NOT LIKE '%ModuleNotFoundError%'
    AND last_error NOT LIKE '%AttributeError%'
    AND last_error NOT LIKE '%FileNotFoundError%'
    AND last_error NOT LIKE '%InvalidVersion%'
    AND last_error NOT LIKE '%ValueError%'
    AND last_error NOT LIKE '%TypeError%'
    AND last_error NOT LIKE '%KeyError%'
    AND last_error NOT LIKE '%UnicodeDecodeError%'
    AND last_error NOT LIKE '%codec%'
    AND last_error NOT LIKE '%RuntimeError%'
    AND last_error NOT LIKE '%OSError%'
    AND last_error NOT LIKE '%PermissionError%'
    AND last_error NOT LIKE '%timeout%'
    AND last_error NOT LIKE '%Timeout%'
    GROUP BY sub ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[1]:>4}  {r[0]}")

# 6. get_requires (143) — why can't the backend start?
print("\n=== get_requires_for_build_sdist failures — samples ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status='failed' AND last_error LIKE '%sdist build failed%'
    AND last_error LIKE '%get_requires_for_build_sdist%'
    AND last_error NOT LIKE '%ImportError%'
    AND last_error NOT LIKE '%ModuleNotFoundError%'
    ORDER BY RANDOM() LIMIT 8
""").fetchall()
for r in rows:
    err = r[2][-200:] if r[2] else "None"
    print(f"  {r[0]}=={r[1]}:")
    print(f"    {err}")
    print()

# 7. How many recovered from our retry?
print("=== Retry results ===")
row = conn.execute("""
    SELECT COUNT(*) FROM jobs WHERE status='complete' AND attempts > 1
""").fetchone()
print(f"  Packages recovered by retry: {row[0]}")

row = conn.execute("""
    SELECT COUNT(*) FROM jobs WHERE status='failed' AND attempts > 1
    AND last_error NOT LIKE '%No sdist%'
""").fetchone()
print(f"  Packages retried but still failed: {row[0]}")

pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
in_prog = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='in_progress'").fetchone()[0]
print(f"  Still processing: {pending} pending, {in_prog} in_progress")

conn.close()
