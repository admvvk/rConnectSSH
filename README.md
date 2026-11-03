# rConnectSSH

An SSH connection manager for Linux (GTK), in the spirit of mRemoteNG: the
connections tree is docked on the left inside a single application window,
with sessions opening as tabs on the right (not as separate top-level
windows, like Remmina does).

Sessions run through a native built-in VTE terminal widget — no external
terminal emulator needed at all — with a right-click Copy/Paste context
menu.

Features: a connections tree editor (groups + SSH connections), JSON
persistence, mRemoteNG import, opt-in master-password encryption of
stored passwords, and a Settings dialog for the terminal's font/color
scheme.

## Installation

### Option 1: .deb package (recommended, Debian/Ubuntu and derivatives)

Download `rconnectssh_<version>_all.deb` from the
[Releases](https://github.com/admvvk/rConnectSSH/releases) page, then:

```sh
sudo apt install ./rconnectssh_<version>_all.deb
```

`apt` resolves and installs every dependency automatically (GTK3/VTE
bindings, OpenSSH client, sshpass) — nothing else to install by hand. The
package works on Debian 12 (bookworm) and newer, and on Ubuntu and other
Debian-derivatives with the same package names available; it was verified
with a clean `apt install` on a fresh `debian:bookworm-slim` image with
nothing pre-installed.

Once installed, launch it from your desktop environment's applications
menu (under **Network** — the same category Remmina uses) or from a
terminal with:

```sh
rconnectssh
```

To remove it: `sudo apt remove rconnectssh`.

### Option 2: manual install from the source tarball

Download `rConnectSSH-<version>-src.tar.gz` from the
[Releases](https://github.com/admvvk/rConnectSSH/releases) page (or clone
the repository directly), then install the system dependencies and the
Python package:

```sh
tar xzf rConnectSSH-<version>-src.tar.gz
cd rConnectSSH-<version>

# Debian/Ubuntu package names — see "Dependencies" below for what each
# one is for and alternatives on other distros.
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-vte-2.91 \
    python3-cryptography openssh-client sshpass

pip install --break-system-packages --no-deps .
python3 -m rconnect
```

`--break-system-packages --no-deps` is intentional, not a workaround to
remove later: `rconnect`'s own code has no pip-installable runtime
dependencies that aren't already satisfied by the apt packages above
(see the "PyGObject must stay a system package" comment in
`pyproject.toml`), so this only ever touches `rconnect` itself, not
anything managed by apt.

This path does not create a menu entry or a plain `rconnectssh` command —
use `python3 -m rconnect` to launch it, or copy
`packaging/rconnectssh.desktop` and `packaging/icons/rconnectssh.png`
into `~/.local/share/applications/` and `~/.local/share/icons/` yourself
if you want one without building the .deb.

### Dependencies

| Package (Debian/Ubuntu) | What it's for |
|---|---|
| `python3-gi`, `gir1.2-gtk-3.0` | GTK3 GUI toolkit bindings |
| `gir1.2-vte-2.91` | the VTE terminal widget used for SSH sessions |
| `python3-cryptography` | opt-in master-password encryption of stored passwords |
| `openssh-client` | the `ssh` command itself |
| `sshpass` | SSH password auto-fill (optional — without it, SSH sessions with a stored password just prompt for it inside the terminal instead) |

All of the above except `python3-cryptography`/the GTK/VTE bindings are
**optional in practice**: if `sshpass` is missing, password auto-fill is
just skipped and you get the normal interactive password prompt instead.

### Troubleshooting

- **`apt install ./rconnectssh_*.deb` fails to resolve dependencies**:
  make sure your `/etc/apt/sources.list` actually has the `main`
  component enabled for your release (some minimal/cloud images ship
  without it) and run `sudo apt update` first — the package itself has no
  unusual repositories, only standard Debian/Ubuntu package names.
- **SSH session doesn't auto-fill a stored password**: install
  `sshpass`; this is a soft dependency, not a hard requirement — without
  it the session still works, it just prompts for the password manually
  inside the terminal instead.
- **No icon/menu entry after a manual (tarball) install**: that
  install path doesn't create one — see the note at the end of "Option 2"
  above for how to add it by hand, or use the .deb instead.

## How sessions work

Sessions run through a native [VTE](https://gitlab.gnome.org/GNOME/vte)
terminal widget (`Vte.Terminal`, the same library behind GNOME Terminal,
xfce4-terminal and Terminator), packed directly into the tab and spawning
`ssh` into its own PTY — just a normal GTK widget, like a label or a
button. No external terminal emulator, no process/window discovery, no
focus/resize workarounds: GTK's normal widget layout and focus chain
handle both for free. See `rconnect/vte_session.py`, which also adds the
right-click Copy/Paste context menu VTE doesn't provide on its own.
