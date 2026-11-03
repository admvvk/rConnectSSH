"""Built-in VTE terminal color schemes for Settings.

Hex values verified against each scheme's official published spec
(not guessed from memory):
- Dracula: https://draculatheme.com/spec (official ANSI 16-color table).
- Solarized Dark: base0x values from https://en.wikipedia.org/wiki/Solarized
  (citing Ethan Schoonover's original spec), mapped to the ANSI slots the
  same way the widely-used "gnome-terminal-colors-solarized" project does
  (there's no single official ANSI-slot mapping in the spec itself, since
  Solarized was designed around named base0x/accent tones, not raw ANSI
  codes — this mapping is the de facto standard one replicated by most
  terminal-emulator Solarized profiles).
- "dark"/"light": simple, generic schemes (not tied to a named brand),
  loosely modeled on VS Code's default integrated-terminal ANSI colors.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, TypedDict

if TYPE_CHECKING:
    from gi.repository import Vte


class ColorScheme(TypedDict):
    background: str
    foreground: str
    palette: list[str]  # 16 hex strings: ANSI 0-7 normal, 8-15 bright


COLOR_SCHEMES: dict[str, Optional[ColorScheme]] = {
    "default": None,  # VTE's own built-in default — don't touch colors at all
    "dark": {
        "background": "#1e1e1e",
        "foreground": "#d4d4d4",
        "palette": [
            "#000000", "#cd3131", "#0dbc79", "#e5e510", "#2472c8", "#bc3fbc", "#11a8cd", "#e5e5e5",
            "#666666", "#f14c4c", "#23d18b", "#f5f543", "#3b8eea", "#d670d6", "#29b8db", "#e5e5e5",
        ],
    },
    "light": {
        "background": "#ffffff",
        "foreground": "#000000",
        "palette": [
            "#000000", "#cd3131", "#00bc00", "#949800", "#0451a5", "#bc05bc", "#0598bc", "#555555",
            "#666666", "#cd3131", "#14ce14", "#b5ba00", "#0451a5", "#bc05bc", "#0598bc", "#a5a5a5",
        ],
    },
    "solarized-dark": {
        "background": "#002b36",
        "foreground": "#839496",
        "palette": [
            "#073642", "#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198", "#eee8d5",
            "#002b36", "#cb4b16", "#586e75", "#657b83", "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
        ],
    },
    "dracula": {
        "background": "#282a36",
        "foreground": "#f8f8f2",
        "palette": [
            "#21222c", "#ff5555", "#50fa7b", "#f1fa8c", "#bd93f9", "#ff79c6", "#8be9fd", "#f8f8f2",
            "#6272a4", "#ff6e6e", "#69ff94", "#ffffa5", "#d6acff", "#ff92df", "#a4ffff", "#ffffff",
        ],
    },
}

DEFAULT_SCHEME = "default"

# Human-readable labels for the Settings dropdown, in display order.
SCHEME_LABELS: list[tuple[str, str]] = [
    ("default", "Default (terminal theme)"),
    ("dark", "Dark"),
    ("light", "Light"),
    ("solarized-dark", "Solarized Dark"),
    ("dracula", "Dracula"),
]


def apply_color_scheme(terminal: "Vte.Terminal", scheme_key: str) -> None:
    scheme = COLOR_SCHEMES.get(scheme_key)
    if scheme is None:
        return  # "default" (or an unknown key — fail safe to the default)
    import gi

    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk

    fg = Gdk.RGBA()
    fg.parse(scheme["foreground"])
    bg = Gdk.RGBA()
    bg.parse(scheme["background"])
    palette = []
    for hex_color in scheme["palette"]:
        rgba = Gdk.RGBA()
        rgba.parse(hex_color)
        palette.append(rgba)
    terminal.set_colors(fg, bg, palette)
