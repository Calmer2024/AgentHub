ARG AGENTHUB_RUNTIME_BASE_IMAGE=agenthub/codex-claude-opencode-runtime:phase15
FROM ${AGENTHUB_RUNTIME_BASE_IMAGE}

ENV PIP_NO_INPUT=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=60
ENV PIP_INDEX_URL=https://repo.huaweicloud.com/repository/pypi/simple
ENV PIP_TRUSTED_HOST=repo.huaweicloud.com

RUN set -eux; \
    if command -v apt-get >/dev/null 2>&1; then \
        export DEBIAN_FRONTEND=noninteractive; \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            ca-certificates \
            fonts-noto-cjk \
            fonts-noto-color-emoji \
            libreoffice-writer \
            pandoc \
            python3-docx \
            python3-pip \
            python3-venv; \
        rm -rf /var/lib/apt/lists/*; \
    else \
        python3 -m pip install --no-cache-dir python-docx; \
    fi; \
    python3 -c "import docx; import zipfile; print('agenthub runtime document toolchain ready')"; \
    if command -v pandoc >/dev/null 2>&1; then pandoc --version >/dev/null; fi; \
    if command -v libreoffice >/dev/null 2>&1; then libreoffice --version >/dev/null; fi

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
