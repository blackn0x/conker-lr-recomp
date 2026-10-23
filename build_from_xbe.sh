#!/usr/bin/env bash
# Build Conker: Live & Reloaded from your own default.xbe: for the Nintendo
# Switch, for Linux, or for Windows.
#
#   ./build_from_xbe.sh /path/to/default.xbe
#
# 1. checks the XBE (retail NTSC, SHA-1 below; other versions are untested)
# 2. makes the homebrew icon and loading logo from the XBE's title image
# 3. lifts the XBE's x86 code to C (tools/regen.sh, ~15 min, ~15 GB RAM)
# 4. builds what VARIANTS asks for (default: the two Switch NROs)
#
# VARIANTS (a space separated list):
#   vulkan   Switch, clx-vulkan.nro (recommended). Needs devkitPro, NVK, glslang
#            (NVK and glslang are built once, ~1 h; the Docker image has them)
#   gl       Switch, clx.nro (OpenGL; also runs in the Eden emulator)
#   linux    Linux x86-64: out/linux/ (clx, clx.sh, clx_options.txt)
#   windows  Windows x64, in an MSYS2 UCRT64 shell: out/windows/
#            (see build_from_xbe.ps1 and the README)
#
# Output:
#   out/sdmc/switch/clx/   Switch: *.nro, clx_env.txt, clx_options.txt
#                          (copy to the root of the SD card; the disc goes to
#                          switch/clx/game/)
#   out/linux/             Linux package
#   out/windows/           Windows package
#   out/work/              lifted C, build dirs (re-used next time)
#
# What this builds contains code generated from your XBE: do not share it.
#
# Environment (all optional):
#   OUT        output dir (default <repo>/out); WORK (default $OUT/work)
#   VARIANTS   see above; default "vulkan gl"
#   REGEN=1    lift again even if out/work/gen matches this source tree
#   JOBS       parallel compile jobs (default: by free memory, ~1.5 GB each)
#   DEVKITPRO  default /opt/devkitpro (Switch)
#   NVK_SDK    prebuilt NVK (lib/libvulkan.a + include/); default $WORK/nvk-sdk
#   GLSLANG_DIR  glslang for the Switch; default $WORK/glslang-switch
set -euo pipefail

XBE_SHA1=2232a1b3874d67b4bb4cf53a940420d2dab59535
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${OUT:-$REPO/out}"
WORK="${WORK:-$OUT/work}"
VARIANTS="${VARIANTS:-vulkan gl}"
export DEVKITPRO="${DEVKITPRO:-/opt/devkitpro}"
NVK_SDK="${NVK_SDK:-$WORK/nvk-sdk}"
GLSLANG_DIR="${GLSLANG_DIR:-$WORK/glslang-switch}"

fail() { echo "error: $*" >&2; exit 1; }
step() { echo; echo "== $*"; }
has() { case " $VARIANTS " in *" $1 "*) return 0;; esac; return 1; }

[ $# -eq 1 ] || fail "usage: $0 /path/to/default.xbe"
[ -f "$1" ] || fail "no file $1"
for v in $VARIANTS; do case $v in vulkan|gl|linux|windows) ;; *) fail "unknown variant $v";; esac; done
sum=$(sha1sum "$1" | cut -d' ' -f1)
[ "$sum" = "$XBE_SHA1" ] || fail "$1 has SHA-1 $sum; this port needs the retail NTSC default.xbe ($XBE_SHA1)"

step "checking tools"
for t in python3 cmake ninja sha1sum; do command -v $t >/dev/null || fail "$t not found"; done
command -v git >/dev/null || echo "warning: git not found; the Switch version text will be 0.0.nogit" >&2
python3 -c "import capstone, PIL" 2>/dev/null || fail "python3 needs capstone and Pillow: pip install capstone==5.0.7 Pillow"
if has vulkan || has gl; then
    command -v rsync >/dev/null || fail "rsync not found"
    [ -f "$DEVKITPRO/cmake/Switch.cmake" ] || fail "devkitPro not found at $DEVKITPRO (README: Switch)"
    for lib in SDL2 EGL zstd expat z; do
        [ -f "$DEVKITPRO/portlibs/switch/lib/lib$lib.a" ] || fail "devkitPro library lib$lib.a missing (README: Switch)"
    done
fi
if has linux; then
    command -v gcc >/dev/null || fail "gcc not found (README: Linux)"
    pkg-config --exists sdl2 || fail "SDL2 development files not found (README: Linux)"
    pkg-config --exists openssl || fail "OpenSSL development files not found (README: Linux)"
    pkg-config --exists epoxy || fail "libepoxy development files not found (README: Linux)"
fi
if has windows; then
    [ "${MSYSTEM:-}" = "UCRT64" ] || fail "windows: run this in an MSYS2 UCRT64 shell (README: Windows)"
    command -v clang >/dev/null || fail "clang not found (pacman -S mingw-w64-ucrt-x86_64-clang)"
    pkg-config --exists sdl2 || fail "SDL2 not found (pacman -S mingw-w64-ucrt-x86_64-SDL2)"
fi

if [ -z "${JOBS:-}" ]; then
    # MSYS2's /proc/meminfo has no MemAvailable
    mem_kb=$(awk '/^MemAvailable:/ {print $2; f=1} END {if(!f) exit 1}' /proc/meminfo 2>/dev/null || awk '/^MemFree:/ {print $2}' /proc/meminfo)
    JOBS=$(( ${mem_kb:-0} / 1024 / 1500 )); [ "$JOBS" -lt 1 ] && JOBS=1
    [ "$JOBS" -gt "$(nproc)" ] && JOBS=$(nproc)
fi

mkdir -p "$WORK/xbe"
cmp -s "$1" "$WORK/xbe/default.xbe" || cp "$1" "$WORK/xbe/default.xbe"
XBE="$WORK/xbe/default.xbe"

step "icon and logo from the XBE"
python3 "$REPO/tools/make_logo.py" "$XBE"

# The lifted C depends on the toolkit, the seeds and the manual overrides.
stamp=$(cd "$REPO" && { sha1sum < "$XBE"; find xboxrecomp/tools config tools src/recomp_manual.c -type f \
        ! -path '*/output/*' ! -name '*.pyc' | LC_ALL=C sort | xargs sha1sum; } | sha1sum | cut -d' ' -f1)
if [ "${REGEN:-0}" = "1" ] || [ "$(cat "$WORK/gen/.stamp" 2>/dev/null)" != "$stamp" ]; then
    step "lifting the XBE to C (~15 min)"
    rm -rf "$WORK/gen"
    XBOXRECOMP_DIR="$REPO/xboxrecomp" CLX_XBE="$XBE" CLX_GEN_DIR="$WORK/gen" bash "$REPO/tools/regen.sh"
    echo "$stamp" > "$WORK/gen/.stamp"
else
    step "lifted C in $WORK/gen is current (REGEN=1 lifts again)"
fi

# ── Switch ──────────────────────────────────────────────────────
if has vulkan; then
    if [ ! -f "$NVK_SDK/lib/libvulkan.a" ]; then
        step "building NVK into $NVK_SDK (once, ~1 h)"
        NVK_SDK="$NVK_SDK" WORK="$WORK/deps" bash "$REPO/tools/build_nvk.sh"
    fi
    if [ ! -f "$GLSLANG_DIR/lib/cmake/glslang/glslang-config.cmake" ]; then
        step "building glslang into $GLSLANG_DIR"
        GLSLANG_DIR="$GLSLANG_DIR" WORK="$WORK/deps" bash "$REPO/tools/build_glslang_switch.sh"
    fi
fi
if has vulkan || has gl; then
    DEST="$OUT/sdmc/switch/clx"
    mkdir -p "$DEST"
    # Settings for playing: the dev copy's profiler, frame-cost lines and FPS digits off.
    [ -f "$DEST/clx_env.txt" ] || sed -e 's/^RECOMP_NX_PROFILE=1/RECOMP_NX_PROFILE=0/' \
        -e 's/^RECOMP_FRAME_STATS=1/RECOMP_FRAME_STATS=0/' -e 's/^RECOMP_FPS_OSD=1/RECOMP_FPS_OSD=0/' \
        "$REPO/switch/clx_env.txt" > "$DEST/clx_env.txt"
    [ -f "$DEST/clx_options.txt" ] || cp "$REPO/switch/clx_options.txt" "$DEST/clx_options.txt"
    for v in vulkan gl; do
        has $v || continue
        step "building the $v NRO (~40 min)"
        VULKAN=$([ $v = vulkan ] && echo 1 || echo 0) BUILD_DIR="$WORK/build-$v" NFSU2_GEN_DIR="$WORK/gen" \
            SD_ROOT="$OUT/sdmc" STAGE_GAME=0 XBOXRECOMP_DIR="$REPO/xboxrecomp" \
            NVK_SDK="$NVK_SDK" GLSLANG_DIR="$GLSLANG_DIR" FFMPEG_DIR= bash "$REPO/switch/build.sh"
    done
    step "Switch output: $DEST"
    ls -l "$DEST"
    echo "Copy it to sdmc:/switch/clx/ on your SD card and your unpacked disc to"
    echo "sdmc:/switch/clx/game/. Start it from hbmenu with title takeover (hold R on a game)."
fi

# ── Linux ───────────────────────────────────────────────────────
if has linux; then
    step "building the Linux binary (~10 min)"
    cmake -S "$REPO" -B "$WORK/build-linux" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DNFSU2_GEN_DIR="$WORK/gen" -DXBOXRECOMP_DIR="$REPO/xboxrecomp" >/dev/null
    ninja -C "$WORK/build-linux" -j"$JOBS"
    DEST="$OUT/linux"
    mkdir -p "$DEST"
    cp "$WORK/build-linux/clx_recomp" "$DEST/clx"
    strip "$DEST/clx" 2>/dev/null || true
    cp "$REPO/pc/clx.sh" "$DEST/clx.sh"; chmod +x "$DEST/clx.sh"
    [ -f "$DEST/clx_options.txt" ] || cp "$REPO/pc/clx_options.txt" "$DEST/clx_options.txt"
    step "Linux output: $DEST"
    ls -l "$DEST"
    echo "Run: $DEST/clx.sh /path/to/unpacked/disc"
fi

# ── Windows (MSYS2 UCRT64) ──────────────────────────────────────
if has windows; then
    step "building the Windows executable (clang, MinGW; ~5 min)"
    cmake -S "$REPO" -B "$WORK/build-windows" -G Ninja -DCMAKE_C_COMPILER=clang -DCMAKE_BUILD_TYPE=Release \
        -DNFSU2_GEN_DIR="$WORK/gen" -DXBOXRECOMP_DIR="$REPO/xboxrecomp" >/dev/null
    ninja -C "$WORK/build-windows" -j"$JOBS"
    DEST="$OUT/windows"
    mkdir -p "$DEST"
    cp "$WORK/build-windows/clx_recomp.exe" "$DEST/clx.exe"
    # the MSYS2 runtime DLLs clx.exe needs (SDL2, winpthreads, ...), not Windows' own
    ldd "$DEST/clx.exe" | awk '/\/ucrt64\// {print $3}' | while read -r dll; do cp -n "$dll" "$DEST/"; done
    cp "$REPO/pc/clx.ps1" "$REPO/pc/clx.bat" "$DEST/"
    [ -f "$DEST/clx_options.txt" ] || cp "$REPO/pc/clx_options.txt" "$DEST/clx_options.txt"
    step "Windows output: $DEST"
    ls -l "$DEST"
    echo "Run: $DEST/clx.bat C:\\path\\to\\unpacked\\disc"
fi
