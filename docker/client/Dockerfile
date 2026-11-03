FROM debian:trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pip \
    python3-cryptography gir1.2-vte-2.91 \
    xvfb xterm x11-apps imagemagick procps xauth \
    openssh-client sshpass \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY rconnect /app/rconnect
COPY docker/client/smoke_test_editor.py /app/smoke_test_editor.py
COPY docker/client/smoke_test_mremoteng_import.py /app/smoke_test_mremoteng_import.py
COPY docker/client/smoke_test_vte_ssh.py /app/smoke_test_vte_ssh.py
COPY docker/client/smoke_test_vte_password.py /app/smoke_test_vte_password.py

# --break-system-packages: this is a throwaway dev/test container, not a
# system install; --no-deps because PyGObject (gi) must stay the apt
# package above, not a pip wheel (see pyproject.toml comment).
RUN pip install --break-system-packages --no-deps -e /app

CMD ["bash", "-c", "Xvfb :99 -screen 0 1280x800x24 & sleep 1 && DISPLAY=:99 python3 -m rconnect > /app/log.txt 2>&1 & sleep 3600"]
