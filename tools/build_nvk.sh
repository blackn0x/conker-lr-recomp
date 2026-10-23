#!/usr/bin/env bash
# Build Mesa's NVK Vulkan driver for the Switch as a static library, from
# danfromtico/mesa-switch at a fixed commit, and install it as an SDK:
#
#   tools/build_nvk.sh [mesa-switch checkout]      (default $WORK/mesa-switch)
#
#   $NVK_SDK/lib/libvulkan.a     the driver (no loader; linked into the NRO)
#   $NVK_SDK/include/            mesa-switch's include tree (vulkan/*.h)
#
# Environment: DEVKITPRO (default /opt/devkitpro), NVK_SDK (default
# /opt/nvk-sdk), WORK (default /tmp/clx-deps).
#
# Needs (the Dockerfile installs all of it; on Ubuntu 24.04 / WSL2 once):
#   apt install python3-pip flex bison pkg-config libclang-dev llvm-15-dev \
#       libllvmspirvlib-15-dev libclc-15-dev libclang-15-dev
#   pip3 install --break-system-packages meson==1.12.1 mako pyyaml packaging
#   rustup (https://rustup.rs); this script installs the pinned nightly itself
#   cargo install bindgen-cli@0.73.2 cbindgen@0.29.4
#   SPIRV-Tools vulkan-sdk-1.3.290.0 in /usr/local
# Like mesa-switch's own build-switch.sh, it writes rustc/bindgen wrappers to
# /usr/local/libexec and the nouveau headers plus empty libdl/librt/libutil
# archives to $DEVKITPRO/portlibs/switch. Run it in the Docker image if you do
# not want that on your machine.
set -euo pipefail

MESA_COMMIT=0ff52079ca9e9e837ed27eb95a8d239f439a1864
RUST_NIGHTLY=nightly-2026-10-16          # the toolchain the tested NROs used
: "${DEVKITPRO:=/opt/devkitpro}"
: "${NVK_SDK:=/opt/nvk-sdk}"
: "${WORK:=/tmp/clx-deps}"
SRC="${1:-$WORK/mesa-switch}"
export DEVKITPRO

if [ ! -d "$SRC/.git" ]; then
    git init -q "$SRC"
    git -C "$SRC" remote add origin https://github.com/danfromtico/mesa-switch
fi
git -C "$SRC" fetch -q --depth 1 origin "$MESA_COMMIT"
git -C "$SRC" checkout -q --force "$MESA_COMMIT"
cd "$SRC"

# shellcheck disable=SC1091
. "$HOME/.cargo/env"
rustup toolchain install "$RUST_NIGHTLY" --profile minimal \
    --component rust-src,rustfmt --target aarch64-unknown-linux-gnu
export RUSTUP_TOOLCHAIN="$RUST_NIGHTLY"

mkdir -p /usr/local/libexec
cp bindgen-switch-wrapper.sh /usr/local/libexec/bindgen
cp rustc-switch-wrapper.sh /usr/local/libexec/rustc
cp bindgen-atomic-shim.h /usr/local/libexec/bindgen-atomic-shim.h
chmod +x /usr/local/libexec/bindgen /usr/local/libexec/rustc
cp src/gallium/winsys/nouveau/drm/nouveau.h "$DEVKITPRO/portlibs/switch/include/"
cp src/nouveau/headers/nv_device_info.h "$DEVKITPRO/portlibs/switch/include/"
# mesa_clc looks for Clang's headers under the major version (Debian: 15.0.6,
# Ubuntu: 15.0.7).
if [ ! -d /usr/lib/llvm-15/lib/clang/15/include ]; then
    full=$(ls -d /usr/lib/llvm-15/lib/clang/15.* | head -1)
    mkdir -p /usr/lib/llvm-15/lib/clang/15     # Debian already has this dir, without include/
    ln -s "$full/include" /usr/lib/llvm-15/lib/clang/15/include
fi
# Rust's std asks for -ldl -lrt -lutil: empty archives (mesa-switch provides the symbols).
if [ ! -f "$DEVKITPRO/portlibs/switch/lib/libdl.a" ]; then
    tmp=$(mktemp -d)
    echo "void __mesa_switch_stub_lib(void) {}" > "$tmp/stub.c"
    "$DEVKITPRO/devkitA64/bin/aarch64-none-elf-gcc" -c "$tmp/stub.c" -o "$tmp/stub.o"
    for L in dl rt util; do
        "$DEVKITPRO/devkitA64/bin/aarch64-none-elf-ar" rcs "$DEVKITPRO/portlibs/switch/lib/lib$L.a" "$tmp/stub.o"
    done
fi

# Host tools (mesa_clc, vtn_bindgen2), with LLVM 15 (meson would pick a newer llvm-config).
printf "[binaries]\nllvm-config = '/usr/lib/llvm-15/bin/llvm-config'\n" > native-llvm15.ini
PATH="/usr/lib/llvm-15/bin:$PATH" meson setup builddir-native --wipe --native-file native-llvm15.ini \
    -Dvulkan-drivers= -Dgallium-drivers= -Dshader-cache=true -Dplatforms= -Dglx=disabled -Degl=disabled \
    -Dopengl=false -Dgles1=disabled -Dgles2=disabled -Dtools=[] -Dllvm=enabled -Dmesa-clc=enabled \
    -Dprecomp-compiler=enabled -Dinstall-mesa-clc=true
ninja -C builddir-native src/compiler/clc/mesa_clc src/compiler/spirv/vtn_bindgen2

# The Switch build. Rust code for the console is built for aarch64-unknown-linux-gnu (the wrapper
# adds the target); proc-macros, which run here, use the plain rustc (native file).
export PATH="/usr/local/libexec:$PWD/builddir-native/src/compiler/clc:$PWD/builddir-native/src/compiler/spirv:$PATH"
export MESA_SWITCH_RUST_TARGET=aarch64-unknown-linux-gnu
printf "[binaries]\nrust = '%s'\ncbindgen = '%s'\n" "$HOME/.cargo/bin/rustc" "$HOME/.cargo/bin/cbindgen" > native-cross-tools.ini
meson setup builddir-switch --wipe --cross-file switch_cross_file.txt --native-file native-cross-tools.ini \
    --buildtype=release -Doptimization=1 -Db_lto=false -Db_ndebug=true -Dvulkan-drivers=nouveau \
    -Dgallium-drivers=nouveau -Dshader-cache=true -Dgallium-rusticl=false -Dplatforms=switch -Dglx=disabled \
    -Degl=disabled -Dopengl=false -Dgles1=disabled -Dgles2=disabled -Dllvm=disabled -Dshared-glapi=disabled \
    -Dshared-llvm=disabled -Dmesa-clc=system -Dprecomp-compiler=system -Dcpp_rtti=false
ninja -C builddir-switch src/nouveau/vulkan/libvulkan.a

mkdir -p "$NVK_SDK/lib"
cp builddir-switch/src/nouveau/vulkan/libvulkan.a "$NVK_SDK/lib/"
# With some binutils (devkitA64 r29.2) the archive's symbol index misses the Rust
# members' symbols and the final NRO link fails (undefined core::result::unwrap_failed).
"$DEVKITPRO/devkitA64/bin/aarch64-none-elf-ranlib" "$NVK_SDK/lib/libvulkan.a"
rm -rf "$NVK_SDK/include"
cp -r include "$NVK_SDK/include"
echo "NVK: $NVK_SDK/lib/libvulkan.a (mesa-switch $MESA_COMMIT)"
