FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash testuser \
    && echo "testuser:testpass" | chpasswd \
    && mkdir -p /run/sshd
EXPOSE 22
CMD ["/usr/sbin/sshd", "-D", "-e"]
