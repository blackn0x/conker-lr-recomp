#!/usr/bin/env bash
# Build glslang 15.4.0 as static Switch libraries (the Vulkan renderer compiles
# its shaders on the console) and install them into $GLSLANG_DIR:
#
#   tools/build_glslang_switch.sh
#
# Environment: DEVKITPRO (default /opt/devkitpro), GLSLANG_DIR (default
# /opt/glslang-switch), WORK (default /tmp/clx-deps).
set -euo pipefail

TAG=15.4.0
: "${DEVKITPRO:=/opt/devkitpro}"
: "${GLSLANG_DIR:=/opt/glslang-switch}"
: "${WORK:=/tmp/clx-deps}"
export DEVKITPRO
SRC="$WORK/glslang-src"

[ -d "$SRC/.git" ] || git clone -q --depth 1 -b "$TAG" https://github.com/KhronosGroup/glslang "$SRC"
cmake -S "$SRC" -B "$WORK/glslang-build" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$DEVKITPRO/cmake/Switch.cmake" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$GLSLANG_DIR" -DBUILD_SHARED_LIBS=OFF -DENABLE_OPT=OFF \
    -DGLSLANG_TESTS=OFF -DENABLE_GLSLANG_BINARIES=OFF -DENABLE_HLSL=OFF >/dev/null
ninja -C "$WORK/glslang-build" install >/dev/null
echo "glslang $TAG: $GLSLANG_DIR"
