# The locally verified official Symphony/Codex base described in docs/15-symphony.md.
FROM maven:3.9.11-eclipse-temurin-21 AS java-tools
FROM innovation-symphony:0.0.3
USER root
COPY --from=java-tools /opt/java/openjdk /opt/java/openjdk
COPY --from=java-tools /usr/share/maven /usr/share/maven
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=/opt/java/openjdk/bin:/usr/share/maven/bin:${PATH}
RUN java -version && mvn --version
COPY requirements-review.txt /opt/symphony-validation/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m venv /opt/symphony-validation/venv \
    && /opt/symphony-validation/venv/bin/python -m pip install --disable-pip-version-check \
        -r /opt/symphony-validation/requirements.txt \
    && /opt/symphony-validation/venv/bin/python -m pip check \
    && /opt/symphony-validation/venv/bin/python -m pip freeze \
        > /opt/symphony-validation/installed.txt
COPY prepare_symphony_workspace.py /opt/symphony-tools/prepare_workspace.py
ENV PIP_CACHE_DIR=/data/cache/pip \
    NPM_CONFIG_CACHE=/data/cache/npm \
    PIP_DISABLE_PIP_VERSION_CHECK=1
USER node
