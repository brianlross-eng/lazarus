"""Deep dive into failure categories."""
import sqlite3

conn = sqlite3.connect("/root/.lazarus/queue.db")

# ImportError sub-breakdown
print("=== ImportError - specific modules ===")
rows = conn.execute("""
    SELECT
        CASE
            WHEN last_error LIKE '%No module named ''pip''%' THEN 'NoModule: pip'
            WHEN last_error LIKE '%No module named ''setuptools%' THEN 'NoModule: setuptools.*'
            WHEN last_error LIKE '%pkg_resources%' THEN 'ImportError: pkg_resources'
            WHEN last_error LIKE '%No module named ''_version''%' OR last_error LIKE '%No module named ''version''%' THEN 'NoModule: _version'
            ELSE 'other_import'
        END as sub,
        COUNT(*) as cnt
    FROM jobs WHERE status = 'failed'
    AND (last_error LIKE '%ImportError%' OR last_error LIKE '%ModuleNotFoundError%')
    AND last_error NOT LIKE '%No sdist%'
    GROUP BY sub ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[1]:>4}  {r[0]}")

# AttributeError samples
print("\n=== AttributeError (88) - samples ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status = 'failed' AND last_error LIKE '%AttributeError%'
    ORDER BY RANDOM() LIMIT 5
""").fetchall()
for r in rows:
    err = r[2][-250:] if r[2] else "None"
    print(f"--- {r[0]}=={r[1]} ---")
    print(err)
    print()

# Version rewrite SyntaxErrors
print("=== SyntaxError caused by version rewrite ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status = 'failed' AND last_error LIKE '%SyntaxError%' AND last_error LIKE '%post314%'
""").fetchall()
print(f"Count: {len(rows)}")
for r in rows:
    err = r[2][-300:] if r[2] else "None"
    print(f"--- {r[0]}=={r[1]} ---")
    print(err)
    print()

# NameError specific breakdown
print("=== NameError - specific names ===")
rows = conn.execute("""
    SELECT
        CASE
            WHEN last_error LIKE '%pkg_resources%' THEN 'pkg_resources'
            WHEN last_error LIKE '%file%not defined%' THEN 'file (py2 builtin)'
            WHEN last_error LIKE '%apply%not defined%' THEN 'apply (py2 builtin)'
            WHEN last_error LIKE '%importlib%not defined%' THEN 'importlib (missing import)'
            WHEN last_error LIKE '%execfile%' THEN 'execfile'
            ELSE 'other'
        END as sub,
        COUNT(*) as cnt
    FROM jobs WHERE status = 'failed' AND last_error LIKE '%NameError%'
    GROUP BY sub ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[1]:>4}  {r[0]}")

# build:sdist_failed - what errors?
print("\n=== build:sdist_failed (409) - last 200 chars samples ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status = 'failed' AND last_error LIKE '%sdist build failed%'
    AND last_error NOT LIKE '%SyntaxError%' AND last_error NOT LIKE '%NameError%'
    AND last_error NOT LIKE '%ImportError%' AND last_error NOT LIKE '%ModuleNotFoundError%'
    AND last_error NOT LIKE '%AttributeError%' AND last_error NOT LIKE '%FileNotFoundError%'
    ORDER BY RANDOM() LIMIT 8
""").fetchall()
for r in rows:
    err = r[2][-200:] if r[2] else "None"
    print(f"--- {r[0]}=={r[1]} ---")
    print(err)
    print()

conn.close()
