#!/bin/bash
# Builds rconnectssh_<version>_all.deb from this repo checkout.
#
# Intentionally NOT a full debhelper/dpkg-buildpackage setup (dh-python
# etc) — this is a small, pure-Python(+GTK bindings via apt Depends:)
# app with nothing to compile, so a plain `dpkg-deb --build` over a
# hand-staged file tree is simpler and has fewer moving parts. Needs
# dpkg-dev (dpkg-deb) and fakeroot on the build machine (see
# packaging/README.md for the exact clean-container build/test recipe
# this was developed and verified against).
#
# Usage: packaging/build_deb.sh [version]   (default: 0.1.0)
set -euo pipefail

VERSION="${1:-0.1.0}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "Building rconnectssh ${VERSION} (all) from ${REPO_ROOT}"

mkdir -p "$STAGE/DEBIAN"
sed "s/__VERSION__/${VERSION}/" "$REPO_ROOT/packaging/debian/control.in" > "$STAGE/DEBIAN/control"

# The Python package itself: installed into the system site-packages
# location Debian's own python3-* packages use (NOT pip, NOT a venv —
# consistent with this project's existing rule that the GTK/VTE bindings
# must stay system packages, not pip wheels; keeping the app's own code
# in the same kind of location avoids mixing install mechanisms).
mkdir -p "$STAGE/usr/lib/python3/dist-packages"
cp -r "$REPO_ROOT/rconnect" "$STAGE/usr/lib/python3/dist-packages/rconnect"
find "$STAGE/usr/lib/python3/dist-packages/rconnect" -name '__pycache__' -exec rm -rf {} +

mkdir -p "$STAGE/usr/bin"
install -m 755 "$REPO_ROOT/packaging/rconnectssh" "$STAGE/usr/bin/rconnectssh"

mkdir -p "$STAGE/usr/share/applications"
install -m 644 "$REPO_ROOT/packaging/rconnectssh.desktop" "$STAGE/usr/share/applications/rconnectssh.desktop"

mkdir -p "$STAGE/usr/share/pixmaps"
install -m 644 "$REPO_ROOT/packaging/icons/rconnectssh.png" "$STAGE/usr/share/pixmaps/rconnectssh.png"

mkdir -p "$REPO_ROOT/dist"
OUT="$REPO_ROOT/dist/rconnectssh_${VERSION}_all.deb"
fakeroot dpkg-deb --build "$STAGE" "$OUT"
echo "Built: $OUT"
