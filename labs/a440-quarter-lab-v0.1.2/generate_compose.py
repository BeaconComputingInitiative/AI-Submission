#!/usr/bin/env python3
# BEACON COMPUTING INITIATIVE
# Developer Seal: CJB-DEV-2026
# Component: A440 Twenty Endpoint Docker Compose Generator
from pathlib import Path
p=Path(__file__).with_name('compose.yaml')
lines=['# BEACON COMPUTING INITIATIVE','# Developer Seal: CJB-DEV-2026','services:','  model:','    build: .','    command: python -u model.py','    environment:','      QUARTER_SECONDS: "${QUARTER_SECONDS:-300}"','    ports:','      - "127.0.0.1:8080:8080"','    volumes:','      - a440_state:/state','    restart: unless-stopped','    networks:','      - lab']
for i in range(1,21):
    lines += [f'  endpoint-{i:02d}:','    build: .','    command: python -u endpoint.py','    environment:',f'      ENDPOINT_ID: "{i}"','    restart: unless-stopped','    networks:','      - lab']
lines+=['networks:','  lab:','    internal: true','volumes:','  a440_state:']
p.write_text('\n'.join(lines)+'\n')
print('[BCI] generated compose.yaml with 20 endpoints and model')
