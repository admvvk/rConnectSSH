"""Smoke test for mRemoteNG import against a REAL export file (not the
test fixture) — exercises import_file() + merging into the live tree +
persistence, the same way the real UI dialog does, without driving the
GTK file-chooser/password dialogs interactively.

Usage: python3 smoke_test_mremoteng_import.py /path/to/real.xml [passphrase]
"""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib  # noqa: E402

from rconnect.app import RConnectApp, force_x11_backend
from rconnect.importers.mremoteng import MRemoteNGImportError, import_file
from rconnect.models import Group


def count(group: Group) -> tuple[int, int]:
    groups, conns = 1, len(group.connections)
    for sub in group.subgroups:
        g, c = count(sub)
        groups += g
        conns += c
    return groups, conns


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: smoke_test_mremoteng_import.py <xml> [passphrase]", file=sys.stderr)
        return 2
    xml_path = sys.argv[1]
    passphrase = sys.argv[2] if len(sys.argv) > 2 else "mR3m"

    force_x11_backend()
    app = RConnectApp(root_group=Group(name="Connections"))

    def on_activate(application):
        win = application.get_active_window()
        try:
            result = import_file(xml_path, passphrase=passphrase)
        except MRemoteNGImportError as exc:
            print("IMPORT FAILED:", exc)
            app.quit()
            return

        print(f"groups={result.group_count} connections={result.connection_count} warnings={len(result.warnings)}")
        for w in result.warnings[:15]:
            print("  WARN:", w)
        if len(result.warnings) > 15:
            print(f"  ... and {len(result.warnings) - 15} more")

        win.root_group.subgroups.append(result.root)
        win.rebuild_tree()
        win.save()

        # sanity: re-read what we just saved from disk and compare counts
        from rconnect import storage
        reloaded = storage.load_tree()
        g, c = count(reloaded)
        print(f"after save+reload: groups={g} connections={c}")

        app.quit()

    app.connect_after("activate", on_activate)
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main())
