"""Smoke test for SSH's native VTE-based session (no external terminal
emulator, no X11 reparenting at all — see rconnect/vte_session.py).

Verifies: a Vte.Terminal widget gets created and packed into the tab with
the configured font/color scheme applied without error, a real ssh
process gets spawned with a PID, and when that process exits (ssh
refusing a closed local port, a fast deterministic stand-in for any
session ending) the tab's _ended flag flips via the "child-exited"
signal AND the tab is automatically removed from the notebook —
exercising the actual production path end-to-end (MainWindow.
open_session_tab, not a hand-rolled SessionTab construction).
"""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib  # noqa: E402

from rconnect.app import RConnectApp, force_x11_backend
from rconnect.models import Connection, Group, Protocol


def main() -> int:
    force_x11_backend()
    # ssh to a port nothing listens on: instant, deterministic failure —
    # no real target server needed, and no risk of the OS's slow TCP
    # connect timeout (a black-holed/unroutable IP would hang for minutes).
    conn = Connection(name="vte-ssh-test", protocol=Protocol.SSH, host="127.0.0.1", port=1, username="nobody")
    root = Group(name="Connections")
    root.connections.append(conn)
    app = RConnectApp(root_group=root)

    def on_activate(application):
        win = application.get_active_window()
        win.app_settings.terminal_font = "Monospace 14"
        win.app_settings.terminal_color_scheme = "dracula"
        win.open_session_tab(conn)
        page = win.notebook.get_nth_page(0)

        from gi.repository import Vte

        print("session is VteSession:", page.session is not None)
        print("terminal is Vte.Terminal:", isinstance(page.session.terminal, Vte.Terminal))
        print("terminal packed into tab:", page.session.terminal in page.get_children())
        print("font applied without error:", page.session.terminal.get_font().to_string())

        def check_result():
            print("pid assigned:", page.session.pid is not None)
            print("is_alive before exit:", page.session.is_alive())
            print("n_pages before exit:", win.notebook.get_n_pages())

            def check_after_exit():
                print("ended after process exit:", page._ended)
                print("is_alive after exit:", page.session.is_alive())
                print("n_pages after exit (tab auto-closed):", win.notebook.get_n_pages())
                app.quit()
                return False

            GLib.timeout_add(1500, check_after_exit)
            return False

        GLib.timeout_add(500, check_result)

    app.connect_after("activate", on_activate)
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main())
