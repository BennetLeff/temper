#!/usr/bin/env bash
# Durable, idempotent installer for the `kicad-cli` used by `make drc`,
# scripts/verify_regenerated_board.py, and the DRC ceiling protocol.
#
# WHY THIS EXISTS
# ---------------
# This machine has no distro KiCad 10.x package. kicad-cli has been installed
# by hand three times in one session and been reported "vanished" twice:
#
#   1. A real loss: the first install lived under /tmp/opencode/kicad-10.0.5.
#      /tmp is reaped. Anything installed there is temporary by construction.
#   2. A false alarm: the reinstall to ~/.local/opt/kicad-10.0.5 was probed at
#      <prefix>/bin/kicad-cli, which has never existed. Debs extract to
#      <prefix>/root/usr/bin/kicad-cli. The binary was present the whole time.
#
# The deeper problem behind both: nothing was ever placed on PATH, so
# `which kicad-cli` returned nothing and every repo tool that shells out to a
# bare `kicad-cli` failed identically to a genuinely missing install. This
# script fixes that permanently by installing a wrapper shim on PATH.
#
# WHY A SHIM AND NOT A SYMLINK
# ----------------------------
# kicad-cli cannot run from a relocated deb tree without two environment
# variables, and a bare symlink supplies neither:
#
#   LD_LIBRARY_PATH        every directory under <prefix>/root holding a .so
#   KICAD_STOCK_DATA_HOME  <prefix>/root/usr/share/kicad
#
# Without them the loader resolves the CLI's own closure but NOT
# _pcbnew.kiface and OpenCASCADE -- so `kicad-cli version` prints 10.0.5 and
# `kicad-cli pcb drc` fails. Probing with `version` is how this install has
# repeatedly been declared healthy while DRC was broken. This script
# validates with a real `pcb drc` run against a real board instead.
#
# USAGE
#   scripts/install_kicad_cli.sh            # install/repair, then validate
#   scripts/install_kicad_cli.sh --check    # validate only, no writes
#   KICAD_PREFIX=/somewhere scripts/install_kicad_cli.sh
#
# Exit 0 = kicad-cli is on PATH and can actually run DRC.

set -euo pipefail

KICAD_VERSION="${KICAD_VERSION:-10.0.5}"
KICAD_PREFIX="${KICAD_PREFIX:-$HOME/.local/opt/kicad-${KICAD_VERSION}}"
SHIM_DIR="${SHIM_DIR:-$HOME/.local/bin}"
SHIM="${SHIM_DIR}/kicad-cli"
ROOT="${KICAD_PREFIX}/root"
DL="${KICAD_PREFIX}/dl"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

say() { printf '%s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# The KiCad deb plus its non-default-installed runtime dependencies.
#
# The five marked (*) are the ones that defeat naming heuristics: the ABI
# suffixes (t64 = the 64-bit time_t transition, and the bare SONAME-style
# versions) mean the package name cannot be derived from the library name a
# failed `ldd` reports. They are listed explicitly so nobody has to
# rediscover them by hand a fourth time. libspnav0 additionally installs to
# /usr/lib, not /usr/lib/x86_64-linux-gnu, which is why LD_LIBRARY_PATH is
# computed by scanning for .so files rather than hardcoding a multiarch dir.
DEPS=(
  "libgit2-1.7"                      # (*)
  "libhttp-parser2.9"                # (*)
  "libmbedtls14t64"                  # (*)
  "libmbedx509-1t64"                 # (*)
  "libspnav0"                        # (*) -> /usr/lib
  "libnng1"
  "libocct-foundation-7.6t64"
  "libocct-modeling-algorithms-7.6t64"
  "libocct-modeling-data-7.6t64"
  "libocct-ocaf-7.6t64"
  "libocct-data-exchange-7.6t64"     # OpenCASCADE: needed by _pcbnew.kiface,
  "libocct-visualization-7.6t64"     # NOT by kicad-cli itself.
)

# ---------------------------------------------------------------------------
# ld path is derived, never hardcoded: scan the extracted tree for .so files.
# ---------------------------------------------------------------------------
kicad_ld_path() {
  find "$ROOT" -name '*.so*' -printf '%h\n' 2>/dev/null | sort -u | tr '\n' ':'
}

# ---------------------------------------------------------------------------
# Validation: a REAL DRC run. Not `kicad-cli version`.
# ---------------------------------------------------------------------------
validate() {
  local exe="$1" board tmp rc
  board="${REPO_ROOT}/pcb/temper.kicad_pcb"
  [ -f "$board" ] || { say "NOTE: ${board} absent; falling back to version probe only."; "$exe" version >/dev/null 2>&1; return $?; }

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  # Copy the project + DRU beside the board. kicad-cli resolves a project by
  # finding <stem>.kicad_pro next to the board and, when it cannot, silently
  # drops every custom-rule violation instead of erroring.
  cp "$board" "$tmp/" || return 1
  for ext in kicad_pro kicad_dru; do
    [ -f "${board%.kicad_pcb}.${ext}" ] && cp "${board%.kicad_pcb}.${ext}" "$tmp/"
  done

  rc=0
  ( cd "$tmp" && "$exe" pcb drc --all-track-errors --format json \
      -o drc.json temper.kicad_pcb >/dev/null 2>&1 ) || rc=$?
  # --exit-code-violations is deliberately NOT passed here: a board with
  # violations is still a working toolchain. We are testing the tool, not
  # the board. Success is "a report got written".
  [ -s "$tmp/drc.json" ] || return 1
  return 0
}

# ---------------------------------------------------------------------------
# --check mode
# ---------------------------------------------------------------------------
instructions() {
  cat >&2 <<EOF

  kicad-cli is missing or cannot run DRC.

  Install/repair it with:

      ${REPO_ROOT}/scripts/install_kicad_cli.sh

  This is NOT optional and must NOT be skipped. A DRC gate that silently
  passes when kicad-cli is absent reports "DRC not run" as a footnote when
  DRC was the entire measurement. See
  docs/evidence/2026-08-12-heatsink-board-drc.md.
EOF
}

if [ "$CHECK_ONLY" = 1 ]; then
  if ! command -v kicad-cli >/dev/null 2>&1; then
    say "FAIL: kicad-cli is not on PATH."
    instructions
    exit 1
  fi
  if ! validate "$(command -v kicad-cli)"; then
    say "FAIL: kicad-cli is on PATH but cannot run 'pcb drc'."
    say "      (This is the failure mode 'kicad-cli version' does not catch:"
    say "       DRC additionally needs _pcbnew.kiface and OpenCASCADE.)"
    instructions
    exit 1
  fi
  say "OK: kicad-cli $(kicad-cli version 2>/dev/null) on PATH, DRC functional."
  exit 0
fi

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
say "==> prefix: ${KICAD_PREFIX}"
mkdir -p "$DL" "$ROOT" "$SHIM_DIR"

if [ ! -x "${ROOT}/usr/bin/kicad-cli" ]; then
  say "==> kicad-cli not extracted; fetching + extracting"

  if [ ! -f "$DL"/kicad_"${KICAD_VERSION}"*_amd64.deb ]; then
    say "    downloading kicad ${KICAD_VERSION} (needs the KiCad PPA configured)"
    ( cd "$DL" && apt-get download "kicad=${KICAD_VERSION}*" 2>/dev/null \
        || apt-get download kicad ) \
      || die "could not download the kicad deb. Add the KiCad release PPA:
    sudo add-apt-repository ppa:kicad/kicad-dev-nightly && sudo apt update"
  fi

  for pkg in "${DEPS[@]}"; do
    if ! ls "$DL"/"${pkg}"_*.deb >/dev/null 2>&1; then
      say "    downloading ${pkg}"
      ( cd "$DL" && apt-get download "$pkg" ) \
        || die "could not download ${pkg}. If apt cannot resolve it, fetch the
    .deb from packages.ubuntu.com by hand into ${DL} and re-run."
    fi
  done

  for deb in "$DL"/*.deb; do
    say "    extracting $(basename "$deb")"
    dpkg-deb -x "$deb" "$ROOT"
  done
fi

[ -x "${ROOT}/usr/bin/kicad-cli" ] \
  || die "extraction finished but ${ROOT}/usr/bin/kicad-cli is missing."
[ -f "${ROOT}/usr/bin/_pcbnew.kiface" ] \
  || die "_pcbnew.kiface missing -- DRC would fail. The kicad deb did not extract fully."

# ---------------------------------------------------------------------------
# The shim. This is the durable part.
# ---------------------------------------------------------------------------
say "==> writing shim ${SHIM}"
cat > "$SHIM" <<EOF
#!/usr/bin/env bash
# Generated by scripts/install_kicad_cli.sh -- do not edit by hand.
#
# Supplies the two environment variables a relocated KiCad deb tree needs
# before exec'ing the real binary, so that a bare \`kicad-cli\` anywhere in
# this repo's tooling can run DRC (which needs _pcbnew.kiface + OpenCASCADE,
# beyond the CLI's own library closure).
KICAD_ROOT="${ROOT}"
export LD_LIBRARY_PATH="\$(find "\$KICAD_ROOT" -name '*.so*' -printf '%h\n' 2>/dev/null | sort -u | tr '\n' ':')\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export KICAD_STOCK_DATA_HOME="\$KICAD_ROOT/usr/share/kicad"
exec "\$KICAD_ROOT/usr/bin/kicad-cli" "\$@"
EOF
chmod +x "$SHIM"

case ":$PATH:" in
  *":${SHIM_DIR}:"*) ;;
  *) say "WARNING: ${SHIM_DIR} is not on PATH. Add it to your shell profile:"
     say "         export PATH=\"${SHIM_DIR}:\$PATH\"" ;;
esac

say "==> validating with a real 'pcb drc' run (not 'version')"
validate "$SHIM" || die "shim installed but DRC still fails. Check LD_LIBRARY_PATH resolution:
    ldd ${ROOT}/usr/bin/_pcbnew.kiface | grep 'not found'"

say "OK: kicad-cli $("$SHIM" version) installed at ${SHIM} -- DRC functional."
