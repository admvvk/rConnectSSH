"""Modal dialogs for creating/editing a Group or a Connection.

Kept separate from app.py so the main window module stays focused on
layout/embedding; these are plain Gtk.Dialog subclasses with no
persistence logic of their own — callers read back the result and decide
what to do with the model.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from rconnect.models import Connection, Protocol
from rconnect.terminal_themes import SCHEME_LABELS


class GroupDialog(Gtk.Dialog):
    """Just a name field — groups have no other attributes yet."""

    def __init__(self, parent: Gtk.Window, initial_name: str = "", title: str = "Group"):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        self.set_default_response(Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(6)
        box.set_border_width(10)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.pack_start(Gtk.Label(label="Name:"), False, False, 0)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(initial_name)
        self.name_entry.set_activates_default(True)
        row.pack_start(self.name_entry, True, True, 0)
        box.pack_start(row, False, False, 0)

        self.show_all()

    def get_name(self) -> str:
        return self.name_entry.get_text().strip()


class ConnectionDialog(Gtk.Dialog):
    """SSH connection form: name, host, port, username, password, and an
    optional private key path. There is only one protocol (SSH) now —
    RDP/VNC and their per-protocol fields were dropped — so every field
    is always visible, no protocol combo/visibility switching needed.
    """

    def __init__(self, parent: Gtk.Window, initial: Connection | None = None, title: str = "Connection"):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        self.set_default_response(Gtk.ResponseType.OK)
        self.error_label = Gtk.Label()
        self.error_label.set_no_show_all(True)

        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        box = self.get_content_area()
        box.set_border_width(10)
        box.set_spacing(6)
        box.pack_start(grid, True, True, 0)
        box.pack_start(self.error_label, False, False, 0)

        self._next_row = 0

        def add_row(label_text: str, widget: Gtk.Widget) -> None:
            row = self._next_row
            self._next_row += 1
            lbl = Gtk.Label(label=label_text, xalign=0)
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)

        self.name_entry = Gtk.Entry()
        add_row("Name:", self.name_entry)

        self.host_entry = Gtk.Entry()
        add_row("Host:", self.host_entry)

        self.port_entry = Gtk.Entry()
        self.port_entry.set_placeholder_text("(default: 22)")
        add_row("Port:", self.port_entry)

        self.username_entry = Gtk.Entry()
        add_row("Username:", self.username_entry)

        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        add_row("Password:", self.password_entry)

        key_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.ssh_key_entry = Gtk.Entry()
        self.ssh_key_entry.set_placeholder_text("optional — leave blank to use a password")
        self.ssh_key_entry.set_hexpand(True)
        key_box.pack_start(self.ssh_key_entry, True, True, 0)
        key_browse_btn = Gtk.Button(label="...")
        key_browse_btn.connect("clicked", self._on_browse_ssh_key_clicked)
        key_box.pack_start(key_browse_btn, False, False, 0)
        add_row("SSH private key (PEM):", key_box)

        if initial is not None:
            self.name_entry.set_text(initial.name)
            self.host_entry.set_text(initial.host)
            self.port_entry.set_text(str(initial.port) if initial.port else "")
            self.username_entry.set_text(initial.username)
            self.password_entry.set_text(initial.password)
            self.ssh_key_entry.set_text(initial.ssh_key_path)

        self.name_entry.set_activates_default(True)
        self.host_entry.set_activates_default(True)

        self.show_all()

    def _on_browse_ssh_key_clicked(self, _btn) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Select SSH private key",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )
        # No file-extension filter: PEM private keys commonly have no
        # extension at all (e.g. ~/.ssh/id_rsa), so filtering by *.pem
        # would hide the most common case.
        try:
            if chooser.run() == Gtk.ResponseType.OK:
                path = chooser.get_filename()
                if path:
                    self.ssh_key_entry.set_text(path)
        finally:
            chooser.destroy()

    def _show_error(self, message: str) -> None:
        self.error_label.set_text(message)
        self.error_label.set_no_show_all(False)
        self.error_label.show()

    def get_connection(self) -> Connection | None:
        """Validates the form and returns a Connection, or None (and shows
        an inline error) if the input is invalid. Callers should keep the
        dialog open and let the user correct the error on None.
        """
        name = self.name_entry.get_text().strip()
        host = self.host_entry.get_text().strip()
        port_text = self.port_entry.get_text().strip()
        username = self.username_entry.get_text()
        password = self.password_entry.get_text()
        ssh_key_path = self.ssh_key_entry.get_text().strip()

        if not name:
            self._show_error("Name is required.")
            return None
        if not host:
            self._show_error("Host is required.")
            return None

        port: int | None = None
        if port_text:
            try:
                port = int(port_text)
            except ValueError:
                self._show_error("Port must be a number.")
                return None
            if not (0 < port < 65536):
                self._show_error("Port must be between 1 and 65535.")
                return None

        return Connection(
            name=name,
            protocol=Protocol.SSH,
            host=host,
            port=port,
            username=username,
            password=password,
            ssh_key_path=ssh_key_path,
        )


class MasterPasswordDialog(Gtk.Dialog):
    """A single password entry, used both to unlock an existing encrypted
    store (verify=True) and to set a brand-new master password when the
    user turns encryption on (confirm=True: a second entry must match).
    """

    def __init__(
        self,
        parent: Gtk.Window | None,
        title: str,
        subtitle: str = "",
        confirm: bool = False,
    ):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.confirm = confirm
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        self.set_default_response(Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_border_width(10)
        box.set_spacing(6)
        if subtitle:
            label = Gtk.Label(label=subtitle)
            label.set_line_wrap(True)
            box.pack_start(label, False, False, 0)

        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.set_placeholder_text("Master password")
        self.password_entry.set_activates_default(True)
        box.pack_start(self.password_entry, False, False, 0)

        self.confirm_entry = None
        if confirm:
            self.confirm_entry = Gtk.Entry()
            self.confirm_entry.set_visibility(False)
            self.confirm_entry.set_placeholder_text("Confirm password")
            self.confirm_entry.set_activates_default(True)
            box.pack_start(self.confirm_entry, False, False, 0)

        self.error_label = Gtk.Label()
        self.error_label.set_no_show_all(True)
        box.pack_start(self.error_label, False, False, 0)

        self.show_all()

    def _show_error(self, message: str) -> None:
        self.error_label.set_text(message)
        self.error_label.set_no_show_all(False)
        self.error_label.show()

    def get_password(self) -> str | None:
        """Validates and returns the entered password, or None (with an
        inline error already shown) if it's empty or the confirmation
        doesn't match. Caller should keep the dialog open and re-run() on
        None so the user can correct it.
        """
        pw = self.password_entry.get_text()
        if not pw:
            self._show_error("Password cannot be empty.")
            return None
        if self.confirm and pw != self.confirm_entry.get_text():
            self._show_error("Passwords do not match.")
            return None
        return pw


class SettingsDialog(Gtk.Dialog):
    """Password encryption toggle + VTE terminal appearance (font, color
    scheme) for SSH sessions. Changing the master password of an
    already-encrypted store isn't wired up as its own flow yet — turn
    encryption off then on again with the new password to change it.
    """

    def __init__(
        self,
        parent: Gtk.Window,
        encryption_enabled: bool,
        terminal_font: str = "Monospace 11",
        terminal_color_scheme: str = "default",
    ):
        super().__init__(title="Settings", transient_for=parent, modal=True)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK,
        )
        self.set_default_response(Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_border_width(10)
        box.set_spacing(6)

        self.encrypt_check = Gtk.CheckButton(label="Encrypt stored passwords (requires a master password)")
        self.encrypt_check.set_active(encryption_enabled)
        box.pack_start(self.encrypt_check, False, False, 0)

        note = Gtk.Label(
            label="If off, connection passwords are stored in plain text\nin connections.json (the default)."
        )
        note.set_line_wrap(True)
        box.pack_start(note, False, False, 0)

        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 6)

        box.pack_start(Gtk.Label(label="SSH terminal font:"), False, False, 0)
        self.font_button = Gtk.FontButton()
        self.font_button.set_font(terminal_font)
        box.pack_start(self.font_button, False, False, 0)

        box.pack_start(Gtk.Label(label="SSH terminal color scheme:"), False, False, 0)
        self.scheme_combo = Gtk.ComboBoxText()
        for key, label in SCHEME_LABELS:
            self.scheme_combo.append(key, label)
        self.scheme_combo.set_active_id(terminal_color_scheme)
        if self.scheme_combo.get_active_id() is None:
            # an unknown saved key (e.g. from a future version) — fall
            # back to the first entry rather than showing a blank combo
            self.scheme_combo.set_active(0)
        box.pack_start(self.scheme_combo, False, False, 0)

        self.error_label = Gtk.Label()
        self.error_label.set_no_show_all(True)
        box.pack_start(self.error_label, False, False, 0)

        self.show_all()

    def show_error(self, message: str) -> None:
        self.error_label.set_text(message)
        self.error_label.set_no_show_all(False)
        self.error_label.show()

    def encryption_requested(self) -> bool:
        return self.encrypt_check.get_active()

    def terminal_font(self) -> str:
        return self.font_button.get_font()

    def terminal_color_scheme(self) -> str:
        return self.scheme_combo.get_active_id()
