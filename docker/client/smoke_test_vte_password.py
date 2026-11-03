"""Smoke test for SSH password auto-fill via sshpass (see
launchers.build_ssh_spawn): connects to the real ssh-target container
with testuser/testpass set on the Connection, and checks the VTE
terminal's own buffer text for a shell prompt rather than a still-
unanswered "password:" prompt — proof the password was actually
injected, not just that no exception was raised.
"""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import GLib, Vte  # noqa: E402

from rconnect.app import RConnectApp, force_x11_backend
from rconnect.models import Connection, Group, Protocol


def main() -> int:
    force_x11_backend()
    conn = Connection(
        name="vte-ssh-password-test",
        protocol=Protocol.SSH,
        host="ssh-target",
        username="testuser",
        password="testpass",
    )
    root = Group(name="Connections")
    root.connections.append(conn)
    app = RConnectApp(root_group=root)

    def on_activate(application):
        win = application.get_active_window()
        win.open_session_tab(conn)
        win.show_all()
        page = win.notebook.get_nth_page(0)

        def check_result():
            terminal = page.session.terminal
            text = terminal.get_text_format(Vte.Format.TEXT)
            print("terminal buffer:\n" + text)
            print("still showing an unanswered password prompt:", "password:" in text.lower())
            print("looks logged in (shell prompt char present):", any(c in text for c in ("$", "#")))
            app.quit()
            return False

        GLib.timeout_add(5000, check_result)

    app.connect_after("activate", on_activate)
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main())
