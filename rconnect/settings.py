"""App-wide settings unrelated to the connections tree: VTE terminal
appearance. Stored separately from connections.json (settings.json, same
XDG config dir) since they're not sensitive and have nothing to do with
the password-encryption flow.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from rconnect.storage import config_dir
from rconnect.terminal_themes import DEFAULT_SCHEME

SETTINGS_FILENAME = "settings.json"
DEFAULT_TERMINAL_FONT = "Monospace 11"


@dataclass
class AppSettings:
    # VTE terminal appearance (SSH sessions). Font string is a Pango font
    # description, e.g. "Monospace 11" or "Fira Code 12". Color scheme is
    # a key into terminal_themes.COLOR_SCHEMES.
    terminal_font: str = DEFAULT_TERMINAL_FONT
    terminal_color_scheme: str = DEFAULT_SCHEME


def settings_path() -> Path:
    return config_dir() / SETTINGS_FILENAME


def load_settings(path: Path | None = None) -> AppSettings:
    path = path or settings_path()
    if not path.exists():
        return AppSettings()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return AppSettings()
    return AppSettings(
        # Unknown/old keys (e.g. the now-removed rdp_command_override/
        # vnc_command_override) are simply ignored, not an error — a
        # settings.json written by a pre-SSH-only version must still
        # load cleanly.
        terminal_font=data.get("terminal_font") or DEFAULT_TERMINAL_FONT,
        terminal_color_scheme=data.get("terminal_color_scheme") or DEFAULT_SCHEME,
    )


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False))
    tmp_path.replace(path)
