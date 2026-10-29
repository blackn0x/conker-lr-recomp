#!/usr/bin/env bash
# Cross-builds what the Android port links, for arm64-v8a:
#   SDL2     window, Vulkan surface, audio, game controllers (libSDL2.so + its Java side)
#   glslang  the Vulkan renderer compiles its shaders at run time (static, no optimizer)
#
#   android/build_deps.sh
#
# Environment:
#   ANDROID_NDK_HOME  NDK r27 (default $ANDROID_HOME/ndk/27.2.12479018)
#   DEPS              where sources and installs go (default out/work/deps)
#   ANDROID_API       minimum API level (default 30, Android 11)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$ANDROID_HOME/ndk/27.2.12479018}"
DEPS="${DEPS:-$REPO/out/work/deps}"
ANDROID_API="${ANDROID_API:-30}"
SDL_VER=2.30.9
GLSLANG_VER=14.3.0
JOBS="${JOBS:-$(nproc)}"

[ -f "$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" ] || {
    echo "error: no NDK at $ANDROID_NDK_HOME (see android/README.md)" >&2; exit 1; }

NDK_CMAKE=(-G Ninja -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake"
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM="android-$ANDROID_API" -DANDROID_STL=c++_static)

fetch() {   # fetch <dir> <url>: unpack a source tarball into its own directory once
    [ -d "$1" ] && return 0
    mkdir -p "$1.tmp"
    curl -fsSL "$2" | tar xz -C "$1.tmp"
    mv "$1.tmp" "$1"
}

fetch "$DEPS/sdl2" "https://github.com/libsdl-org/SDL/releases/download/release-$SDL_VER/SDL2-$SDL_VER.tar.gz"
fetch "$DEPS/glslang" "https://github.com/KhronosGroup/glslang/archive/refs/tags/$GLSLANG_VER.tar.gz"

if [ ! -f "$DEPS/sdl2-android/lib/libSDL2.so" ]; then
    echo "== SDL2 $SDL_VER"
    cmake -S "$DEPS/sdl2/SDL2-$SDL_VER" -B "$DEPS/build-sdl2" "${NDK_CMAKE[@]}" \
        -DCMAKE_INSTALL_PREFIX="$DEPS/sdl2-android" \
        -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST=OFF \
        -DCMAKE_SHARED_LINKER_FLAGS="-Wl,-z,max-page-size=16384" >/dev/null
    ninja -C "$DEPS/build-sdl2" -j"$JOBS" install >/dev/null
fi

if [ ! -f "$DEPS/glslang-android/lib/libglslang.a" ]; then
    echo "== glslang $GLSLANG_VER"
    cmake -S "$DEPS/glslang/glslang-$GLSLANG_VER" -B "$DEPS/build-glslang" "${NDK_CMAKE[@]}" \
        -DCMAKE_INSTALL_PREFIX="$DEPS/glslang-android" \
        -DENABLE_OPT=OFF -DGLSLANG_TESTS=OFF -DENABLE_GLSLANG_BINARIES=OFF \
        -DENABLE_SPVREMAPPER=OFF -DBUILD_SHARED_LIBS=OFF -DENABLE_HLSL=OFF >/dev/null
    ninja -C "$DEPS/build-glslang" -j"$JOBS" install >/dev/null
fi

echo "SDL2:    $DEPS/sdl2-android"
echo "glslang: $DEPS/glslang-android"
