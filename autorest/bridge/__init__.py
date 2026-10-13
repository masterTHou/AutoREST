"""
AutoREST DSH Bridge — Protocol definitions.

This module defines the JSON protocol for communication between
the TypeScript DSH plugin and the Python bridge process.

Protocol is versioned to allow backward-compatible evolution.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Current protocol version.
# Increment when the wire format changes in a non-backward-compatible way.
PROTOCOL_VERSION = 1

# Supported actions
ACTION_DETECT = "detect"
ACTION_GENERATE_INPUT = "generate_input"
ACTION_PARSE_OUTPUT = "parse_output"

# ── Request / Response DTOs ──────────────────────────────────────


def build_request(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a bridge request envelope."""
    return {
        "protocol": PROTOCOL_VERSION,
        "action": action,
        "payload": payload,
    }


def build_response(
    ok: bool,
    code: str = "",
    message: str = "",
    hint: str = "",
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a standard bridge response envelope.

    Args:
        ok: Whether the action completed successfully.
        code: Machine-readable error/diagnostic code.
        message: Human-readable summary.
        hint: Actionable next step or suggestion.
        data: Structured result payload.
    """
    resp: Dict[str, Any] = {"ok": ok}
    if code:
        resp["code"] = code
    if message:
        resp["message"] = message
    if hint:
        resp["hint"] = hint
    if data is not None:
        resp["data"] = data
    return resp


# ── Error Codes ──────────────────────────────────────────────────

class ErrorCode:
    """Centralised error codes.  Every bridge response that is not
    ``ok = True`` should include one of these codes so the plugin
    can route errors without inspecting free-text messages."""

    PYTHON_NOT_FOUND = "PYTHON_NOT_FOUND"
    PYTHON_DEPENDENCY_MISSING = "PYTHON_DEPENDENCY_MISSING"
    BRIDGE_PROTOCOL_ERROR = "BRIDGE_PROTOCOL_ERROR"
    REST_NOT_FOUND = "REST_NOT_FOUND"
    INVALID_TASK = "INVALID_TASK"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"
    UNSUPPORTED_TASK = "UNSUPPORTED_TASK"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    PARSE_PARTIAL = "PARSE_PARTIAL"
    PARSE_FAILED = "PARSE_FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"