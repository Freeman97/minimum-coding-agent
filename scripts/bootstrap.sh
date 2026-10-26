#!/usr/bin/env bash
#
# Install the project-local toolchain: uv, a Python interpreter and the locked
# dependencies. Everything stays inside the repository so the development
# sandbox never needs to write outside the workspace.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

UV_VERSION="${UV_VERSION:-0.13.1}"
PYTHON_REQUEST="${MCA_PYTHON:-3.12}"
TOOLS_DIR="$ROOT/.tools"
UV_BIN="$TOOLS_DIR/uv"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uv-cache}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$ROOT/.uv-python}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$ROOT/.venv}"

log() {
  printf '[bootstrap] %s\n' "$*" >&2
}

warn() {
  printf '[bootstrap] warning: %s\n' "$*" >&2
}

install_uv() {
  if [[ -x "$UV_BIN" ]]; then
    log "Using existing uv at $UV_BIN"
    return
  fi
  mkdir -p "$TOOLS_DIR" "$TOOLS_DIR/config"
  local installer="$TOOLS_DIR/uv-installer.sh"
  log "Downloading uv $UV_VERSION"
  if command -v curl >/dev/null 2>&1 \
      && curl --proto '=https' --tlsv1.2 -LsSf \
          --connect-timeout 10 --max-time 180 \
          "https://astral.sh/uv/$UV_VERSION/install.sh" -o "$installer"; then
    # Keep the installer receipt inside the project: writing to ~/.config is
    # not possible when the workspace sandbox is active.
    XDG_CONFIG_HOME="$TOOLS_DIR/config" \
      UV_INSTALL_DIR="$TOOLS_DIR" \
      UV_NO_MODIFY_PATH=1 \
      sh "$installer" >/dev/null 2>&1 || true
    rm -f "$installer"
    if [[ -x "$UV_BIN" ]]; then
      log "Installed uv $UV_VERSION"
      return
    fi
  else
    rm -f "$installer"
  fi
  warn "could not download uv $UV_VERSION from astral.sh"
  if command -v uv >/dev/null 2>&1; then
    cp "$(command -v uv)" "$UV_BIN"
    chmod +x "$UV_BIN"
    warn "falling back to the system uv: $("$UV_BIN" --version)"
    return
  fi
  warn "uv is not installed and could not be downloaded"
  warn "install uv >= $UV_VERSION and rerun 'make setup'"
  exit 1
}

find_python() {
  "$UV_BIN" python find --no-python-downloads "$1" 2>/dev/null
}

choose_python() {
  local request candidate
  if candidate="$(find_python "$PYTHON_REQUEST")"; then
    printf '%s\n' "$candidate"
    return
  fi
  log "Installing CPython $PYTHON_REQUEST"
  if timeout 180 "$UV_BIN" python install --no-bin "$PYTHON_REQUEST" >/dev/null 2>&1 \
      && candidate="$(find_python "$PYTHON_REQUEST")"; then
    printf '%s\n' "$candidate"
    return
  fi
  warn "could not install CPython $PYTHON_REQUEST; falling back to an available interpreter"
  for request in 3.12 3.11 3.10 3; do
    if candidate="$(find_python "$request")"; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  warn "no Python interpreter >= 3.10 found"
  exit 1
}

create_venv() {
  local python_request="$1"
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    log "Reusing existing virtual environment at $ROOT/.venv"
    return
  fi
  log "Creating virtual environment with $python_request"
  "$UV_BIN" venv --python "$python_request" "$ROOT/.venv"
}

sync_dependencies() {
  "$UV_BIN" sync
}

install_uv

PYTHON_CANDIDATE="$(choose_python)"
log "Selected Python interpreter: $PYTHON_CANDIDATE"

create_venv "$PYTHON_CANDIDATE"

attempt=0
until sync_dependencies; do
  attempt=$((attempt + 1))
  if (( attempt >= 3 )); then
    warn "dependency installation failed after $attempt attempts"
    exit 1
  fi
  warn "dependency installation failed; retrying ($attempt/3)"
  sleep 5
done

log "Verifying the package import"
"$UV_BIN" run python -c "import minimum_coding_agent"

log "Environment ready: $("$UV_BIN" run python -V)"
log "Run 'make check' to execute the quality gate."
