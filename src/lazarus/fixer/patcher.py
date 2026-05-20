"""Apply fixes to extracted source trees with backup/restore support."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path


class Patcher:
    """Manages applying fixes to source code with backup/restore."""

    def backup_original(self, source_dir: Path) -> Path:
        """Create a backup of the source directory.

        Returns the path to the backup.
        """
        backup_path = source_dir.parent / f"{source_dir.name}.backup"
        if backup_path.exists():
            shutil.rmtree(backup_path)
        shutil.copytree(source_dir, backup_path)
        return backup_path

    def restore_backup(self, backup_path: Path, source_dir: Path) -> None:
        """Restore source from a backup."""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        if source_dir.exists():
            shutil.rmtree(source_dir)
        shutil.copytree(backup_path, source_dir)

    def cleanup_backup(self, backup_path: Path) -> None:
        """Remove a backup directory."""
        if backup_path.exists():
            shutil.rmtree(backup_path)

    def apply_fix(self, file_path: Path, original: str, fixed: str) -> bool:
        """Apply a fix to a file. Returns True if the file was modified."""
        if original == fixed:
            return False
        file_path.write_text(fixed, encoding="utf-8")
        return True

    def create_diff(self, original: str, fixed: str, filename: str = "") -> str:
        """Create a unified diff between original and fixed code."""
        original_lines = original.splitlines(keepends=True)
        fixed_lines = fixed.splitlines(keepends=True)
        diff = difflib.unified_diff(
            original_lines,
            fixed_lines,
            fromfile=f"a/{filename}" if filename else "a/original",
            tofile=f"b/{filename}" if filename else "b/fixed",
        )
        return "".join(diff)
