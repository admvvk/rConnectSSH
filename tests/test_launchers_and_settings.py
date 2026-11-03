import tempfile
from pathlib import Path

from rconnect import launchers, settings
from rconnect.models import Connection, Protocol


def test_resolve_binary_override_wins_unconditionally():
    # Even a nonexistent path is accepted verbatim when explicitly set —
    # an explicit override means "trust me", not "verify me".
    assert launchers.resolve_binary(["doesnotexist123"], override="/my/custom/bin") == "/my/custom/bin"


def test_resolve_binary_finds_a_real_candidate():
    # "sh" exists on PATH on basically any POSIX system, including a bare
    # CI container — stand in for a real client binary without depending
    # on anything specific being installed where tests run.
    found = launchers.resolve_binary(["doesnotexist123", "sh"])
    assert found.endswith("/sh")


def test_resolve_binary_raises_when_nothing_found():
    try:
        launchers.resolve_binary(["doesnotexist123", "alsonotreal456"])
    except launchers.BinaryNotFoundError:
        pass
    else:
        raise AssertionError("expected BinaryNotFoundError")


def test_build_ssh_command_plain_no_terminal_wrapping():
    # SSH runs natively via VTE now (see vte_session.py) — build_ssh_command
    # returns the bare ssh invocation, no terminal-emulator wrapping at all.
    conn = Connection(name="x", protocol=Protocol.SSH, host="example.com", port=2222, username="testuser")
    assert launchers.build_ssh_command(conn) == ["ssh", "-p", "2222", "testuser@example.com"]


def test_build_ssh_command_no_port_no_username():
    conn = Connection(name="x", protocol=Protocol.SSH, host="example.com")
    assert launchers.build_ssh_command(conn) == ["ssh", "example.com"]


def test_build_ssh_command_includes_key_path():
    conn = Connection(name="x", protocol=Protocol.SSH, host="example.com", port=22, ssh_key_path="/home/testuser/.ssh/id_rsa")
    assert launchers.build_ssh_command(conn) == ["ssh", "-i", "/home/testuser/.ssh/id_rsa", "-p", "22", "example.com"]


def test_build_ssh_command_key_path_does_not_require_pem_extension():
    # ssh itself never cares about file extensions, only content — a path
    # with no extension at all (the common ~/.ssh/id_rsa case) must be
    # passed through verbatim, same as one ending in .pem.
    conn = Connection(name="x", protocol=Protocol.SSH, host="example.com", ssh_key_path="/no/extension/here")
    assert "-i" in launchers.build_ssh_command(conn)
    assert "/no/extension/here" in launchers.build_ssh_command(conn)


def test_build_ssh_spawn_no_password_is_plain():
    conn = Connection(name="x", protocol=Protocol.SSH, host="example.com")
    argv, envv = launchers.build_ssh_spawn(conn)
    assert argv == ["ssh", "example.com"]
    assert envv is None


def test_build_ssh_spawn_with_password_injects_via_sshpass_if_available():
    import shutil

    conn = Connection(name="x", protocol=Protocol.SSH, host="example.com", password="secret")
    argv, envv = launchers.build_ssh_spawn(conn)
    if shutil.which("sshpass"):
        assert argv[0].endswith("sshpass")
        assert argv[1:] == ["-e", "ssh", "-o", "StrictHostKeyChecking=accept-new", "example.com"]
        assert envv is not None
        assert "SSHPASS=secret" in envv
        # the password must never land in argv (visible to `ps` for other
        # processes on the same machine) — only in the env, read by sshpass
        assert "secret" not in argv
    else:
        # sshpass not installed where this test happens to run: falls back
        # to the plain command, no error, no attempt to inject differently
        assert argv == ["ssh", "example.com"]
        assert envv is None


def test_settings_round_trip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        assert settings.load_settings(path) == settings.AppSettings()  # defaults when missing

        s = settings.AppSettings(
            terminal_font="Fira Code 13",
            terminal_color_scheme="dracula",
        )
        settings.save_settings(s, path)
        loaded = settings.load_settings(path)
        assert loaded == s


def test_settings_tolerates_unknown_old_fields() -> None:
    """A settings.json saved by an older version (e.g. with the now-removed
    rdp_command_override/vnc_command_override fields) must not crash
    loading — unknown keys are just ignored."""
    import json

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        path.write_text(json.dumps({"rdp_command_override": "/a/b", "terminal_template": "xterm -e {cmd}"}))
        loaded = settings.load_settings(path)
        assert loaded.terminal_font == settings.DEFAULT_TERMINAL_FONT


def test_terminal_color_schemes_are_well_formed():
    from rconnect.terminal_themes import COLOR_SCHEMES, SCHEME_LABELS

    label_keys = {key for key, _ in SCHEME_LABELS}
    assert label_keys == set(COLOR_SCHEMES.keys())
    for key, scheme in COLOR_SCHEMES.items():
        if scheme is None:  # "default" — VTE's own colors, nothing to check
            continue
        assert len(scheme["palette"]) == 16, key
        for hex_color in [scheme["background"], scheme["foreground"], *scheme["palette"]]:
            assert hex_color.startswith("#") and len(hex_color) == 7, (key, hex_color)


if __name__ == "__main__":
    test_resolve_binary_override_wins_unconditionally()
    test_resolve_binary_finds_a_real_candidate()
    test_resolve_binary_raises_when_nothing_found()
    test_build_ssh_command_plain_no_terminal_wrapping()
    test_build_ssh_command_no_port_no_username()
    test_build_ssh_command_includes_key_path()
    test_build_ssh_command_key_path_does_not_require_pem_extension()
    test_build_ssh_spawn_no_password_is_plain()
    test_build_ssh_spawn_with_password_injects_via_sshpass_if_available()
    test_settings_round_trip()
    test_settings_tolerates_unknown_old_fields()
    test_terminal_color_schemes_are_well_formed()
    print("OK")
