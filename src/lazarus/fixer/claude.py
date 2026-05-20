"""Claude API integration for AI-powered code fixes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from lazarus.compat.analyzer import CompatIssue


@dataclass
class FixAttempt:
    original_code: str
    fixed_code: str
    explanation: str
    issues_addressed: list[str] = field(default_factory=list)


SYSTEM_PROMPT = """\
You are a Python compatibility expert. Your job is to fix Python code that \
is broken due to API removals in Python 3.14.

Rules:
- Make MINIMAL changes — only fix what's broken, don't refactor
- Preserve all existing behavior and functionality
- Keep the same code style (indentation, naming, etc.)
- Do NOT add type hints, docstrings, or comments unless fixing a breakage
- Return ONLY the fixed code, no explanations or markdown fences
"""


def _build_prompt(code: str, issues: list[CompatIssue]) -> str:
    """Build the prompt for Claude with code and identified issues."""
    issue_text = "\n".join(
        f"- Line {i.line_number}: {i.description}" for i in issues
    )
    return f"""\
Fix the following Python code for Python 3.14 compatibility.

## Identified Issues
{issue_text}

## Code to Fix
```python
{code}
```

Return ONLY the fixed Python code, no markdown fences or explanations."""


class ClaudeFixer:
    """Fix Python code using the Claude API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5-20241022",
        max_tokens: int = 8192,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def fix_file(self, file_path: Path, issues: list[CompatIssue]) -> FixAttempt:
        """Fix a single file using Claude.

        Args:
            file_path: Path to the Python file to fix.
            issues: Compatibility issues found in this file.

        Returns:
            A FixAttempt with the original and fixed code.
        """
        original = file_path.read_text(encoding="utf-8")

        if not issues:
            return FixAttempt(
                original_code=original,
                fixed_code=original,
                explanation="No issues to fix",
            )

        prompt = _build_prompt(original, issues)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        fixed_code = response.content[0].text

        # Strip markdown fences if Claude included them despite instructions
        if fixed_code.startswith("```python"):
            fixed_code = fixed_code[len("```python"):].strip()
        if fixed_code.startswith("```"):
            fixed_code = fixed_code[3:].strip()
        if fixed_code.endswith("```"):
            fixed_code = fixed_code[:-3].strip()

        return FixAttempt(
            original_code=original,
            fixed_code=fixed_code,
            explanation=f"Fixed {len(issues)} issue(s) via Claude",
            issues_addressed=[i.issue_type for i in issues],
        )

    def fix_package(
        self, source_dir: Path, issues: list[CompatIssue]
    ) -> list[FixAttempt]:
        """Fix all files in a package that have non-auto-fixable issues.

        Args:
            source_dir: Root directory of the extracted package.
            issues: All compatibility issues found in the package.

        Returns:
            List of FixAttempts, one per file modified.
        """
        # Group non-auto-fixable issues by file
        by_file: dict[str, list[CompatIssue]] = {}
        for issue in issues:
            if not issue.auto_fixable:
                by_file.setdefault(issue.file_path, []).append(issue)

        results: list[FixAttempt] = []
        for file_path, file_issues in by_file.items():
            attempt = self.fix_file(Path(file_path), file_issues)
            results.append(attempt)

        return results
