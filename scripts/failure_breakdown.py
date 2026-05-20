import sqlite3
import re
from collections import Counter

conn = sqlite3.connect("/root/.lazarus/queue.db")
rows = conn.execute("SELECT last_error FROM jobs WHERE status = 'failed'").fetchall()

categories = Counter()
for (err,) in rows:
    if not err:
        categories["(no error message)"] += 1
    elif "no sdist" in err.lower() or "no suitable sdist" in err:
        categories["no_sdist"] += 1
    elif "unfixed issue" in err:
        # Extract the issue type
        m = re.search(r"unfixed issue\(s\): (\S+)", err)
        issue = m.group(1) if m else "unknown"
        categories[f"unfixed:{issue}"] += 1
    elif "SyntaxError" in err:
        categories["build:SyntaxError"] += 1
    elif "ModuleNotFoundError" in err or "No module named" in err:
        m = re.search(r"No module named ['\"]?(\S+?)['\"]?[\s\n]", err)
        mod = m.group(1) if m else "unknown"
        categories[f"build:NoModule:{mod}"] += 1
    elif "NameError" in err:
        m = re.search(r"name ['\"](\w+)['\"]", err)
        name = m.group(1) if m else "unknown"
        categories[f"build:NameError:{name}"] += 1
    elif "InvalidVersion" in err:
        categories["build:InvalidVersion"] += 1
    elif "FileNotFoundError" in err:
        categories["build:FileNotFoundError"] += 1
    elif "AttributeError" in err:
        categories["build:AttributeError"] += 1
    elif "ValueError" in err:
        categories["build:ValueError"] += 1
    elif "ImportError" in err:
        categories["build:ImportError"] += 1
    elif "TypeError" in err:
        categories["build:TypeError"] += 1
    elif "KeyError" in err:
        categories["build:KeyError"] += 1
    elif "pkg_resources" in err:
        categories["build:pkg_resources"] += 1
    elif "sdist build failed" in err:
        categories["build:other"] += 1
    elif "timeout" in err.lower() or "timed out" in err.lower():
        categories["timeout"] += 1
    else:
        categories["other"] += 1

# Also check needs_review
nr_rows = conn.execute("SELECT last_error FROM jobs WHERE status = 'needs_review'").fetchall()
nr_categories = Counter()
for (err,) in nr_rows:
    if not err:
        nr_categories["(no error)"] += 1
    elif "unfixed issue" in err:
        m = re.search(r"unfixed issue\(s\): (\S+)", err)
        issue = m.group(1) if m else "unknown"
        nr_categories[f"unfixed:{issue}"] += 1
    else:
        nr_categories["other"] += 1

conn.close()

print(f"=== FAILED ({sum(categories.values())} total) ===")
for cat, count in categories.most_common():
    print(f"  {count:6d}  {cat}")

print(f"\n=== NEEDS_REVIEW ({sum(nr_categories.values())} total) ===")
for cat, count in nr_categories.most_common():
    print(f"  {count:6d}  {cat}")
