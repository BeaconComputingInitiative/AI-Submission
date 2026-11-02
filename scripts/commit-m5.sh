#!/usr/bin/env bash
# ============================================================
# BEACON COMPUTING INITIATIVE
# Project: BCIPitch
# Component: Commit 5 / GitHub Publication
# Developer Seal: CJB-DEV-2026
# ============================================================

set -euo pipefail

ROOT="/home/chance/Desktop/BCIPitch"
REMOTE="https://github.com/BeaconComputingInitiative/AI-Submission.git"
THRESHOLD=5

cd "$ROOT"

fail() {
    echo "[BCI][BLOCKED] $*" >&2
    exit 1
}

echo "=== BCI REPOSITORY VERIFICATION ==="

[[ "$(git rev-parse --show-toplevel)" == "$ROOT" ]] ||
    fail "Incorrect Git repository"

[[ "$(git remote get-url origin)" == "$REMOTE" ]] ||
    fail "Incorrect GitHub remote"

[[ "$(git branch --show-current)" == "main" ]] ||
    fail "Expected branch main"

git diff --cached --quiet ||
    fail "Existing staged changes must be reviewed"

git diff --quiet ||
    fail "Existing tracked modifications must be reviewed"

[[ "$(git config --get commit.gpgsign)" == "true" ]] ||
    fail "Git commit signing is not enabled"

GIT_DIR="$(git rev-parse --absolute-git-dir)"

[[ -x "$GIT_DIR/hooks/post-commit" ]] ||
    fail "Git post-commit hook is unavailable"

grep -q 'bci-auto-publish.sh' \
    "$GIT_DIR/hooks/post-commit" ||
    fail "BCI publishing hook is not installed"

[[ -x scripts/bci-auto-publish.sh ]] ||
    fail "Publisher is unavailable"

echo "=== VERIFY PUBLICATION BASELINE ==="

[[ -s "$GIT_DIR/BCI-LAST-PUBLISHED" ]] ||
    fail "Publication baseline missing"

BASE="$(cat "$GIT_DIR/BCI-LAST-PUBLISHED")"

git fetch --quiet origin main

REMOTE_HEAD="$(git rev-parse origin/main)"
HEAD="$(git rev-parse HEAD)"

[[ "$REMOTE_HEAD" == "$BASE" ]] ||
    fail "GitHub changed since the publication baseline"

git merge-base --is-ancestor "$BASE" "$HEAD" ||
    fail "Local commit history diverged"

COUNT="$(git rev-list --count "${BASE}..HEAD")"

echo "[BCI] Pending commits: $COUNT/$THRESHOLD"

# Publish if and only if four local commits are present.
[[ "$COUNT" == "4" ]] ||
    fail "Expected 4 unpublished commits before Commit 5"

echo "=== VERIFY ENGINEERING RECORDS ==="

bash -n scripts/bci-auto-publish.sh
bash -n scripts/devlog.sh

sha256sum -c docs/DEVLOG-SHA256SUMS
sha256sum -c docs/M2-COMPUTE-AUDIT.json.sha256
sha256sum -c docs/README-RECONCILIATION.SHA256SUMS

echo "=== VERIFY FOUNDATION TESTS ==="

python3 -m pytest -q test_bcipitch.py

echo "=== VALIDATE RELEASE FILE PATHS ==="

# Inspect filenames in previous commits and any staged files.
python3 - <<'PY'
import subprocess
from pathlib import PurePosixPath

def git_paths(*args):
    result = subprocess.check_output(
        ["git", *args]
    )
    return [
        p.decode("utf-8", "surrogateescape")
        for p in result.split(b"\0")
        if p
    ]

paths = git_paths(
    "diff", "--name-only", "-z", "origin/main", "HEAD"
)

blocked_extensions = (
    ".pt", ".pth", ".safetensors",
    ".db", ".sqlite", ".sqlite3",
    ".pem", ".key",
)

blocked_names = {
    ".env",
    "id_rsa",
    "id_ed25519",
}

for path in paths:
    p = PurePosixPath(path)

    if (
        p.suffix.lower() in blocked_extensions
        or p.name in blocked_names
        or "__pycache__" in p.parts
        or "backups" in p.parts
        or ".ssh" in p.parts
    ):
        raise SystemExit(
            f"[BCI][BLOCKED] Restricted release path: {path}"
        )

print("[BCI][PASS] Filename policy verified")
print("[BCI] Previously committed release files:", len(paths))
PY

echo "=== GENERATE PUBLICATION DOCUMENTATION ==="

cat <<'MD' > docs/milestones/M5-GITHUB-PUBLISHING.md
# BEACON COMPUTING INITIATIVE
# BCIPitch — GitHub Publication Protocol

**Developer Seal:** CJB-DEV-2026
**Project:** BCIPitch
**Architecture:** A440 Tonal Network Model
**Version:** 1.0

## Publication policy

BCIPitch uses a five-commit publication cycle.

Commits 1–4 remain local. The fifth local commit
triggers the post-commit publication hook.

The hook pushes the accumulated commits to:

BeaconComputingInitiative/AI-Submission

Branch: main

## Safety requirements

Publication occurs if and only if:

1. The project Git root is correct.
2. The remote points to the intended repository.
3. Local history descends from the publication baseline.
4. The remote has not diverged.
5. The five-commit threshold has been reached.
6. Git accepts the push without force.
7. Authentication and network connectivity succeed.

The publication counter resets only after a successful push.

## Release contents

The first consolidated source publication includes:

- M1 evidence pipeline and unit tests
- A440 neural training source
- M2 evaluation results
- M2.1 controlled Octet benchmarks
- M2.2 learned harmonic tournament
- M2.3 parameter-matched experiments
- Engineering development log
- Compute audit
- SHA-256 manifests
- Five-commit publisher source

## Exclusions

Local neural checkpoints are not published.

Local customer databases, credentials, SSH keys,
telemetry, and runtime caches are excluded.

## Experimental limitations

A440 is not yet a pretrained general-purpose language model.

Published benchmarks are synthetic numerical experiments.
They do not establish enterprise deployment readiness
or superiority over established language models.

## Verification

The actual GitHub branch must be checked after pushing.

A successful local Git commit alone does not establish
that the remote repository was updated.

## Authorship

Founder and Architect: Chance Joaquin Boone

Developer Seal: CJB-DEV-2026

Observe accurately.
Preserve faithfully.
Analyze transparently.
Communicate securely.
Act deliberately.
MD

echo "=== GENERATE SHA-256 MANIFEST ==="

sha256sum \
    scripts/bci-auto-publish.sh \
    scripts/commit-m5.sh \
    docs/milestones/M5-GITHUB-PUBLISHING.md \
    > docs/milestones/M5-PUBLISH-SHA256SUMS

sha256sum -c docs/milestones/M5-PUBLISH-SHA256SUMS

echo "=== STAGE PUBLICATION INFRASTRUCTURE ==="

git add -- \
    scripts/bci-auto-publish.sh \
    scripts/commit-m5.sh \
    scripts/commit-m5.sh.sha256 \
    docs/milestones/M5-GITHUB-PUBLISHING.md \
    docs/milestones/M5-PUBLISH-SHA256SUMS

git diff --cached --check

echo "=== VERIFY EXACT STAGED FILES ==="

diff -u \
    <(printf '%s\n' \
        scripts/bci-auto-publish.sh \
        scripts/commit-m5.sh \
        scripts/commit-m5.sh.sha256 \
        docs/milestones/M5-GITHUB-PUBLISHING.md \
        docs/milestones/M5-PUBLISH-SHA256SUMS | sort) \
    <(git diff --cached --name-only | sort) ||
    fail "Unexpected staged files detected"

echo "=== PUBLICATION REVIEW ==="

git diff --cached --stat

echo
echo "[BCI] This operation will publish five commits"
echo "[BCI] to the PUBLIC GitHub repository:"
echo "[BCI] $REMOTE"
echo

read -r -p \
    "Type PUBLISH to approve this first release: " \
    CONFIRM

[[ "$CONFIRM" == "PUBLISH" ]] ||
    fail "Publication was not approved"

echo "=== CREATE COMMIT 5 ==="

git commit -m \
    "release(bcipitch): establish five-commit publication infrastructure"

echo "=== CHECK GITHUB PUBLICATION ==="

# The post-commit hook should already have attempted the push.
# Retry only if the baseline was not advanced.

CURRENT_HEAD="$(git rev-parse HEAD)"
LAST_PUBLISHED="$(cat "$GIT_DIR/BCI-LAST-PUBLISHED")"

if [[ "$LAST_PUBLISHED" != "$CURRENT_HEAD" ]]; then
    echo "[BCI][INFO] Retrying pending publication"
    GIT_TERMINAL_PROMPT=0 \
        ./scripts/bci-auto-publish.sh ||
        fail "Automatic push failed; local commit preserved"
fi

REMOTE_VERIFIED="$(
    git ls-remote origin refs/heads/main | awk '{print $1}'
)"

[[ "$REMOTE_VERIFIED" == "$CURRENT_HEAD" ]] ||
    fail "Remote main does not match local HEAD"

echo
echo "[BCI][PASS] GitHub publication verified"
echo "[BCI][PASS] Five-commit cycle completed"
echo "[BCI] Remote SHA: $REMOTE_VERIFIED"
echo "Developer Seal: CJB-DEV-2026"
