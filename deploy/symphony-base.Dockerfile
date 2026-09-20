FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git openssh-client ripgrep python3 python3-venv \
    libstdc++6 libncurses6 libtinfo6 xz-utils procps \
    && rm -rf /var/lib/apt/lists/*
RUN npm install --global @openai/codex@0.154.0
COPY downloads/symphony-v0.0.3-linux_x86_64 /usr/local/bin/symphony
RUN chmod 755 /usr/local/bin/symphony \
    && mkdir -p /opt/symphony /home/node/.codex /data \
    && chown -R node:node /opt/symphony /home/node/.codex /data
ENV SYMPHONY_INSTALL_DIR=/opt/symphony
USER node
WORKDIR /data
ENTRYPOINT ["/usr/local/bin/symphony"]
