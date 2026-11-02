#!/usr/bin/env bash
# ============================================================
# BEACON COMPUTING INITIATIVE
# Component: BCIPitch Development Log Writer v1.0
# Developer Seal: CJB-DEV-2026
# ============================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/docs/DEVLOG.md"
MANIFEST="$ROOT/docs/DEVLOG-SHA256SUMS"

STATUS="${1:-}"
COMPONENT="${2:-}"
DETAILS="${3:-}"

if [[ ! -f "$LOG" ]]; then
    echo "[BCI][FAIL] Development log not found."
    exit 1
fi

case "$STATUS" in
    PASS|FAIL|INFO|START|COMPLETE|BLOCKED|DECISION)
        ;;
    *)
        echo "Usage: $0 STATUS COMPONENT DETAILS"
        echo "Statuses: PASS FAIL INFO START COMPLETE BLOCKED DECISION"
        exit 2
        ;;
esac

if [[ -z "$COMPONENT" || -z "$DETAILS" ]]; then
    echo "[BCI][FAIL] Component and details are required."
    exit 2
fi

# Normalize multiline input so a single entry remains well formed.
COMPONENT="${COMPONENT//$'\n'/ }"
DETAILS="${DETAILS//$'\n'/ }"

STAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
GIT_COMMIT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo 'uncommitted')"

# Append if and only if the development log and entry fields are valid.
{
    printf '\n### %s | %s | %s\n\n' "$STAMP" "$STATUS" "$COMPONENT"
    printf '**Details:** %s\n\n' "$DETAILS"
    printf '**Git:** %s\n' "$GIT_COMMIT"
    printf '**Developer Seal:** CJB-DEV-2026\n\n'
    printf '%s\n' '---'
} >> "$LOG"

# SHA-256 manifest excludes itself to avoid circular hashing.
(
    cd "$ROOT"
    sha256sum docs/DEVLOG.md scripts/devlog.sh \
        > "$MANIFEST"
)

echo "[BCI][$STATUS] Development entry recorded."
echo "[BCI][SHA256] $MANIFEST"
