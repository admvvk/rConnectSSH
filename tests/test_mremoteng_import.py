from pathlib import Path

from rconnect.importers.mremoteng import (
    MRemoteNGImportError,
    decrypt_field,
    import_file,
)
from rconnect.models import Protocol

FIXTURE = Path(__file__).parent / "fixtures" / "mremoteng_sample.xml"


def test_decrypt_field_known_value():
    # "Protected" sentinel from a real export with no master password set.
    assert decrypt_field(
        "d0gj9QQWCEfBh7m+eFvCp50SopztS6cihfKx6sYnx/zLkpP/If/DRSapWn8tI4+/zL+8QCWx9aQV98FcMd9rjvHb",
        "mR3m",
    ) == b"ThisIsNotProtected"


def test_wrong_passphrase_raises():
    try:
        import_file(str(FIXTURE), passphrase="definitely-wrong")
    except MRemoteNGImportError:
        pass
    else:
        raise AssertionError("expected MRemoteNGImportError for a wrong passphrase")


def test_import_sample_fixture():
    result = import_file(str(FIXTURE), passphrase="mR3m")
    assert result.root.name  # has some name
    assert result.group_count >= 1
    assert result.connection_count >= 1

    # flatten for easier assertions
    def flatten(group):
        items = list(group.connections)
        for sub in group.subgroups:
            items += flatten(sub)
        return items

    conns = flatten(result.root)
    by_name = {c.name: c for c in conns}

    assert "ssh-host" in by_name
    ssh = by_name["ssh-host"]
    assert ssh.protocol is Protocol.SSH
    assert ssh.host == "192.0.2.5"
    assert ssh.port == 22
    assert ssh.username == "testuser"
    assert ssh.password == "testpass123"

    # unsupported protocols (RDP, Telnet) must be skipped with a warning,
    # not crash — RDP support was dropped from this app entirely.
    assert "rdp-host" not in by_name
    assert any("rdp-host" in w and "unsupported protocol" in w for w in result.warnings)

    assert "telnet-host" not in by_name
    assert any("telnet-host" in w and "unsupported protocol" in w for w in result.warnings)


if __name__ == "__main__":
    test_decrypt_field_known_value()
    test_wrong_passphrase_raises()
    test_import_sample_fixture()
    print("OK")
