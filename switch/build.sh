#!/usr/bin/env bash
# Build the NFSU2 (Xbox) recompilation as a Switch homebrew NRO and stage an
# SD-card layout:
#
#   <SD>/switch/clx/clx.nro
#   <SD>/switch/clx/game/        the extracted disc: default.xbe, the disc tree, ...
#   <SD>/switch/clx/save/        created on first run
#   <SD>/switch/clx/clx_env.txt   optional KEY=VALUE runtime switches
#   <SD>/switch/clx/clx_log.txt   written when no nxlink host is listening
#
# The game reads the unpacked disc files directly -- never the ISO.
#
# Environment:
#   DEVKITPRO        default /opt/devkitpro (switch-dev, switch-sdl2, switch-mesa)
#   XBOXRECOMP_DIR   toolkit (default: the vendored xboxrecomp/)
#   NFSU2_GEN_DIR    lifted C from tools/regen.sh (default out/work/gen)
#   NFSU2_GAME_SRC   extracted disc to stage (default out/work/game)
#   STAGE_GAME=0     do not stage the disc (default 1): only the NRO and settings
#   SD_ROOT          staging SD root (default <repo>/switch_sd)
#   BUILD_DIR        default out/work/build-switch
#   JOBS             parallel compile jobs (default: nproc, capped by memory)
#   VULKAN=1         (default) the Vulkan renderer: stages clx-vulkan.nro, built in
#                    BUILD_DIR (default out/work/build-switch-vk) against
#                    NVK_SDK (mesa-switch NVK: lib/libvulkan.a + include, default
#                    out/work/nvk-sdk) and GLSLANG_DIR (glslang for the Switch,
#                    default out/work/glslang-switch). VULKAN=0: the GL clx.nro.
#   LTO=1            link-time optimisation of the lifted code (NFSU2_LTO):
#                    BUILD_DIR gets a -lto suffix and the NRO is staged as
#                    clx[-vulkan]-lto.nro next to the normal one, for A/B.
#                    LTO_JOBS parallel link jobs (default 4, ~2 GB each)
#   FFMPEG_DIR       VP6-only LGPL FFmpeg for the movies (tools/build_ffmpeg_vp6.sh
#                    switch; default out/work/ffmpeg-vp6-switch). Without
#                    it the lifted (slow) decoder plays them.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DEVKITPRO="${DEVKITPRO:-/opt/devkitpro}"
TK="${XBOXRECOMP_DIR:-$REPO/xboxrecomp}"
GEN="${NFSU2_GEN_DIR:-$REPO/out/work/gen}"
GAME="${NFSU2_GAME_SRC:-$REPO/out/work/game}"
SD="${SD_ROOT:-$REPO/switch_sd}"
VK="${VULKAN:-1}"
if [ "$VK" = "1" ]; then
    BUILD="${BUILD_DIR:-$REPO/out/work/build-switch-vk}"
    NRO_NAME=clx-vulkan.nro
    NVK_SDK="${NVK_SDK:-$REPO/out/work/nvk-sdk}"
    GLSLANG_DIR="${GLSLANG_DIR:-$REPO/out/work/glslang-switch}"
    VK_ARGS=(-DNFSU2_VULKAN=ON -DNVK_SDK="$NVK_SDK"
             -Dglslang_DIR="$GLSLANG_DIR/lib/cmake/glslang")
else
    BUILD="${BUILD_DIR:-$REPO/out/work/build-switch}"
    NRO_NAME=clx.nro
    VK_ARGS=(-DNFSU2_VULKAN=OFF)
fi

# NFSU2_SWITCH_VERSION_OVERRIDE: NRO version text instead of the git one (max 15 bytes).
VER_ARGS=()
[ -n "${NFSU2_SWITCH_VERSION_OVERRIDE:-}" ] && VER_ARGS=(-DNFSU2_SWITCH_VERSION_OVERRIDE="$NFSU2_SWITCH_VERSION_OVERRIDE")

LTO_ARGS=(-DNFSU2_LTO=OFF)
if [ "${LTO:-0}" = "1" ]; then
    [ -z "${BUILD_DIR:-}" ] && BUILD="$BUILD-lto"
    NRO_NAME="${NRO_NAME%.nro}-lto.nro"
    LTO_ARGS=(-DNFSU2_LTO=ON -DNFSU2_LTO_JOBS="${LTO_JOBS:-4}")
fi

FFMPEG_DIR="${FFMPEG_DIR-$REPO/out/work/ffmpeg-vp6-switch}"   # FFMPEG_DIR= : none, no warning
if [ -z "$FFMPEG_DIR" ]; then
    FF_ARGS=(-DNFSU2_FFMPEG_DIR=)
elif [ -f "$FFMPEG_DIR/lib/libavcodec.a" ]; then
    FF_ARGS=(-DNFSU2_FFMPEG_DIR="$FFMPEG_DIR")
else
    echo "warning: no FFmpeg in $FFMPEG_DIR -- movies use the lifted VP6 decoder" >&2
    FF_ARGS=(-DNFSU2_FFMPEG_DIR=)
fi

fail() { echo "error: $*" >&2; exit 1; }
[ -f "$DEVKITPRO/cmake/Switch.cmake" ] || fail "devkitPro not found at $DEVKITPRO"
[ -f "$DEVKITPRO/portlibs/switch/include/SDL2/SDL.h" ] || fail "switch-sdl2 missing"
[ -f "$GEN/recomp_funcs.h" ] || fail "no generated code in $GEN (run tools/regen.sh)"
STAGE_GAME="${STAGE_GAME:-1}"
[ "$STAGE_GAME" = "0" ] || [ -f "$GAME/default.xbe" ] || fail "no extracted disc in $GAME"
# The icon and the GL loader's logo come from the XBE's own title image; they
# are made here from the user's default.xbe (build_from_xbe.sh makes them first),
# never kept in git.
if [ ! -f "$REPO/src/logo.h" ] || [ ! -f "$REPO/assets/icon.jpg" ]; then
    [ -f "$GAME/default.xbe" ] || fail "no src/logo.h or assets/icon.jpg and no default.xbe in $GAME (tools/make_logo.py)"
    python3 "$REPO/tools/make_logo.py" "$GAME/default.xbe" || fail "tools/make_logo.py failed (needs Pillow)"
fi

if [ -z "${JOBS:-}" ]; then
    mem_mb=$(( $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) / 1024 ))
    JOBS=$(( mem_mb / 1500 )); [ "$JOBS" -lt 1 ] && JOBS=1
    [ "$JOBS" -gt "$(nproc)" ] && JOBS=$(nproc)
fi

cmake -S "$REPO" -B "$BUILD" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$DEVKITPRO/cmake/Switch.cmake" \
    -DCMAKE_BUILD_TYPE=Release \
    -DXBOXRECOMP_DIR="$TK" -DNFSU2_GEN_DIR="$GEN" \
    -DNFSU2_SWITCH_ICON="$REPO/assets/icon.jpg" "${VK_ARGS[@]}" "${FF_ARGS[@]}" \
    "${LTO_ARGS[@]}" "${VER_ARGS[@]}" >/dev/null
ninja -C "$BUILD" -j"$JOBS"

DEST="$SD/switch/clx"
mkdir -p "$DEST"
cp "$BUILD/clx_recomp.nro" "$DEST/$NRO_NAME"
# Default settings, only when the card has none (edits there are kept).
[ -f "$DEST/clx_env.txt" ] || cp "$REPO/switch/clx_env.txt" "$DEST/clx_env.txt"
echo
echo "staged $DEST"
echo "  $NRO_NAME $(stat -c %s "$DEST/$NRO_NAME") bytes"
if [ "$STAGE_GAME" != "0" ]; then
    # The disc image is 4.5 GB: copy only what changed.
    mkdir -p "$DEST/game"
    rsync -a --size-only "$GAME/" "$DEST/game/" --exclude '*_analysis.json' --exclude UDATA --exclude TDATA --exclude CACHE
    echo "  game/ $(du -sh "$DEST/game" | cut -f1)"
fi
echo "  copy <SD>/switch/clx/ to the card (or point Eden's sdmc at $SD),"
echo "  and start it from hbmenu with title takeover (hold R on a game) for full RAM."
