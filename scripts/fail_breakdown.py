"""Breakdown of current failure categories."""
import sqlite3
conn = sqlite3.connect("/root/.lazarus/queue.db")

print("=== Failed jobs by error category ===")
rows = conn.execute("""
    SELECT
        CASE
            WHEN last_error LIKE '%No sdist%' THEN 'no_sdist'
            WHEN last_error LIKE '%unfixed%syntax_error%' THEN 'unfixed:syntax_error'
            WHEN last_error LIKE '%unfixed%deprecated_pkg_resources%' THEN 'unfixed:pkg_resources'
            WHEN last_error LIKE '%unfixed%removed_urllib_class%' THEN 'unfixed:urllib_class'
            WHEN last_error LIKE '%unfixed%removed_asyncio_watcher%' THEN 'unfixed:asyncio_watcher'
            WHEN last_error LIKE '%unfixed%pathlib_extra_args%' THEN 'unfixed:pathlib_args'
            WHEN last_error LIKE '%unfixed%' THEN 'unfixed:other'
            WHEN last_error LIKE '%sdist build failed%' THEN 'build:sdist_failed'
            WHEN last_error LIKE '%SyntaxError%' THEN 'SyntaxError'
            WHEN last_error LIKE '%NameError%' THEN 'NameError'
            WHEN last_error LIKE '%ImportError%' OR last_error LIKE '%ModuleNotFoundError%' THEN 'ImportError'
            WHEN last_error LIKE '%AttributeError%' THEN 'AttributeError'
            WHEN last_error LIKE '%FileNotFoundError%' THEN 'FileNotFoundError'
            WHEN last_error LIKE '%InvalidVersion%' OR last_error LIKE '%InvalidWheelFilename%' THEN 'InvalidVersion'
            WHEN last_error LIKE '%ValueError%' THEN 'ValueError'
            WHEN last_error LIKE '%TypeError%' THEN 'TypeError'
            WHEN last_error LIKE '%KeyError%' THEN 'KeyError'
            WHEN last_error LIKE '%UnicodeDecodeError%' OR last_error LIKE '%codec%' THEN 'encoding'
            WHEN last_error LIKE '%RuntimeError%' THEN 'RuntimeError'
            WHEN last_error LIKE '%OSError%' OR last_error LIKE '%PermissionError%' THEN 'OSError'
            WHEN last_error LIKE '%timeout%' OR last_error LIKE '%Timeout%' THEN 'timeout'
            ELSE 'other'
        END as cat,
        COUNT(*) as cnt
    FROM jobs WHERE status = 'failed'
    GROUP BY cat ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[1]:>6}  {r[0]}")

non_sdist = sum(r[1] for r in rows if r[0] != 'no_sdist')
print(f"\nNon-no_sdist failures: {non_sdist}")

pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
in_prog = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='in_progress'").fetchone()[0]
complete = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='complete'").fetchone()[0]
print(f"Still processing: {pending} pending, {in_prog} in_progress")
print(f"Complete: {complete}")

print("\n=== build:sdist_failed sub-breakdown ===")
rows = conn.execute("""
    SELECT
        CASE
            WHEN last_error LIKE '%SyntaxError%' THEN 'SyntaxError'
            WHEN last_error LIKE '%NameError%' THEN 'NameError'
            WHEN last_error LIKE '%ImportError%' OR last_error LIKE '%ModuleNotFoundError%' THEN 'ImportError'
            WHEN last_error LIKE '%AttributeError%' THEN 'AttributeError'
            WHEN last_error LIKE '%FileNotFoundError%' THEN 'FileNotFoundError'
            WHEN last_error LIKE '%pkg_resources%' THEN 'pkg_resources'
            WHEN last_error LIKE '%InvalidVersion%' THEN 'InvalidVersion'
            WHEN last_error LIKE '%ValueError%' THEN 'ValueError'
            WHEN last_error LIKE '%TypeError%' THEN 'TypeError'
            WHEN last_error LIKE '%encoding%' OR last_error LIKE '%codec%' THEN 'encoding'
            WHEN last_error LIKE '%KeyError%' THEN 'KeyError'
            WHEN last_error LIKE '%get_requires_for_build_sdist%' THEN 'get_requires'
            WHEN last_error LIKE '%RuntimeError%' THEN 'RuntimeError'
            ELSE 'other_build'
        END as sub,
        COUNT(*) as cnt
    FROM jobs WHERE status='failed' AND last_error LIKE '%sdist build failed%'
    GROUP BY sub ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[1]:>4}  {r[0]}")

print("\n=== NameError details ===")
rows = conn.execute("""
    SELECT
        CASE
            WHEN last_error LIKE '%name ''file''%' THEN 'file'
            WHEN last_error LIKE '%name ''pkg_resources''%' THEN 'pkg_resources'
            WHEN last_error LIKE '%name ''reload''%' THEN 'reload'
            WHEN last_error LIKE '%name ''execfile''%' THEN 'execfile'
            WHEN last_error LIKE '%name ''raw_input''%' THEN 'raw_input'
            WHEN last_error LIKE '%name ''unicode''%' THEN 'unicode'
            WHEN last_error LIKE '%name ''basestring''%' THEN 'basestring'
            WHEN last_error LIKE '%name ''imp''%' THEN 'imp'
            WHEN last_error LIKE '%name ''xrange''%' THEN 'xrange'
            WHEN last_error LIKE '%name ''long''%' THEN 'long'
            ELSE 'other'
        END as sub,
        COUNT(*) as cnt
    FROM jobs WHERE status='failed' AND last_error LIKE '%NameError%'
    AND last_error NOT LIKE '%unfixed%'
    GROUP BY sub ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[1]:>4}  {r[0]}")

print("\n=== ImportError details ===")
rows = conn.execute("""
    SELECT
        CASE
            WHEN last_error LIKE '%No module named ''pip''%' THEN 'pip'
            WHEN last_error LIKE '%No module named%setuptools%' THEN 'setuptools'
            WHEN last_error LIKE '%pkg_resources%' THEN 'pkg_resources'
            WHEN last_error LIKE '%No module named ''_version''%' OR last_error LIKE '%No module named ''version''%' THEN '_version'
            WHEN last_error LIKE '%No module named%versioneer%' THEN 'versioneer'
            WHEN last_error LIKE '%No module named%numpy%' THEN 'numpy'
            WHEN last_error LIKE '%No module named%cython%' OR last_error LIKE '%No module named%Cython%' THEN 'cython'
            WHEN last_error LIKE '%No module named%scipy%' THEN 'scipy'
            ELSE 'other'
        END as sub,
        COUNT(*) as cnt
    FROM jobs WHERE status='failed'
    AND (last_error LIKE '%ImportError%' OR last_error LIKE '%ModuleNotFoundError%')
    AND last_error NOT LIKE '%unfixed%'
    GROUP BY sub ORDER BY cnt DESC
""").fetchall()
for r in rows:
    print(f"  {r[1]:>4}  {r[0]}")

print("\n=== unfixed:pkg_resources samples ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status='failed' AND last_error LIKE '%unfixed%deprecated_pkg_resources%'
    ORDER BY RANDOM() LIMIT 5
""").fetchall()
for r in rows:
    print(f"  {r[0]}=={r[1]}: {r[2][:120]}")

print("\n=== 'other' category samples ===")
rows = conn.execute("""
    SELECT package_name, version, last_error FROM jobs
    WHERE status='failed'
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
    ORDER BY RANDOM() LIMIT 10
""").fetchall()
for r in rows:
    err = r[2][:150] if r[2] else "None"
    print(f"  {r[0]}=={r[1]}: {err}")

conn.close()
