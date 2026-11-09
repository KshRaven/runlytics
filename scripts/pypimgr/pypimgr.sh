#!/usr/bin/env bash
# ======================================================================
#  pypimgr.sh  -  runlytics PyPI Build & Upload Manager (Linux/macOS)
#  Requirements: bash 4.3+, python 3.11+, tar.   Usage: bash pypimgr.sh
#  Builds from a CLEAN STAGING COPY (no tests/scripts/.git/keys/caches),
#  inspects every artifact (verify_dist.py) before upload, and keeps the
#  PyPI token in memory only. runlytics' web UI is static (runlytics/web),
#  so there is no frontend build step.
# ======================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
VERSION_FILE="$PROJECT_DIR/runlytics/_version.py"
CACHE_DIR="$SCRIPT_DIR/pypimgr_cache"; VENV_DIR="$CACHE_DIR/venv"; ART_DIR="$CACHE_DIR/artifacts"
STAGE_DIR=""; TESTPYPI_URL="https://test.pypi.org/legacy/"

if [[ -t 1 ]]; then RED=$'\033[0;31m' GRN=$'\033[0;32m' YLW=$'\033[0;33m' BLU=$'\033[0;34m' CYN=$'\033[0;36m' BOLD=$'\033[1m' DIM=$'\033[2m' RST=$'\033[0m'
else RED='' GRN='' YLW='' BLU='' CYN='' BOLD='' DIM='' RST=''; fi
TW=$(tput cols 2>/dev/null || echo 72); (( TW < 64 )) && TW=64; (( TW > 104 )) && TW=104
hr()   { printf "${DIM}"; printf '%*s' "$TW" '' | tr ' ' '-'; printf "${RST}\n"; }
ok()   { printf "  ${GRN}[OK]${RST}  %s\n" "$*"; }
warn() { printf "  ${YLW}[!!]${RST}  %s\n" "$*"; }
err()  { printf "  ${RED}[XX]${RST}  %s\n" "$*"; }
info() { printf "  ${BLU} * ${RST}  %s\n" "$*"; }
anykey() { echo; printf "  ${DIM}Press any key to continue...${RST}"; read -r -s -n1; echo; }
confirm() { printf "  ${YLW}?${RST}  %s [y/N] " "${1:-Are you sure?}"; local r; read -r r; [[ "${r,,}" =~ ^(y|yes)$ ]]; }
banner() { echo; hr; printf "${CYN}${BOLD}  %s${RST}\n" "$1"; hr; }
cleanup() { [[ -n "$STAGE_DIR" && -d "$STAGE_DIR" ]] && rm -rf "$STAGE_DIR"; tput cnorm 2>/dev/null; stty echo 2>/dev/null; }
trap cleanup EXIT
trap 'echo; echo "  Interrupted."; exit 130' INT TERM

find_python() {
    local c
    for c in "${PYTHON:-}" python3.13 python3.12 python3.11 python3 python; do
        [[ -n "$c" ]] || continue; command -v "$c" &>/dev/null || continue
        "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null && { echo "$c"; return 0; }
    done; return 1
}
get_version() { sed -nE 's/^[[:space:]]*__version__[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' "$VERSION_FILE" | head -1; }

ensure_venv() {
    local py; py=$(find_python) || { err "Python 3.11+ not found (set PYTHON=/path/to/python)"; return 1; }
    mkdir -p "$CACHE_DIR" "$ART_DIR"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        info "Creating isolated build environment..."; "$py" -m venv "$VENV_DIR" || { err "venv creation failed"; return 1; }
    fi
    if ! "$VENV_DIR/bin/python" -c 'import build, twine' 2>/dev/null; then
        info "Installing build + twine..."
        "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip build twine setuptools wheel || { err "pip install failed"; return 1; }
    fi
}
artifacts() { ls "$ART_DIR"/*.whl "$ART_DIR"/*.tar.gz 2>/dev/null; }

check_project() {
    [[ -f "$VERSION_FILE" ]] || { err "runlytics/_version.py not found in $PROJECT_DIR"; return 1; }
    ok "Project:  $PROJECT_DIR"; ok "Version:  $(get_version)"
    local missing=0 f
    for f in README.md LICENSE MANIFEST.in pyproject.toml; do
        [[ -f "$PROJECT_DIR/$f" ]] && ok "$f present" || { err "$f missing"; missing=1; }
    done
    [[ -f "$PROJECT_DIR/runlytics/web/index.html" ]] && ok "Web UI present" || { err "runlytics/web/index.html missing"; missing=1; }
    if [[ -d "$PROJECT_DIR/.git" ]] && command -v git &>/dev/null; then
        [[ -z "$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null)" ]] && ok "Git tree clean" || warn "Uncommitted changes in git tree"
    fi
    return $missing
}

make_stage() {
    STAGE_DIR="$(mktemp -d)"; info "Staging clean copy of project..."
    tar -C "$PROJECT_DIR" -cf - \
        --exclude='./.git' --exclude='./.github' --exclude='./build' --exclude='./dist' --exclude='./scripts' \
        --exclude='./tests' --exclude='./test' --exclude='./examples' --exclude='*.egg-info' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='node_modules' --exclude='.env' --exclude='.env.*' \
        --exclude='*.pem' --exclude='*.key' --exclude='.pypirc' --exclude='*.map' --exclude='*.pkl' --exclude='*.pt' \
        --exclude='*.pth' --exclude='*.log' --exclude='./runs' --exclude='./demo_runs' --exclude='.venv' \
        --exclude='.idea' --exclude='.vscode' --exclude='.DS_Store' --exclude='TODO.md' --exclude='*.zip' \
        . | tar -C "$STAGE_DIR" -xf - || { err "Staging failed"; return 1; }
    ok "Staged at $STAGE_DIR"
}

build_package() {
    ensure_venv || return 1; make_stage || return 1
    info "Building sdist + wheel..."
    ( cd "$STAGE_DIR" || exit 1; "$VENV_DIR/bin/python" -m build --outdir "$STAGE_DIR/_out" ) || { err "Build failed"; return 1; }
    rm -f "$ART_DIR"/*.whl "$ART_DIR"/*.tar.gz
    cp "$STAGE_DIR"/_out/* "$ART_DIR"/ && ok "Artifacts in $ART_DIR"
    ls -1 "$ART_DIR" | grep -E '\.(whl|tar\.gz)$' | sed 's/^/        /'
    verify_package
}

verify_package() {
    local files; files=$(artifacts); [[ -n "$files" ]] || { err "No artifacts - build first"; return 1; }
    ensure_venv || return 1; info "Inspecting artifacts for forbidden files / secrets..."
    # shellcheck disable=SC2086
    "$VENV_DIR/bin/python" "$SCRIPT_DIR/verify_dist.py" $files || { err "Verification FAILED - do not upload"; return 1; }
    "$VENV_DIR/bin/python" -m twine check $files || { err "twine check failed"; return 1; }
    ok "Artifacts passed verification"
}

list_contents() {
    local files; files=$(artifacts); [[ -n "$files" ]] || { err "No artifacts - build first"; return 1; }
    local f
    for f in $files; do
        echo; info "$(basename "$f")"
        case "$f" in *.whl) "$VENV_DIR/bin/python" -m zipfile -l "$f" ;; *) tar -tzf "$f" ;; esac | head -n 400
    done
}

upload_package() {
    local target="$1" label url=()
    if [[ $target == test ]]; then label="TestPyPI"; url=(--repository-url "$TESTPYPI_URL"); else label="PyPI (PRODUCTION)"; fi
    verify_package || return 1
    local ver; ver=$(get_version)
    warn "About to upload runlytics $ver to $label. Published versions cannot be replaced."
    local typed; printf "  Type the version (%s) to confirm: " "$ver"; read -r typed
    [[ "$typed" == "$ver" ]] || { info "Cancelled."; return 0; }
    local token="${PYPI_TOKEN:-}"
    if [[ -z "$token" ]]; then printf "  API token (hidden, not stored): "; read -r -s token; echo; fi
    [[ "$token" == pypi-* ]] || { err "Token must start with 'pypi-'"; return 1; }
    TWINE_USERNAME=__token__ TWINE_PASSWORD="$token" \
        "$VENV_DIR/bin/python" -m twine upload --non-interactive "${url[@]}" $(artifacts) \
        && ok "Uploaded to $label" || err "Upload failed"
    token=""
}

bump_version() {
    info "Current version: $(get_version)"
    local new; printf "  New version (blank = cancel): "; read -r new; [[ -z "$new" ]] && return 0
    [[ "$new" =~ ^[0-9]+(\.[0-9]+)*([abrc]+[0-9]+|\.post[0-9]+|\.dev[0-9]+)?$ ]] || { err "Invalid version format"; return 1; }
    sed -i.bak -E "s/^([[:space:]]*__version__[[:space:]]*=[[:space:]]*\")[^\"]+(\")/\1$new\2/" "$VERSION_FILE" && rm -f "$VERSION_FILE.bak"
    ok "_version.py -> $(get_version)"
}

clean_all() {
    confirm "Delete artifacts, build venv, build/ and *.egg-info?" || return 0
    rm -rf "$CACHE_DIR/venv" "$ART_DIR" "$PROJECT_DIR/build" "$PROJECT_DIR/dist" "$PROJECT_DIR"/*.egg-info; ok "Cleaned"
}

full_release() { check_project || return 1; build_package || return 1; ok "Ready. Use the upload options to publish."; }

main_menu() {
    while true; do
        clear 2>/dev/null; banner "runlytics PyPI Manager  -  v$(get_version)"
        cat <<MENU
   1) Check project            5) Upload to TestPyPI
   2) Build package (staged)   6) Upload to PyPI
   3) Verify artifacts         7) Bump version
   4) List artifact contents   8) Clean
                               F) Full prepare (1+2)
                               Q) Quit
MENU
        hr; printf "  Select: "; local c; read -r c; echo
        case "${c,,}" in
            1) check_project ;; 2) build_package ;; 3) verify_package ;; 4) list_contents ;;
            5) upload_package test ;; 6) upload_package prod ;; 7) bump_version ;; 8) clean_all ;;
            f) full_release ;; q) exit 0 ;; *) warn "Unknown option" ;;
        esac
        anykey
    done
}
[[ -f "$VERSION_FILE" ]] || { err "runlytics/_version.py not found in $PROJECT_DIR (set PROJECT_DIR)"; exit 1; }
main_menu
