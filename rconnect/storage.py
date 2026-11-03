"""Persistence for the connections tree: a single JSON file under the
user's XDG config directory.

This is a single-user desktop app (one process, one person), so a plain
JSON file is enough — no concurrent-write protection needed, unlike a
multi-client server.

Password encryption is OPT-IN, per user decision: a settings flag
(`encryption.enabled`) controls whether connection passwords are stored
in plain text (default, and the only behavior until this flag is turned
on) or encrypted with a user-chosen master password (see rconnect.crypto).
The flag and a verification sentinel (not any real password) live at the
top of the file, same shape as mRemoteNG's own `Protected` attribute, so
a wrong/missing master password is caught before touching any connection
data.

File shape:
{
  "encryption": {"enabled": false},
  "root": {"name": ..., "connections": [...], "subgroups": [...]}
}
or, with encryption enabled:
{
  "encryption": {"enabled": true, "sentinel": "<base64>"},
  "root": {... "connections": [{..., "password_enc": "<base64>"}, ...] ...}
}
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from rconnect import crypto
from rconnect.models import Connection, Group, Protocol

APP_DIR_NAME = "rconnect"
CONNECTIONS_FILENAME = "connections.json"


class EncryptionRequiredError(Exception):
    """Raised by load_tree() when the file has encrypted passwords but no
    passphrase was supplied."""


def config_dir() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / APP_DIR_NAME


def connections_path() -> Path:
    return config_dir() / CONNECTIONS_FILENAME


def is_encrypted(path: Path | None = None) -> bool:
    """Whether the on-disk file currently has password encryption turned
    on. False (including: file doesn't exist yet) means passwords are/will
    be stored in plain text — the default until the user opts in via
    Settings.
    """
    path = path or connections_path()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    return bool(data.get("encryption", {}).get("enabled", False))


def get_sentinel(path: Path | None = None) -> str | None:
    path = path or connections_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data.get("encryption", {}).get("sentinel")


def _connection_to_dict(conn: Connection, passphrase: str | None) -> dict:
    d = {
        "name": conn.name,
        "protocol": conn.protocol.value,
        "host": conn.host,
        "port": conn.port,
        "username": conn.username,
        "ssh_key_path": conn.ssh_key_path,
    }
    if passphrase is not None:
        d["password_enc"] = crypto.encrypt_field(conn.password, passphrase)
    else:
        d["password"] = conn.password
    return d


def _connection_from_dict(data: dict, passphrase: str | None) -> Connection:
    if "password_enc" in data:
        if passphrase is None:
            raise EncryptionRequiredError("file has encrypted passwords but no passphrase was given")
        password = crypto.decrypt_field(data["password_enc"], passphrase)
    else:
        password = data.get("password", "")
    return Connection(
        name=data["name"],
        protocol=Protocol(data["protocol"]),
        host=data["host"],
        port=data.get("port"),
        username=data.get("username", ""),
        password=password,
        ssh_key_path=data.get("ssh_key_path", ""),
    )


def _group_to_dict(group: Group, passphrase: str | None) -> dict:
    return {
        "name": group.name,
        "connections": [_connection_to_dict(c, passphrase) for c in group.connections],
        "subgroups": [_group_to_dict(g, passphrase) for g in group.subgroups],
    }


def _group_from_dict(data: dict, passphrase: str | None) -> Group:
    return Group(
        name=data["name"],
        connections=[_connection_from_dict(c, passphrase) for c in data.get("connections", [])],
        subgroups=[_group_from_dict(g, passphrase) for g in data.get("subgroups", [])],
    )


def save_tree(root: Group, path: Path | None = None, passphrase: str | None = None) -> None:
    """passphrase: None stores passwords in plain text (the default).
    A string enables encryption for this save — every connection's
    password is encrypted with it, and a verification sentinel is stored
    alongside so a wrong passphrase is caught at load time.
    """
    path = path or connections_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    encryption_block: dict = {"enabled": passphrase is not None}
    if passphrase is not None:
        encryption_block["sentinel"] = crypto.make_sentinel(passphrase)

    data = {"encryption": encryption_block, "root": _group_to_dict(root, passphrase)}

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp_path.replace(path)  # atomic on the same filesystem


def load_tree(path: Path | None = None, passphrase: str | None = None) -> Group | None:
    """Returns None if the file does not exist yet (first run).

    Raises EncryptionRequiredError if the file has encrypted passwords and
    no passphrase was given, and crypto.WrongPassphraseError if one was
    given but doesn't match. Callers should check is_encrypted()/verify
    against get_sentinel() BEFORE calling this with user input, so a
    wrong password can be reported without partially decrypting data.
    """
    path = path or connections_path()
    if not path.exists():
        return None
    data = json.loads(path.read_text())

    if data.get("encryption", {}).get("enabled") and passphrase is not None:
        sentinel = data["encryption"].get("sentinel")
        if sentinel and not crypto.verify_sentinel(sentinel, passphrase):
            raise crypto.WrongPassphraseError("wrong master password")

    root_data = data.get("root", data)  # tolerate the pre-encryption file shape too
    return _group_from_dict(root_data, passphrase)
