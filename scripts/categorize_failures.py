"""Categorize all failed jobs for AI fixability analysis."""
import sqlite3
import re
from collections import Counter

conn = sqlite3.connect("/root/.lazarus/queue.db")
c = conn.cursor()

c.execute("SELECT package_name, last_error FROM jobs WHERE status='failed'")
rows = c.fetchall()

cats = Counter()
for pkg, err in rows:
    if not err:
        cats["no error msg"] += 1
        continue
    el = err.lower()
    if "no sdist" in el or "could not find sdist" in el or "no compatible sdist" in el:
        cats["no_sdist"] += 1
    elif "syntaxerror" in el:
        cats["SyntaxError"] += 1
    elif "filenotfounderror" in el:
        cats["FileNotFoundError"] += 1
    elif "no module named" in el:
        m = re.search(r"No module named '([^']+)'", err)
        mod = m.group(1).split(".")[0] if m else "?"
        cats["NoModule:" + mod] += 1
    elif "invalidversion" in el or "invalid version" in el:
        cats["InvalidVersion"] += 1
    elif "nameerror" in el:
        m = re.search(r"NameError: name '([^']+)'", err)
        name = m.group(1) if m else "?"
        cats["NameError:" + name] += 1
    elif "importerror" in el:
        cats["ImportError"] += 1
    elif "typeerror" in el:
        cats["TypeError"] += 1
    elif "attributeerror" in el:
        cats["AttributeError"] += 1
    elif "valueerror" in el:
        cats["ValueError"] += 1
    elif "keyerror" in el:
        cats["KeyError"] += 1
    elif "pkg_resources" in el:
        cats["pkg_resources"] += 1
    elif "maturin" in el or "cargo" in el or "rust" in el:
        cats["Rust/maturin"] += 1
    elif "cmake" in el or "meson" in el:
        cats["cmake/meson"] += 1
    elif "encoding" in el or "codec" in el or "unicode" in el:
        cats["encoding"] += 1
    elif "timeout" in el:
        cats["timeout"] += 1
    elif "oserror" in el:
        cats["OSError"] += 1
    elif "oom" in el or "memory" in el:
        cats["OOM"] += 1
    else:
        cats["other"] += 1

print(f"Total failed: {len(rows)}")
print()
for cat, count in cats.most_common(40):
    print(f"  {count:5d}  {cat}")
