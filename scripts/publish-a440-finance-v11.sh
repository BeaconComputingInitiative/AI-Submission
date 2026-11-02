#!/usr/bin/env bash
# =============================================================
# BEACON COMPUTING INITIATIVE
# Component: A440 Financial Dataset v1.1.0 Verified Publisher
# Developer Seal: CJB-DEV-2026
# =============================================================
# Publishes the exact verified archive and reviewable source tools.
# This script neither trains models nor approves production deployment.
set -euo pipefail

REPO="${BCI_REPO_PATH:-$HOME/Desktop/BCIPitch}"
SOURCE="${BCI_A440_FINANCE_ZIP:-$HOME/Downloads/A440-Financial-Multifaceted-Dataset-v1.1.0.zip}"
NAME="A440-Financial-Multifaceted-Dataset-v1.1.0.zip"
EXPECTED="a2bfedad080d1d807815d2cad0a69bbbf33a366822b171eb42b98d462b3863c1"
TOP="A440-Financial-Multifaceted-Dataset-v1.1.0"
DEST="$REPO/datasets/financial/v1.1.0"
mkdir -p "$HOME/Documents"

for binary in git python3 unzip sha256sum mktemp; do
    command -v "$binary" >/dev/null || {
        echo "[BCI][FAIL] Missing executable: $binary"
        exit 1
    }
done

[[ -f "$SOURCE" ]] || {
    echo "[BCI][FAIL] Missing dataset ZIP: $SOURCE"
    exit 1
}
[[ -d "$REPO/.git" ]] || {
    echo "[BCI][FAIL] Not a Git checkout: $REPO"
    exit 1
}

REMOTE="$(git -C "$REPO" remote get-url origin)"
case "$REMOTE" in
    *github.com:BeaconComputingInitiative/AI-Submission*|*github.com/BeaconComputingInitiative/AI-Submission*) ;;
    *) echo "[BCI][FAIL] Unexpected origin: $REMOTE"; exit 1 ;;
esac
[[ "$(git -C "$REPO" branch --show-current)" == main ]] || {
    echo "[BCI][FAIL] Switch to main before publishing."
    exit 1
}
[[ -z "$(git -C "$REPO" status --porcelain)" ]] || {
    echo "[BCI][FAIL] Commit or stash existing changes before publishing."
    exit 1
}

# Release if and only if the archive matches its reviewed SHA-256.
ACTUAL="$(sha256sum "$SOURCE" | awk '{print $1}')"
[[ "$ACTUAL" == "$EXPECTED" ]] || {
    echo "[BCI][FAIL] Dataset ZIP checksum mismatch."
    exit 1
}

STAGE="$(mktemp -d "$HOME/Documents/a440-finance-v11.XXXXXX")"
trap 'rm -rf -- "$STAGE"' EXIT

unzip -tqq "$SOURCE"
unzip -q "$SOURCE" -d "$STAGE"
DIR="$STAGE/$TOP"
[[ -d "$DIR" && -f "$DIR/SHA256SUMS" ]] || {
    echo "[BCI][FAIL] Missing expected archive content."
    exit 1
}

(
    cd "$DIR"
    sha256sum -c SHA256SUMS
    python3 scripts/verify_dataset.py --root .
)

echo "[BCI][PASS] Numerical, split, provenance and SHA-256 audits."

# Advance only if all validations pass, and synchronize without rewriting history.
git -C "$REPO" fetch origin main
git -C "$REPO" pull --ff-only origin main
[[ -z "$(git -C "$REPO" status --porcelain)" ]] || {
    echo "[BCI][FAIL] Unexpected local modifications after sync."
    exit 1
}

mkdir -p "$DEST/docs" "$DEST/scripts"

# Preserve the canonical archive. Publish source + documentation for review.
cp -- "$SOURCE" "$DEST/$NAME"
cp -- "$DIR/README.md" "$DIR/manifest.json" "$DIR/SHA256SUMS" "$DEST/"
cp -- "$DIR/docs/"* "$DEST/docs/"
cp -- "$DIR/scripts/"* "$DEST/scripts/"

(
    cd "$DEST"
    sha256sum -c ARCHIVE-SHA256SUMS
    for f in README.md manifest.json SHA256SUMS; do
        cmp -- "$f" "$DIR/$f"
    done
)

git -C "$REPO" add -- \
    datasets/financial/v1.1.0/README.md \
    datasets/financial/v1.1.0/manifest.json \
    datasets/financial/v1.1.0/SHA256SUMS \
    datasets/financial/v1.1.0/docs \
    datasets/financial/v1.1.0/scripts
git -C "$REPO" add -f -- "datasets/financial/v1.1.0/$NAME"

if git -C "$REPO" diff --cached --quiet; then
    echo "[BCI][PASS] No new changes; archive and sources already committed."
else
    git -C "$REPO" commit -m "data(a440): publish verified multifaceted financial dataset v1.1.0"
    git -C "$REPO" push origin main
fi

echo "[BCI][PASS] Dataset publication completed."
echo "[BCI] Repository: https://github.com/BeaconComputingInitiative/AI-Submission"
echo "[BCI] Developer Seal: CJB-DEV-2026"
