FROM agenthub/codex-claude-opencode-runtime:phase15

RUN if ! getent group agenthub >/dev/null; then groupadd -g 1000 agenthub; fi \
    && if ! id -u agenthub >/dev/null 2>&1; then useradd -m -u 1000 -g agenthub -s /bin/bash agenthub; fi \
    && mkdir -p /workspace /home/agenthub \
    && chown -R agenthub:agenthub /workspace /home/agenthub

COPY agenthub-runtime-entrypoint.py /usr/local/bin/agenthub-runtime-entrypoint
RUN chmod +x /usr/local/bin/agenthub-runtime-entrypoint

ENV AGENTHUB_RUNTIME_USER=agenthub
ENV HOME=/home/agenthub
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/agenthub-runtime-entrypoint"]
