#!/usr/bin/env bash
# ============================================================
# BEACON COMPUTING INITIATIVE
# Component: A440 M4.4 Resilient Public Data Recovery v1.0
# Developer Seal: CJB-DEV-2026
# ============================================================
set -euo pipefail

ROOT="$HOME/Desktop/BCIPitch"
DATA="$HOME/Documents/A440-M4.4-CA-NV-1990-2025"
BRIDGE="$ROOT/src/bcipitch/realworld_bridge.py"

command -v curl >/dev/null || { echo '[BCI][FAIL] curl is required'; exit 1; }
command -v python3 >/dev/null || { echo '[BCI][FAIL] python3 is required'; exit 1; }
[[ -f "$BRIDGE" ]] || { echo '[BCI][FAIL] M4.4 bridge not installed'; exit 1; }
mkdir -p "$HOME/Documents"

if [[ -e "$DATA" ]]; then
    echo "[BCI][INFO] Data directory already exists: $DATA"
    echo '[BCI][INFO] Checking it without overwriting anything.'
    python3 - "$BRIDGE" "$DATA" <<'PY'
import importlib.util, pathlib, sys
bridge_path, data_path = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(bridge_path.parent))
spec = importlib.util.spec_from_file_location('bci_realworld_bridge', bridge_path)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
aligned, _ = bridge.load_paired_data(data_path)
print(f'[BCI][PASS] Existing dataset verified: {len(aligned)} aligned monthly records')
PY
    exit 0
fi

STAGE="$(mktemp -d "${DATA}.staging.XXXXXX")"
trap 'rm -rf -- "$STAGE"' EXIT

for SID in CAUR NVUR; do
    URL="https://fred.stlouisfed.org/graph/fredgraph.csv?id=${SID}&cosd=1990-01-01&coed=2025-12-01"
    echo "[BCI][FETCH] ${SID}: retries enabled; up to 120 seconds per attempt"
    curl --fail --location --silent --show-error \
        --connect-timeout 20 --max-time 120 \
        --retry 4 --retry-delay 5 --retry-all-errors \
        --max-filesize 3000000 \
        --output "$STAGE/$SID.csv" "$URL"
done

python3 - "$BRIDGE" "$STAGE" <<'PY'
import importlib.util, json, pathlib, sys
from datetime import datetime, timezone
from urllib.parse import urlencode

bridge_path, data_dir = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(bridge_path.parent))
spec = importlib.util.spec_from_file_location('bci_realworld_bridge', bridge_path)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

sources = {}
for sid, description in bridge.PUBLIC_SERIES.items():
    content = (data_dir / f'{sid}.csv').read_bytes()
    if len(content) > bridge.MAX_DOWNLOAD_BYTES:
        raise ValueError(f'FRED CSV exceeds size limit for {sid}')
    values = bridge.parse_csv(content, sid)
    if len(values) < 100:
        raise ValueError(f'Insufficient observations for {sid}: {len(values)}')
    if min(values).isoformat() < '1990-01-01' or max(values).isoformat() > '2025-12-01':
        raise ValueError(f'{sid} observations outside requested date range')
    params = urlencode({'id': sid, 'cosd': '1990-01-01', 'coed': '2025-12-01'})
    sources[sid] = {
        'filename': f'{sid}.csv', 'series_id': sid,
        'name': description,
        'original_provider': 'U.S. Bureau of Labor Statistics',
        'download_provider': 'Federal Reserve Bank of St. Louis FRED',
        'source_url': f'{bridge.SOURCE_URL}?{params}',
        'reference_url': f'https://fred.stlouisfed.org/series/{sid}',
        'retrieved_utc': datetime.now(timezone.utc).isoformat(),
        'sha256': bridge.sha256_bytes(content),
        'frequency': bridge.MONTH_FREQ,
        'unit': bridge.MONTH_UNIT,
        'seasonal_adjustment': bridge.SEASONALITY,
        'rows_with_values': len(values),
    }

metadata = {
    'project': 'BCIPitch', 'model': 'A440',
    'developer_seal': bridge.SEAL,
    'format_version': bridge.VERSION,
    'local_series': 'CAUR', 'reference_series': 'NVUR',
    'data_notice': 'Series may have undergone revision; not vintage-correct real-time data.',
    'sources': sources,
}
(data_dir / 'sources.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
aligned, _ = bridge.load_paired_data(data_dir)
records = bridge.build_windows(aligned)
bridge.chronological_splits(records)
print(f'[BCI][PASS] Aligned observations: {len(aligned)}; eligible Octets: {len(records)}')
PY

(
    cd "$STAGE"
    sha256sum CAUR.csv NVUR.csv sources.json > SHA256SUMS
    sha256sum -c SHA256SUMS
)

# Publish if and only if the complete, verified dataset has no existing destination.
if [[ -e "$DATA" ]]; then
    echo '[BCI][BLOCKED] Destination appeared during download; refusing overwrite.'
    exit 1
fi
mv -T -- "$STAGE" "$DATA"
trap - EXIT

echo "[BCI][PASS] Complete FRED dataset installed: $DATA"
echo '[BCI] Now run: bash ~/Documents/run-a440-m44.sh'
echo '[BCI] Developer Seal: CJB-DEV-2026'
