#!/usr/bin/env bash
# Run Conker: Live & Reloaded (Xbox recompilation) on Linux.
#
#   ./clx.sh [path/to/unpacked/disc]
#
# The disc folder is the one with default.xbe. Give it here, or as game=... in
# clx_options.txt (next to this script), or in NFSU2_GAME_DIR.
# The game writes its saves, its cache and its logs into that folder: use a
# folder you may write to.
#
# The game reads clx_options.txt itself (aspect, fps, camera, volume, render
# scale, key bindings, ...; see docs/settings-and-controls.md). This script reads
# only the keys the game does not: game, skip_intro, start_single. A variable
# you set yourself wins over the file.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPT="${CLX_OPTIONS:-$HERE/clx_options.txt}"
GAME="${1:-${NFSU2_GAME_DIR:-}}"
CR=$'\r'

# Defaults for playing on a PC
export CLX_START_SINGLE="${CLX_START_SINGLE:-1}"       # title cursor on Game 1
export RECOMP_CACHE_DIR="${RECOMP_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/clx/}"
export RECOMP_QUIET="${RECOMP_QUIET:-1}"
export CLX_OPTIONS="$OPT"

setdef() { [ -z "${!1:-}" ] && export "$1=$2"; return 0; }

if [ -f "$OPT" ]; then
    while IFS='=' read -r k v; do
        k="${k//$CR/}"; v="${v//$CR/}"      # a file saved with Windows line ends
        k="${k//[[:space:]]/}"; v="${v%%#*}"; v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"
        case "$k" in
            game)         [ -z "$GAME" ] && GAME="$v" ;;
            skip_intro)   [ "$v" = "1" ] && setdef CLX_SKIP_INTRO 1 ;;
            start_single) setdef CLX_START_SINGLE "$v" ;;
        esac
    done < "$OPT"
fi

if [ -z "$GAME" ] || [ ! -f "$GAME/default.xbe" ]; then
    echo "usage: $0 /path/to/unpacked/disc   (the folder with default.xbe)" >&2
    echo "or put game=/path/to/disc in $OPT" >&2
    exit 1
fi
mkdir -p "$RECOMP_CACHE_DIR"
export NFSU2_GAME_DIR="$GAME"
cd "$HERE"
exec "$HERE/clx" "$@"
