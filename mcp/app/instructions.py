"""Helpers for loading profile-specific optional MCP handshake instructions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

InstructionProfile = Literal[
    "stdio-user",
    "stdio-admin",
    "remote-user",
    "remote-admin",
]

_DEFAULT_CONNECTION_MODE = "stdio"
_DEFAULT_PROFILE: InstructionProfile = "stdio-user"
_PROFILE_FILENAMES: dict[InstructionProfile, str] = {
    "stdio-user": "stdio-user__mcp-instructions.md",
    "stdio-admin": "stdio-admin__mcp-instructions.md",
    "remote-user": "remote-user__mcp-instructions.md",
    "remote-admin": "remote-admin__mcp-instructions.md",
}
_active_instruction_profile: InstructionProfile | None = None


def set_active_instruction_profile(profile: InstructionProfile | None) -> None:
    """Record the instruction profile chosen for the active server process."""
    global _active_instruction_profile
    _active_instruction_profile = profile


def active_instruction_profile() -> InstructionProfile | None:
    """Return the profile currently advertised by the running server, if known."""
    return _active_instruction_profile


def normalize_connection_mode(mode: str | None = None) -> str:
    """Normalize the configured instruction transport mode."""
    value = (mode or os.getenv("LIGHTRAG_MCP_CONNECTION_MODE") or "").strip().lower()
    if value in {"remote", "stdio"}:
        return value
    return _DEFAULT_CONNECTION_MODE


def instruction_profile(
    *, connection_mode: str | None = None, is_admin: bool | None = None
) -> InstructionProfile:
    """Resolve the instruction profile for the current connection + role."""
    explicit = os.getenv("LIGHTRAG_MCP_INSTRUCTIONS_PROFILE")
    if explicit:
        normalized = explicit.strip().lower()
        if normalized in _PROFILE_FILENAMES:
            return normalized  # type: ignore[return-value]
    mode = normalize_connection_mode(connection_mode)
    if is_admin is None:
        return _DEFAULT_PROFILE if mode == "stdio" else "remote-user"
    return (
        "stdio-admin"
        if mode == "stdio" and is_admin
        else (
            "stdio-user"
            if mode == "stdio"
            else "remote-admin" if is_admin else "remote-user"
        )
    )


def profile_filename(profile: InstructionProfile) -> str:
    """Return the default file name for a given instruction profile."""
    return _PROFILE_FILENAMES[profile]


def _profile_env_var(profile: InstructionProfile) -> str:
    return "LIGHTRAG_MCP_INSTRUCTIONS_" f"{profile.upper().replace('-', '_')}_FILE"


def instructions_path(profile: InstructionProfile | None = None) -> str | None:
    """Return the configured instructions file path for the selected profile."""
    selected = profile or active_instruction_profile() or instruction_profile()
    profile_specific = os.getenv(_profile_env_var(selected))
    if profile_specific:
        return profile_specific
    instructions_dir = os.getenv("LIGHTRAG_MCP_INSTRUCTIONS_DIR")
    if instructions_dir:
        return str(Path(instructions_dir) / profile_filename(selected))
    return os.getenv("LIGHTRAG_MCP_INSTRUCTIONS_FILE") or None


def load_instructions(profile: InstructionProfile | None = None) -> str:
    """Load the server instructions from a file, if configured."""
    path = instructions_path(profile)
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""
