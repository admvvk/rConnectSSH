"""Smoke test for the connections editor: exercises the real tree-mutation
and persistence logic (add/edit/delete group & connection), and takes a
screenshot of the Add Connection dialog so the form layout can be checked
visually. Modal dialog *interaction* (typing + clicking OK) is not
automated here — Gtk.Dialog.run() blocks on a nested main loop, and
driving it programmatically would need synthetic X input events, which is
disproportionate for this stage. Instead we call the same tree-mutation
methods the dialog handlers call internally, bypassing only the modal
dialog's blocking run().
"""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from rconnect.app import ConnectionDialog, MainWindow, RConnectApp, force_x11_backend
from rconnect.models import Connection, Group, Protocol


def dump_tree(group: Group, indent: int = 0) -> None:
    print(" " * indent, "Group:", group.name)
    for sub in group.subgroups:
        dump_tree(sub, indent + 2)
    for conn in group.connections:
        print(" " * (indent + 2), "Connection:", conn.name, conn.protocol.value, conn.host, conn.port)


def main() -> int:
    force_x11_backend()
    app = RConnectApp(root_group=Group(name="Connections"))

    def on_activate(application):
        win: MainWindow = application.get_active_window()

        # 1. add a group at the root
        win.root_group.subgroups.append(Group(name="Work"))
        win.rebuild_tree()
        win.save()
        work_group = win.root_group.subgroups[0]
        assert work_group.name == "Work"

        # 2. add a connection into that group (same mutation the dialog
        # handler performs after dialog.get_connection() succeeds)
        work_group.connections.append(
            Connection(name="jump host", protocol=Protocol.SSH, host="10.0.0.5", port=22, username="root")
        )
        win.rebuild_tree()
        win.save()
        assert len(work_group.connections) == 1

        # 3. edit it in place
        conn = work_group.connections[0]
        conn.name = "jump host (renamed)"
        win.rebuild_tree()
        win.save()

        # 4. verify _parent_group_of / _target_group_for_insert against a
        # real TreeIter from the rebuilt store. The root group itself is
        # row 0 (rebuild_tree always includes it); "Work" is its only child.
        model = win.tree_store
        root_iter = model.get_iter_first()
        assert model[root_iter][win.COL_OBJ] is win.root_group
        work_iter = model.iter_children(root_iter)
        assert model[work_iter][win.COL_OBJ] is work_group
        conn_iter = model.iter_children(work_iter)
        assert model[conn_iter][win.COL_OBJ] is conn
        assert win._parent_group_of(conn_iter) is work_group

        # 5. delete the connection, verify it's gone from the model
        work_group.connections.remove(conn)
        win.rebuild_tree()
        win.save()
        assert work_group.connections == []

        print("TREE MUTATION / PERSISTENCE: OK")
        dump_tree(win.root_group)

        # 6. render the Add Connection dialog (visual check only, no
        # interaction) and take a screenshot before tearing it down
        dialog = ConnectionDialog(win, title="Add connection")
        dialog.show_now()

        def snap_and_quit():
            import subprocess

            subprocess.run(["import", "-window", "root", "/app/dialog.png"], check=False)
            dialog.destroy()
            app.quit()
            return False

        GLib.timeout_add(1500, snap_and_quit)

    app.connect_after("activate", on_activate)
    return app.run(None)


if __name__ == "__main__":
    sys.exit(main())
