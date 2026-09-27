#!/usr/bin/env bash
# Fetch pinned upstream code and binaries, and set up the Python venv.
# Pins live in reference/UPSTREAM.md; keep the two in sync.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor"

OTD_REPO="https://github.com/opentaxdocument/otd-spec"
OTD_PIN="be6452a"
OPENTAX_REPO="https://github.com/filedcom/opentax"
OPENTAX_PIN="c4c7d72"      # == release tag below
OPENTAX_TAG="v2.0.4"
PYTHON_VERSION="3.11"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null || die "git is required"
command -v curl >/dev/null || die "curl is required"

# Clone (or update) a repo and check out its pin.
fetch_pinned() {
  local repo="$1" pin="$2" dest="$3"
  if [[ ! -d "$dest/.git" ]]; then
    log "Cloning $repo"
    git clone --quiet "$repo" "$dest"
  else
    git -C "$dest" fetch --quiet origin
  fi
  git -C "$dest" -c advice.detachedHead=false checkout --quiet "$pin"
  log "$(basename "$dest") @ $(git -C "$dest" rev-parse --short HEAD)"
}

mkdir -p "$VENDOR/bin"
fetch_pinned "$OTD_REPO" "$OTD_PIN" "$VENDOR/otd-spec"
fetch_pinned "$OPENTAX_REPO" "$OPENTAX_PIN" "$VENDOR/opentax"

# opentax release binary for this platform (same asset names as upstream install.sh).
case "$(uname -s)" in Darwin) os=macos ;; Linux) os=linux ;; *) die "unsupported OS" ;; esac
case "$(uname -m)" in arm64|aarch64) arch=arm64 ;; x86_64|amd64) arch=x64 ;; *) die "unsupported arch" ;; esac
OPENTAX_BIN="$VENDOR/bin/opentax"
if [[ -x "$OPENTAX_BIN" ]] && "$OPENTAX_BIN" version 2>/dev/null | grep -q "${OPENTAX_TAG#v}"; then
  log "opentax $OPENTAX_TAG present"
else
  log "Downloading opentax $OPENTAX_TAG ($os-$arch)"
  curl -fsSL -o "$OPENTAX_BIN" \
    "$OPENTAX_REPO/releases/download/$OPENTAX_TAG/opentax-$os-$arch"
  chmod +x "$OPENTAX_BIN"
  [[ "$os" == macos ]] && xattr -d com.apple.quarantine "$OPENTAX_BIN" 2>/dev/null || true
fi
log "$("$OPENTAX_BIN" version)"

# Python venv via uv (fetches Python $PYTHON_VERSION if the system lacks it).
command -v uv >/dev/null || die "uv is required: curl -LsSf https://astral.sh/uv/install.sh | sh"
log "Syncing .venv (Python $PYTHON_VERSION) from pyproject.toml / uv.lock"
# BOOTSTRAP_UV_ARGS overrides the sync flags (the Dockerfile uses --frozen --no-dev).
(cd "$ROOT" && uv sync --quiet ${BOOTSTRAP_UV_ARGS:---python "$PYTHON_VERSION"})

log "Done. Next: scripts/smoke.sh"
