"""Failure type classification for compatibility issues."""

from __future__ import annotations

from enum import StrEnum


class FailureType(StrEnum):
    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    REMOVED_API = "removed_api"
    C_EXTENSION = "c_extension"
    DEPENDENCY = "dependency"
    TEST_FAILURE = "test_failure"
    BUILD_FAILURE = "build_failure"
    UNKNOWN = "unknown"


def classify_failure(error_output: str) -> FailureType:
    """Classify a failure based on error output text."""
    lower = error_output.lower()

    if "modulenotfounderror" in lower or "importerror" in lower:
        return FailureType.IMPORT_ERROR
    if "syntaxerror" in lower:
        return FailureType.SYNTAX_ERROR
    if any(term in lower for term in [
        "attributeerror", "has no attribute", "removed in python",
        "deprecationwarning", "was removed",
    ]):
        return FailureType.REMOVED_API
    if any(term in lower for term in [
        "c extension", ".so", ".pyd", "compilation failed",
        "error: command 'gcc'", "error: command 'cl.exe'",
        "microsoft visual c++", "cannot open shared object",
    ]):
        return FailureType.C_EXTENSION
    if "no matching distribution" in lower or "requirement" in lower:
        return FailureType.DEPENDENCY
    if any(term in lower for term in ["failed", "error", "assert"]):
        if "build" in lower or "setup.py" in lower or "install" in lower:
            return FailureType.BUILD_FAILURE
        return FailureType.TEST_FAILURE

    return FailureType.UNKNOWN


def is_auto_fixable(failure_type: FailureType) -> bool:
    """Check if a failure type can potentially be auto-fixed."""
    return failure_type in (FailureType.REMOVED_API, FailureType.IMPORT_ERROR)
