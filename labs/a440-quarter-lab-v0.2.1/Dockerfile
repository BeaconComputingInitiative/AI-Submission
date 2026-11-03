# BEACON COMPUTING INITIATIVE
# Developer Seal: CJB-DEV-2026
FROM python:3.12-slim
WORKDIR /app
COPY endpoint.py model.py /app/
RUN useradd -u 10001 -m bci && mkdir -p /state && chown bci:bci /state
USER bci
EXPOSE 8000 8080
