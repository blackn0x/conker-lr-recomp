# Build environment for build_from_xbe.sh: devkitPro (devkitA64, libnx, the
# Switch portlibs), Python with capstone/Pillow for the lifter, and NVK +
# glslang for the Switch built from source at fixed versions.
#
#   docker build -t clx-build .                       # once, ~1 h (NVK)
#   docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
#       -v "$PWD:/src" -v /path/to/xbe-folder:/xbe:ro clx-build \
#       ./build_from_xbe.sh /xbe/default.xbe          # NROs in out/sdmc/
#
# No game data goes into the image; the XBE is mounted at run time.

# devkitpro/devkita64 (Debian 12, devkitA64 r29.2, libnx 4.12.0), pinned.
FROM devkitpro/devkita64@sha256:1fc388c3a0d34bd2045a6dadcb1020e069d5f876a187fd705de14b4440c00282

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-pip flex bison pkg-config cmake ninja-build git curl rsync ca-certificates \
        build-essential clang libclang-dev \
        llvm-15-dev libllvmspirvlib-15-dev libclc-15-dev libclang-15-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir \
        capstone==5.0.7 Pillow==10.2.0 meson==1.12.1 mako==1.4.3 pyyaml packaging

# The Switch libraries the NROs link (all in the base image; fail early if not).
RUN dkp-pacman -Q switch-sdl2 switch-mesa switch-libdrm_nouveau switch-glad \
        switch-libzstd switch-libexpat switch-zlib

# SPIRV-Tools >= 2024.1 for Mesa's mesa_clc.
RUN git clone -q --depth 1 -b vulkan-sdk-1.3.290.0 https://github.com/KhronosGroup/SPIRV-Tools /tmp/spt \
    && git clone -q --depth 1 -b vulkan-sdk-1.3.290.0 https://github.com/KhronosGroup/SPIRV-Headers /tmp/spt/external/spirv-headers \
    && cmake -S /tmp/spt -B /tmp/spt/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DSPIRV_SKIP_TESTS=ON \
        -DSPIRV_WERROR=OFF -DCMAKE_INSTALL_PREFIX=/usr/local \
    && ninja -C /tmp/spt/build install && rm -rf /tmp/spt

# Rust (NVK's compiler NAK is Rust), the nightly the tested NROs were built with.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal \
        --default-toolchain nightly-2026-10-16 \
    && . /root/.cargo/env \
    && rustup component add rust-src rustfmt \
    && rustup target add aarch64-unknown-linux-gnu \
    && cargo install --locked bindgen-cli@0.73.2 cbindgen@0.29.4
ENV PATH="/root/.cargo/bin:${PATH}"

COPY tools/build_nvk.sh tools/build_glslang_switch.sh /opt/clx-tools/
RUN NVK_SDK=/opt/nvk-sdk WORK=/tmp/deps bash /opt/clx-tools/build_nvk.sh \
    && GLSLANG_DIR=/opt/glslang-switch WORK=/tmp/deps bash /opt/clx-tools/build_glslang_switch.sh \
    && rm -rf /tmp/deps

ENV NVK_SDK=/opt/nvk-sdk GLSLANG_DIR=/opt/glslang-switch DEVKITPRO=/opt/devkitpro
WORKDIR /src
