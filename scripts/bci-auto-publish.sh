#!/usr/bin/env bash
# ============================================================
# BEACON COMPUTING INITIATIVE
# Project: BCIPitch — A440 Tonal Network Model
# Component: Five-Commit GitHub Publisher v1.0
# Developer Seal: CJB-DEV-2026
# ============================================================

set -euo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
GIT_DIR="$(git -C "$ROOT" rev-parse --absolute-git-dir)"

STATE="$GIT_DIR/BCI-LAST-PUBLISHED"
LOG="$GIT_DIR/BCI-PUBLISH.log"
LOCK="$GIT_DIR/BCI-PUBLISH.lock"

REMOTE="origin"
BRANCH="main"
THRESHOLD=5

cd "$ROOT"

record() {
    printf '%s | %s | %s\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        "CJB-DEV-2026" "$*" >> "$LOG"
}

# Only publish the designated release branch.
CURRENT="$(git symbolic-ref --quiet --short HEAD || true)"

if [[ "$CURRENT" != "$BRANCH" ]]; then
    record "SKIP: Current branch is ${CURRENT:-detached}"
    exit 0
fi

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    record "FAIL: Git remote $REMOTE is missing"
    echo "[BCI][FAIL] Configure the origin remote."
    exit 1
fi

# Serialize publisher invocations.
if ! mkdir "$LOCK" 2>/dev/null; then
    record "SKIP: Publisher already running"
    exit 0
fi

trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

HEAD="$(git rev-parse HEAD)"

if [[ ! -f "$STATE" ]]; then
    record "FAIL: Publication baseline not initialized"
    exit 1
fi

LAST="$(cat "$STATE")"

if ! git cat-file -e "${LAST}^{commit}" 2>/dev/null; then
    record "FAIL: Publication baseline is invalid"
    exit 1
fi

# Preserve history; reject rewritten ancestry.
if ! git merge-base --is-ancestor "$LAST" "$HEAD"; then
    record "BLOCKED: Commit ancestry changed"
    echo "[BCI][BLOCKED] Review publication baseline."
    exit 1
fi

COUNT="$(git rev-list --count "${LAST}..${HEAD}")"

echo "[BCI] Commits since last publication: $COUNT/$THRESHOLD"

if (( COUNT < THRESHOLD )); then
    record "PENDING: $COUNT/$THRESHOLD commits"
    exit 0
fi

echo "[BCI] Publishing $COUNT commits to $REMOTE/$BRANCH"

# Push if and only if the threshold and safety gates pass.
# Never force-push; GitHub rejects conflicting remote history.
if git push "$REMOTE" "HEAD:refs/heads/$BRANCH"; then
    printf '%s\n' "$HEAD" > "$STATE"
    record "PASS: Published $COUNT commits at $HEAD"
    echo "[BCI][PASS] GitHub publication completed."
else
    record "FAIL: GitHub push rejected; counter preserved"
    echo "[BCI][FAIL] Push failed. Pending commits retained."
    exit 1
fi
