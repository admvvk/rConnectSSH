"""Native, in-process terminal for SSH sessions, using VTE (the GTK
widget library behind GNOME Terminal, xfce4-terminal, Terminator, etc.)
instead of spawning an external terminal emulator and reparenting its
X11 window.

This sidesteps the entire "which terminal emulator, which flags" problem
documented in the linux-x11-window-embedding skill and this project's
README: VTE.Terminal is a normal GTK widget, so it's just packed into
the tab directly — no process-window discovery, no single-instance/
server-mode quirks, no invisible leader-window races, no manual X11
resize/focus handling (GTK's normal widget layout and focus chain handle
both for free). (RDP/VNC used to need the X11-reparenting approach for
exactly the opposite reason — those are graphical protocols with no
GTK-widget equivalent to VTE — but that support was dropped.)

VTE has no built-in right-click context menu (unlike GNOME Terminal,
which layers its own on top of the same widget) — see
_show_context_menu()/_on_terminal_button_press() below for the
Copy/Paste menu added on top of it.
"""
from __future__ import annotations

import logging
import os
import signal
from dataclasses import dataclass, field
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, GLib, Gtk, Pango, Vte  # noqa: E402

from rconnect.terminal_themes import apply_color_scheme

log = logging.getLogger(__name__)


class VteSpawnError(RuntimeError):
    """Raised when VTE failed to spawn the child process (e.g. the ssh
    binary is missing)."""


@dataclass
class VteSession:
    """Wraps a Vte.Terminal widget and the child process spawned into it.
    on_exited(status) is called (on the GTK main loop) once the child
    process exits, for any reason.
    """

    terminal: Vte.Terminal
    pid: Optional[int] = None
    exit_status: Optional[int] = None
    _on_exited: Optional[Callable[[int], None]] = field(default=None, repr=False)

    def is_alive(self) -> bool:
        return self.exit_status is None

    def terminate(self) -> None:
        if self.pid is not None and self.is_alive():
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def give_focus(self) -> None:
        """A normal GTK widget — grab_focus() is all that's needed, no
        Xlib SetInputFocus dance (RDP/VNC's X11-reparenting embedding
        needed that; dropped along with that protocol support)."""
        self.terminal.grab_focus()


def _show_context_menu(terminal: Vte.Terminal, event: Gdk.EventButton) -> None:
    """Right-click context menu with Copy/Paste — VTE itself has no
    built-in one (unlike GNOME Terminal, which builds its own on top of
    the same widget). Copy is only sensitive when there's an actual
    selection; Paste is always offered since checking the clipboard's
    current content would need an async round-trip just to decide
    whether to grey out a menu item.
    """
    menu = Gtk.Menu()

    copy_item = Gtk.MenuItem(label="Copy")
    copy_item.set_sensitive(terminal.get_has_selection())
    copy_item.connect("activate", lambda _item: terminal.copy_clipboard_format(Vte.Format.TEXT))
    menu.append(copy_item)

    paste_item = Gtk.MenuItem(label="Paste")
    paste_item.connect("activate", lambda _item: terminal.paste_clipboard())
    menu.append(paste_item)

    menu.show_all()
    menu.popup_at_pointer(event)


def _on_terminal_button_press(terminal: Vte.Terminal, event: Gdk.EventButton) -> bool:
    if event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
        _show_context_menu(terminal, event)
        return True  # handled: don't let VTE's own click handling run too
    return False


def spawn_ssh_terminal(
    argv: list[str],
    on_exited: Callable[[int], None],
    envv: Optional[list[str]] = None,
    font: str = "Monospace 11",
    color_scheme: str = "default",
) -> VteSession:
    """Create a Vte.Terminal, spawn argv as its child process (a PTY is
    allocated automatically), and return the VteSession wrapping both.
    Spawning is asynchronous (matches Vte's own API) — call this from the
    GTK main thread; on_exited is invoked later from the main loop too.

    envv: full replacement environment for the child (None = inherit the
    app's own environment unchanged). Used to pass SSHPASS to `sshpass`
    without putting the password on argv (visible to other processes via
    `ps`) — see launchers.build_ssh_spawn().
    """
    terminal = Vte.Terminal()
    terminal.set_font(Pango.FontDescription.from_string(font))
    apply_color_scheme(terminal, color_scheme)
    terminal.connect("button-press-event", _on_terminal_button_press)
    session = VteSession(terminal=terminal, _on_exited=on_exited)

    def on_child_exited(_term: Vte.Terminal, status: int) -> None:
        session.exit_status = status
        on_exited(status)

    terminal.connect("child-exited", on_child_exited)

    def spawn_callback(_term: Vte.Terminal, pid: int, error, _user_data) -> None:
        if error is not None:
            log.error("VTE spawn failed for %r: %s", argv, error)
            session.exit_status = -1
            on_exited(-1)
            return
        session.pid = pid

    terminal.spawn_async(
        Vte.PtyFlags.DEFAULT,
        None,  # working directory: inherit
        argv,
        envv,  # None = inherit the app's own environment unchanged
        GLib.SpawnFlags.DEFAULT,
        None,  # child_setup
        None,  # child_setup_data
        -1,  # timeout: no timeout
        None,  # cancellable
        spawn_callback,
        None,
    )
    return session
