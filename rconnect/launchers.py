"""Build the SSH argv fed into the VTE terminal widget.

SSH has no external client/terminal process at all — it runs natively
inside a VTE widget (see rconnect.vte_session), with just the plain ssh
invocation and no terminal-emulator wrapping. (RDP/VNC client auto-
detection used to live here too; dropped along with that protocol
support.)
"""
from __future__ import annotations

import logging
import os
import shutil

from rconnect.models import Connection

log = logging.getLogger(__name__)


class UnsupportedProtocolError(ValueError):
    pass


class BinaryNotFoundError(RuntimeError):
    """Raised when no candidate binary is on PATH and no override is set."""


def resolve_binary(candidates: list[str], override: str = "", what: str = "client") -> str:
    """override wins unconditionally (not even checked for existence —
    an explicit setting is the user asserting they know what they're
    doing, e.g. a non-PATH absolute path or a wrapper script).
    """
    if override:
        return override
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    raise BinaryNotFoundError(
        f"no {what} found on PATH (tried: {', '.join(candidates)}). "
        f"Install one of these packages, or set an explicit command in Settings."
    )


def build_ssh_command(conn: Connection, extra_ssh_opts: list[str] | None = None) -> list[str]:
    """The plain ssh invocation, with no terminal-emulator wrapping — this
    is fed directly to Vte.Terminal.spawn_async(), which allocates its
    own PTY and runs it natively inside the GTK widget.

    If conn.ssh_key_path is set, it's passed as `-i <path>` verbatim — no
    existence/readability check here. If the file turns out to be
    missing or unreadable by the time this actually runs, ssh's own
    default behavior (print a warning, then fall through to whatever
    other auth methods are configured) already does exactly what's
    wanted: the session just prompts for a password as if no key path
    had been set at all, with no special handling needed on our side.
    """
    argv = ["ssh", *(extra_ssh_opts or [])]
    if conn.ssh_key_path:
        argv += ["-i", conn.ssh_key_path]
    if conn.port:
        argv += ["-p", str(conn.port)]
    argv.append(f"{conn.username}@{conn.host}" if conn.username else conn.host)
    return argv


def build_ssh_spawn(conn: Connection) -> tuple[list[str], list[str] | None]:
    """Like build_ssh_command(), but also auto-fills a stored password via
    `sshpass` when one is set and sshpass is available on PATH — without
    that, ssh always prompts on its own tty (which VTE gives it, being a
    real PTY) and there's no way to answer that prompt programmatically
    without it.

    Returns (argv, envv). envv is None (inherit the app's environment
    unchanged) unless a password is actually being injected, in which
    case it's the full environment plus SSHPASS=<password> — passed via
    the environment rather than argv so the plaintext password doesn't
    show up in `ps` output to other processes on the same machine.
    sshpass itself reads SSHPASS and never re-exposes it to the spawned
    ssh's own argv either.

    If sshpass isn't installed, silently falls back to the plain command
    (same as before this existed) — the user just gets ssh's normal
    on-screen password prompt instead, no error, since this is a
    convenience on top of a command that already works without it.
    """
    if not conn.password:
        return build_ssh_command(conn), None
    sshpass = shutil.which("sshpass")
    if not sshpass:
        log.info("sshpass not found on PATH — SSH password auto-fill skipped, prompting normally")
        return build_ssh_command(conn), None
    # sshpass answers ssh's password prompt, but NOT ssh's separate
    # "unknown host key, are you sure (yes/no)?" prompt for a host never
    # connected to before — it just exits (code 6) instead of falling
    # back to an interactive prompt the way plain ssh would (there's no
    # one left to type "yes" once sshpass owns the pty). Without a
    # stored password, that prompt still reaches the user normally
    # through VTE's real PTY, so this only needs handling in this
    # sshpass-specific path. accept-new auto-trusts a host on first
    # contact (same as a human routinely typing "yes") but still rejects
    # a host whose key later CHANGES — same security posture, just not
    # interactively confirmed.
    argv = build_ssh_command(conn, extra_ssh_opts=["-o", "StrictHostKeyChecking=accept-new"])
    envv = [f"{k}={v}" for k, v in os.environ.items()] + [f"SSHPASS={conn.password}"]
    return [sshpass, "-e"] + argv, envv
