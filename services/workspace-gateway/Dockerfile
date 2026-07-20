ARG LIGHTRAG_IMAGE=ghcr.io/hkuds/lightrag:latest@sha256:de09cd75e32b6b45b104625a9fb229f84f3dec4827ecffc825aa4438b196cbe6
FROM ${LIGHTRAG_IMAGE}

COPY services/workspace-gateway /opt/workspace-gateway
RUN pip install --no-cache-dir /opt/workspace-gateway

ENTRYPOINT ["lightrag-workspace-gateway"]
