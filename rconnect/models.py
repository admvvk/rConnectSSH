"""In-memory data model for the connections tree (Group -> Connection).

SSH only: RDP/VNC support (and the X11-reparenting embedding it needed)
was dropped — see the project notes for why. Persistence/import (own
storage format, mRemoteNG import) lives in storage.py / importers/.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Protocol(enum.Enum):
    SSH = "ssh"


@dataclass
class Connection:
    name: str
    protocol: Protocol
    host: str
    port: int | None = None
    username: str = ""
    # Password storage/encryption is a separate, not-yet-designed concern;
    # plain field here is a placeholder for the UI skeleton only.
    password: str = ""
    # Path to a private key file (PEM, with or without a .pem extension —
    # ssh itself doesn't care about the extension, only the file's actual
    # content). Empty = no explicit key, same as not passing -i at all. If
    # the path is set but the file turns out to be missing/unreadable at
    # connect time, we deliberately do NOT validate or special-case that
    # ourselves — ssh's own default behavior (warn on stderr, then fall
    # through to its other configured auth methods) already gives exactly
    # the wanted fallback: the session just prompts for a password as if
    # none had been configured as a key at all. See
    # launchers.build_ssh_command().
    ssh_key_path: str = ""


@dataclass
class Group:
    name: str
    connections: list[Connection] = field(default_factory=list)
    subgroups: list["Group"] = field(default_factory=list)


def demo_tree() -> Group:
    """Static sample data shown on first run, before the user has added
    any real connections of their own. Deliberately generic placeholder
    values, not a real host: 192.0.2.1 is from the IANA/RFC 5737
    TEST-NET-1 block reserved specifically for documentation/examples —
    guaranteed to never be a real, reachable address, unlike a private
    (192.168.x.x/10.x.x.x) address, which could be mistaken for an actual
    machine on *some* real network.
    """
    root = Group(name="Connections")
    example = Group(name="Example")
    example.connections.append(
        Connection(name="example-ssh-host", protocol=Protocol.SSH, host="192.0.2.1", port=22, username="user")
    )
    root.subgroups.append(example)
    return root
