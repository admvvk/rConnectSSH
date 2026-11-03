"""Main GTK window: a docked connections tree (left) + session tabs (right),
in the style of mRemoteNG — unlike Remmina, the tree and the active
sessions live in ONE window, not separate top-level windows.

SSH only: sessions run natively via a VTE terminal widget packed
directly into each tab (see rconnect.vte_session) — no external
process/window discovery needed at all. (RDP/VNC support, and the
X11-reparenting embedding they needed, were dropped — see the project
notes for why.)
"""
from __future__ import annotations

import logging
import os
from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from rconnect import crypto, launchers, settings, storage
from rconnect.editor_dialogs import ConnectionDialog, GroupDialog, MasterPasswordDialog, SettingsDialog
from rconnect.importers.mremoteng import MRemoteNGImportError, import_file
from rconnect.models import Connection, Group, Protocol, demo_tree
from rconnect.vte_session import VteSession, spawn_ssh_terminal

log = logging.getLogger(__name__)


def force_x11_backend() -> None:
    """Historically needed so our X11-reparenting embedding (used for
    RDP/VNC, since removed) worked transparently through XWayland on a
    Wayland session. The native VTE terminal used for SSH has no such
    requirement, but this is kept as a harmless default for anyone still
    calling it from a test harness.
    """
    os.environ.setdefault("GDK_BACKEND", "x11")


def prompt_new_master_password(parent: Gtk.Window | None) -> str | None:
    """Used when the user turns password encryption on: asks for a new
    master password twice (must match). Returns None if cancelled.
    """
    dialog = MasterPasswordDialog(
        parent,
        title="Set master password",
        subtitle="This password encrypts all stored connection passwords.\nThere is no recovery if you forget it.",
        confirm=True,
    )
    try:
        while True:
            if dialog.run() != Gtk.ResponseType.OK:
                return None
            pw = dialog.get_password()
            if pw is not None:
                return pw
            # invalid (empty / mismatch): get_password() already showed the
            # inline error, loop back to dialog.run() so the user can retry
    finally:
        dialog.destroy()


def prompt_unlock_master_password(parent: Gtk.Window | None, sentinel: str) -> str | None:
    """Used at startup when the store is encrypted: asks for the existing
    master password and verifies it against the sentinel before
    returning. Returns None if cancelled or after too many wrong
    attempts.
    """
    for _attempt in range(5):
        dialog = MasterPasswordDialog(parent, title="Unlock connections", subtitle="Enter your master password.")
        try:
            if dialog.run() != Gtk.ResponseType.OK:
                return None
            pw = dialog.get_password()
        finally:
            dialog.destroy()
        if pw is None:
            continue  # empty password rejected inline, let them retry
        if crypto.verify_sentinel(sentinel, pw):
            return pw
        error = Gtk.MessageDialog(
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Wrong master password.",
        )
        try:
            error.run()
        finally:
            error.destroy()
    return None


class SessionTab(Gtk.Box):
    """A single session's tab contents: an SSH session running natively
    via a VTE terminal widget packed directly into this box — no
    external process/window at all (see rconnect.vte_session).
    """

    def __init__(
        self,
        connection: Connection,
        terminal_font: str = "Monospace 11",
        terminal_color_scheme: str = "default",
        on_ended_close: Callable[[], None] | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.connection = connection
        self.terminal_font = terminal_font
        self.terminal_color_scheme = terminal_color_scheme
        # Called (if set) when the SSH session ends on its own (user
        # typed "exit", connection closed, etc) — the tab has nothing
        # left to show, so the caller (MainWindow) closes it
        # automatically.
        self.on_ended_close = on_ended_close
        self.session: VteSession | None = None
        self._ended = False  # True once the session has ended (crash or clean)

        self._start_vte_session()

    def _start_vte_session(self) -> None:
        argv, envv = launchers.build_ssh_spawn(self.connection)
        session = spawn_ssh_terminal(
            argv,
            on_exited=self._on_vte_exited,
            envv=envv,
            font=self.terminal_font,
            color_scheme=self.terminal_color_scheme,
        )
        self.session = session
        self.pack_start(session.terminal, True, True, 0)
        log.info("started VTE session for %s", self.connection.name)
        GLib.idle_add(self.give_focus)

    def _on_vte_exited(self, status: int) -> None:
        self._ended = True
        log.info("VTE session for %s ended (status %s), closing tab", self.connection.name, status)
        if self.on_ended_close is not None:
            self.on_ended_close()

    def give_focus(self) -> None:
        if self._ended or self.session is None:
            return
        self.session.give_focus()

    def close(self) -> None:
        if self.session is not None:
            self.session.terminate()


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, root_group: Group | None = None, passphrase: str | None = None):
        super().__init__(application=app, title="rConnectSSH")
        self.set_default_size(1100, 750)
        self.app_settings = settings.load_settings()
        self.root_group = root_group or demo_tree()
        self.passphrase = passphrase  # None = passwords stored in plain text

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(paned)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.set_size_request(240, -1)
        left.pack_start(self._build_toolbar(), False, False, 0)

        self.tree_view = Gtk.TreeView()
        self.tree_view.set_headers_visible(False)
        self.tree_view.connect("row-activated", self._on_row_activated)
        self.rebuild_tree()

        tree_scroller = Gtk.ScrolledWindow()
        tree_scroller.add(self.tree_view)
        left.pack_start(tree_scroller, True, True, 0)
        paned.pack1(left, False, False)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.connect("switch-page", self._on_switch_page)
        paned.pack2(self.notebook, True, True)

    def _on_switch_page(self, _notebook, page: Gtk.Widget, _page_num: int) -> None:
        if isinstance(page, SessionTab):
            page.give_focus()

    def save(self) -> None:
        """Persist the current tree. Called after every edit (add/update/
        delete of a group or connection) and once on first run to seed the
        on-disk demo data.
        """
        storage.save_tree(self.root_group, passphrase=self.passphrase)

    # -- toolbar --------------------------------------------------------
    def _build_toolbar(self) -> Gtk.Box:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        def add_btn(icon_name: str, tooltip: str, handler) -> Gtk.Button:
            btn = Gtk.Button.new_from_icon_name(icon_name, Gtk.IconSize.SMALL_TOOLBAR)
            btn.set_tooltip_text(tooltip)
            btn.connect("clicked", handler)
            bar.pack_start(btn, False, False, 0)
            return btn

        add_btn("folder-new-symbolic", "Add group", self._on_add_group_clicked)
        add_btn("list-add-symbolic", "Add connection", self._on_add_connection_clicked)
        add_btn("document-edit-symbolic", "Edit selected", self._on_edit_clicked)
        add_btn("list-remove-symbolic", "Delete selected", self._on_delete_clicked)
        add_btn("document-import-symbolic", "Import from mRemoteNG...", self._on_import_mremoteng_clicked)
        add_btn("preferences-system-symbolic", "Settings", self._on_settings_clicked)
        return bar

    # -- tree ---------------------------------------------------------
    COL_NAME = 0
    COL_OBJ = 1  # the actual Group or Connection instance for this row
    COL_ICON = 2
    COL_WEIGHT = 3  # Pango.Weight — bold for groups, normal for connections

    _CONNECTION_ICONS = {
        Protocol.SSH: "utilities-terminal-symbolic",
    }

    def rebuild_tree(self) -> None:
        """Rebuilds the GtkTreeStore from self.root_group from scratch.
        Simplest-correct approach for a tree this small — avoids having to
        keep TreeIters in sync with incremental model edits.
        """
        store = Gtk.TreeStore(str, object, str, int)

        def add_group(parent_iter, group: Group) -> None:
            group_iter = store.append(
                parent_iter, [group.name, group, "folder-symbolic", Pango.Weight.BOLD]
            )
            for sub in group.subgroups:
                add_group(group_iter, sub)
            for conn in group.connections:
                icon = self._CONNECTION_ICONS.get(conn.protocol, "network-server-symbolic")
                store.append(group_iter, [conn.name, conn, icon, Pango.Weight.NORMAL])

        add_group(None, self.root_group)

        self.tree_store = store
        self.tree_view.set_model(store)
        if not self.tree_view.get_columns():
            column = Gtk.TreeViewColumn("Name")
            icon_renderer = Gtk.CellRendererPixbuf()
            column.pack_start(icon_renderer, False)
            column.add_attribute(icon_renderer, "icon-name", self.COL_ICON)
            text_renderer = Gtk.CellRendererText()
            column.pack_start(text_renderer, True)
            column.add_attribute(text_renderer, "text", self.COL_NAME)
            column.add_attribute(text_renderer, "weight", self.COL_WEIGHT)
            self.tree_view.append_column(column)
        self.tree_view.expand_all()

    def _on_row_activated(self, view: Gtk.TreeView, path: Gtk.TreePath, _column) -> None:
        obj = view.get_model()[path][self.COL_OBJ]
        if isinstance(obj, Connection):
            self.open_session_tab(obj)
        # a Group row: row-activated's default expander behaviour already
        # handles expand/collapse, nothing else to do here.

    def _get_selected(self) -> tuple[Gtk.TreeIter | None, object | None]:
        selection = self.tree_view.get_selection()
        model, it = selection.get_selected()
        if it is None:
            return None, None
        return it, model[it][self.COL_OBJ]

    def _parent_group_of(self, it: Gtk.TreeIter) -> Group:
        """The Group that the row at `it` lives directly under (its
        children list is where siblings of this row's object are stored).
        """
        parent_iter = self.tree_store.iter_parent(it)
        if parent_iter is None:
            return self.root_group
        parent_obj = self.tree_store[parent_iter][self.COL_OBJ]
        assert isinstance(parent_obj, Group)
        return parent_obj

    def _target_group_for_insert(self) -> Group:
        """Where a new group/connection should be added: the selected
        group, the parent of the selected connection, or the root if
        nothing is selected.
        """
        it, obj = self._get_selected()
        if it is None:
            return self.root_group
        if isinstance(obj, Group):
            return obj
        return self._parent_group_of(it)

    # -- editing: groups --------------------------------------------------
    def _on_add_group_clicked(self, _btn) -> None:
        dialog = GroupDialog(self, title="Add group")
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                name = dialog.get_name()
                if name:
                    target = self._target_group_for_insert()
                    target.subgroups.append(Group(name=name))
                    self.rebuild_tree()
                    self.save()
        finally:
            dialog.destroy()

    def _edit_group(self, group: Group) -> None:
        if group is self.root_group:
            return  # renaming the invisible root isn't useful
        dialog = GroupDialog(self, initial_name=group.name, title="Edit group")
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                name = dialog.get_name()
                if name:
                    group.name = name
                    self.rebuild_tree()
                    self.save()
        finally:
            dialog.destroy()

    # -- editing: connections ----------------------------------------------
    def _on_add_connection_clicked(self, _btn) -> None:
        dialog = ConnectionDialog(self, title="Add connection")
        try:
            while True:
                if dialog.run() != Gtk.ResponseType.OK:
                    break
                conn = dialog.get_connection()
                if conn is not None:
                    target = self._target_group_for_insert()
                    target.connections.append(conn)
                    self.rebuild_tree()
                    self.save()
                    break
                # invalid input: get_connection() already showed the error,
                # loop back to dialog.run() so the user can fix it
        finally:
            dialog.destroy()

    def _edit_connection(self, conn: Connection) -> None:
        dialog = ConnectionDialog(self, initial=conn, title="Edit connection")
        try:
            while True:
                if dialog.run() != Gtk.ResponseType.OK:
                    break
                updated = dialog.get_connection()
                if updated is not None:
                    conn.name = updated.name
                    conn.protocol = updated.protocol
                    conn.host = updated.host
                    conn.port = updated.port
                    conn.username = updated.username
                    conn.password = updated.password
                    conn.ssh_key_path = updated.ssh_key_path
                    self.rebuild_tree()
                    self.save()
                    break
        finally:
            dialog.destroy()

    # -- editing: shared add/edit/delete dispatch ---------------------------
    def _on_edit_clicked(self, _btn) -> None:
        _, obj = self._get_selected()
        if isinstance(obj, Connection):
            self._edit_connection(obj)
        elif isinstance(obj, Group):
            self._edit_group(obj)

    def _on_delete_clicked(self, _btn) -> None:
        it, obj = self._get_selected()
        if it is None or obj is None:
            return
        if obj is self.root_group:
            return  # cannot delete the root
        parent = self._parent_group_of(it)

        confirm = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete '{obj.name}'?" + (" (and everything inside it)" if isinstance(obj, Group) else ""),
        )
        try:
            response = confirm.run()
        finally:
            confirm.destroy()
        if response != Gtk.ResponseType.YES:
            return

        if isinstance(obj, Group):
            parent.subgroups.remove(obj)
        else:
            parent.connections.remove(obj)
        self.rebuild_tree()
        self.save()

    # -- import: mRemoteNG --------------------------------------------------
    def _on_import_mremoteng_clicked(self, _btn) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Select mRemoteNG confCons.xml",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )
        xml_filter = Gtk.FileFilter()
        xml_filter.set_name("mRemoteNG XML (*.xml)")
        xml_filter.add_pattern("*.xml")
        chooser.add_filter(xml_filter)

        try:
            if chooser.run() != Gtk.ResponseType.OK:
                return
            xml_path = chooser.get_filename()
        finally:
            chooser.destroy()
        if not xml_path:
            return

        passphrase = self._prompt_mremoteng_passphrase()
        if passphrase is None:
            return

        try:
            result = import_file(xml_path, passphrase=passphrase)
        except MRemoteNGImportError as exc:
            self._show_message(f"Import failed:\n{exc}", message_type=Gtk.MessageType.ERROR)
            return

        if not self._confirm_mremoteng_import(result):
            return

        target = self._target_group_for_insert()
        target.subgroups.append(result.root)
        self.rebuild_tree()
        self.save()

    def _prompt_mremoteng_passphrase(self) -> str | None:
        """mRemoteNG's hardcoded default key is "mR3m" unless the user set
        a custom master password in mRemoteNG itself — pre-fill it since
        that's the common case, but let the user overwrite it.
        """
        dialog = Gtk.Dialog(title="mRemoteNG master password", transient_for=self, modal=True)
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(10)
        box.set_spacing(6)
        box.pack_start(
            Gtk.Label(label="Leave as-is unless you set a custom master\npassword in mRemoteNG's security options."),
            False, False, 0,
        )
        entry = Gtk.Entry()
        entry.set_text("mR3m")
        entry.set_visibility(False)
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)
        dialog.show_all()
        try:
            if dialog.run() != Gtk.ResponseType.OK:
                return None
            return entry.get_text()
        finally:
            dialog.destroy()

    def _confirm_mremoteng_import(self, result) -> bool:
        text = f"Found {result.group_count} group(s), {result.connection_count} connection(s)."
        if result.warnings:
            text += f"\n\n{len(result.warnings)} warning(s) (these entries were skipped):\n"
            text += "\n".join(f"  - {w}" for w in result.warnings[:20])
            if len(result.warnings) > 20:
                text += f"\n  ... and {len(result.warnings) - 20} more"
        text += "\n\nImport into the current selection (or root if nothing selected)?"

        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=text,
        )
        try:
            response = dialog.run()
        finally:
            dialog.destroy()
        return response == Gtk.ResponseType.YES

    def _show_message(self, text: str, message_type=Gtk.MessageType.INFO) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.OK,
            text=text,
        )
        try:
            dialog.run()
        finally:
            dialog.destroy()

    # -- settings / password encryption -------------------------------------
    def _on_settings_clicked(self, _btn) -> None:
        dialog = SettingsDialog(
            self,
            encryption_enabled=self.passphrase is not None,
            terminal_font=self.app_settings.terminal_font,
            terminal_color_scheme=self.app_settings.terminal_color_scheme,
        )
        try:
            if dialog.run() != Gtk.ResponseType.OK:
                return
            wants_encryption = dialog.encryption_requested()
            terminal_font = dialog.terminal_font()
            terminal_color_scheme = dialog.terminal_color_scheme()
        finally:
            dialog.destroy()

        self.app_settings.terminal_font = terminal_font
        self.app_settings.terminal_color_scheme = terminal_color_scheme
        settings.save_settings(self.app_settings)

        currently_encrypted = self.passphrase is not None
        if wants_encryption and not currently_encrypted:
            new_passphrase = prompt_new_master_password(self)
            if new_passphrase is None:
                return  # user cancelled, leave everything as it was
            self.passphrase = new_passphrase
            self.save()
            self._show_message("Password encryption enabled.")
        elif not wants_encryption and currently_encrypted:
            self.passphrase = None
            self.save()
            self._show_message("Password encryption disabled; passwords are now stored in plain text.")
        # else: no change requested

    # -- sessions -------------------------------------------------------
    def open_session_tab(self, connection: Connection) -> None:
        tab = SessionTab(
            connection,
            terminal_font=self.app_settings.terminal_font,
            terminal_color_scheme=self.app_settings.terminal_color_scheme,
        )
        label_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        label_box.pack_start(Gtk.Label(label=connection.name), False, False, 0)
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        label_box.pack_start(close_btn, False, False, 0)
        label_box.show_all()

        page_index = self.notebook.append_page(tab, label_box)
        tab.show_all()
        self.notebook.set_current_page(page_index)

        def close_tab() -> None:
            idx = self.notebook.page_num(tab)
            if idx != -1:
                tab.close()
                self.notebook.remove_page(idx)

        # Wired up after construction (not via the constructor's
        # on_ended_close param) since this closure needs `tab` itself —
        # safe because "child-exited" is always delivered asynchronously
        # via the GLib main loop, never synchronously inside __init__.
        tab.on_ended_close = close_tab
        close_btn.connect("clicked", lambda _btn: close_tab())


class RConnectApp(Gtk.Application):
    def __init__(self, root_group: Group | None = None):
        super().__init__(application_id="dev.rconnect.RConnectGTK")
        # root_group explicitly set means a caller (test harness) wants
        # full control over the tree and no startup password prompt at
        # all — see do_activate(). The normal app entry point (main())
        # leaves this None so the real storage/encryption flow runs.
        self.root_group = root_group

    def do_activate(self) -> None:
        if self.root_group is not None:
            win = MainWindow(self, root_group=self.root_group)
            win.show_all()
            return

        passphrase = None
        if storage.is_encrypted():
            sentinel = storage.get_sentinel()
            passphrase = prompt_unlock_master_password(None, sentinel) if sentinel else None
            if passphrase is None:
                self.quit()
                return

        try:
            root_group = storage.load_tree(passphrase=passphrase)
        except crypto.WrongPassphraseError:
            # shouldn't happen — prompt_unlock_master_password already
            # verified against the sentinel — but don't silently proceed
            # with a possibly-wrong key if it somehow does.
            self.quit()
            return

        first_run = root_group is None
        win = MainWindow(self, root_group=root_group, passphrase=passphrase)
        if first_run:
            # Brand new install (no connections.json yet): MainWindow
            # already seeded self.root_group with demo_tree(); persist it
            # so the file exists from the first run onward.
            win.save()
        win.show_all()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    force_x11_backend()
    app = RConnectApp()
    return app.run(None)
