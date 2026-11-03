import json
import tempfile
from pathlib import Path

from rconnect.models import Connection, Group, Protocol
from rconnect import crypto, storage


def _sample_tree():
    root = Group(name="Connections")
    sub = Group(name="Example")
    sub.connections.append(
        Connection(
            name="example-ssh-host",
            protocol=Protocol.SSH,
            host="192.0.2.10",
            port=22,
            username="testuser",
            password="secret",
            ssh_key_path="/home/testuser/.ssh/id_rsa",
        )
    )
    root.subgroups.append(sub)
    root.connections.append(Connection(name="top-level host", protocol=Protocol.SSH, host="192.0.2.20"))
    return root


def test_round_trip_plaintext():
    root = _sample_tree()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "connections.json"
        storage.save_tree(root, path)  # no passphrase -> plain text (default)

        assert path.exists()
        raw = json.loads(path.read_text())
        assert raw["encryption"]["enabled"] is False
        assert raw["root"]["name"] == "Connections"
        assert raw["root"]["subgroups"][0]["connections"][0]["password"] == "secret"

        assert storage.is_encrypted(path) is False

        loaded = storage.load_tree(path)
        assert loaded.name == "Connections"
        assert loaded.subgroups[0].name == "Example"
        assert loaded.subgroups[0].connections[0].host == "192.0.2.10"
        assert loaded.subgroups[0].connections[0].protocol is Protocol.SSH
        assert loaded.subgroups[0].connections[0].password == "secret"
        assert loaded.subgroups[0].connections[0].ssh_key_path == "/home/testuser/.ssh/id_rsa"
        assert loaded.connections[0].protocol is Protocol.SSH
        assert loaded.connections[0].ssh_key_path == ""  # default, not set on this one


def test_round_trip_encrypted():
    root = _sample_tree()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "connections.json"
        storage.save_tree(root, path, passphrase="hunter2")

        raw = json.loads(path.read_text())
        assert raw["encryption"]["enabled"] is True
        assert "sentinel" in raw["encryption"]
        # the password must not appear anywhere in cleartext on disk
        assert "secret" not in path.read_text()
        assert "password_enc" in raw["root"]["subgroups"][0]["connections"][0]

        assert storage.is_encrypted(path) is True

        loaded = storage.load_tree(path, passphrase="hunter2")
        assert loaded.subgroups[0].connections[0].password == "secret"


def test_wrong_passphrase_rejected():
    root = _sample_tree()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "connections.json"
        storage.save_tree(root, path, passphrase="hunter2")

        try:
            storage.load_tree(path, passphrase="wrong-one")
        except crypto.WrongPassphraseError:
            pass
        else:
            raise AssertionError("expected WrongPassphraseError")


def test_encrypted_file_without_passphrase_raises():
    root = _sample_tree()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "connections.json"
        storage.save_tree(root, path, passphrase="hunter2")

        try:
            storage.load_tree(path)  # no passphrase given
        except storage.EncryptionRequiredError:
            pass
        else:
            raise AssertionError("expected EncryptionRequiredError")


def test_toggle_encryption_off_rewrites_plaintext():
    root = _sample_tree()
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "connections.json"
        storage.save_tree(root, path, passphrase="hunter2")
        loaded = storage.load_tree(path, passphrase="hunter2")

        storage.save_tree(loaded, path, passphrase=None)  # user turned encryption off
        assert storage.is_encrypted(path) is False
        reloaded = storage.load_tree(path)
        assert reloaded.subgroups[0].connections[0].password == "secret"


def test_missing_file_returns_none():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "does-not-exist.json"
        assert storage.load_tree(path) is None


if __name__ == "__main__":
    test_round_trip_plaintext()
    test_round_trip_encrypted()
    test_wrong_passphrase_rejected()
    test_encrypted_file_without_passphrase_raises()
    test_toggle_encryption_off_rewrites_plaintext()
    test_missing_file_returns_none()
    print("OK")
