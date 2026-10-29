#!/usr/bin/env bash
# Build the Android APK (arm64-v8a) from the lifted C.
#
#   NFSU2_GEN_DIR=out/work/gen android/build.sh
#
# build_from_xbe.sh runs this for VARIANTS=android after lifting the XBE.
# No Gradle: the SDK's own tools (javac, d8, aapt2, zipalign, apksigner).
#
# Environment:
#   NFSU2_GEN_DIR     lifted C (default out/work/gen)
#   ANDROID_HOME      SDK with platforms;android-34, build-tools;34.0.0 and
#                     ndk;27.2.12479018 (default ~/Android/Sdk)
#   JAVA_HOME         JDK 17 (default: javac on PATH)
#   BUILD_DIR         CMake build dir (default out/work/build-android)
#   OUT               output dir (default out); the APK goes to $OUT/android/
#   JOBS              parallel compile jobs
#   KEYSTORE          signing key (default out/work/android/debug.keystore, made once)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-$REPO/out}"
WORK="${WORK:-$OUT/work}"
GEN="${NFSU2_GEN_DIR:-$WORK/gen}"
BUILD_DIR="${BUILD_DIR:-$WORK/build-android}"
ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$ANDROID_HOME/ndk/27.2.12479018}"
BT="$ANDROID_HOME/build-tools/34.0.0"
PLATFORM="$ANDROID_HOME/platforms/android-34/android.jar"
DEPS="${DEPS:-$WORK/deps}"
STAGE="$WORK/android"
KEYSTORE="${KEYSTORE:-$STAGE/debug.keystore}"
JOBS="${JOBS:-$(nproc)}"
[ -n "${JAVA_HOME:-}" ] && export PATH="$JAVA_HOME/bin:$PATH"

fail() { echo "error: $*" >&2; exit 1; }
[ -f "$GEN/recomp_funcs.h" ] || fail "no lifted C in $GEN (run build_from_xbe.sh)"
[ -f "$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" ] || fail "no NDK at $ANDROID_NDK_HOME (android/README.md)"
[ -x "$BT/aapt2" ] || fail "no build-tools 34.0.0 in $ANDROID_HOME (android/README.md)"
[ -f "$PLATFORM" ] || fail "no platforms;android-34 in $ANDROID_HOME (android/README.md)"
command -v javac >/dev/null || fail "javac not found: install JDK 17 or set JAVA_HOME"
command -v keytool >/dev/null || fail "keytool not found: install JDK 17 or set JAVA_HOME"

ANDROID_HOME="$ANDROID_HOME" ANDROID_NDK_HOME="$ANDROID_NDK_HOME" DEPS="$DEPS" bash "$REPO/android/build_deps.sh"
SDL_SRC="$(echo "$DEPS"/sdl2/SDL2-*)"

# Version from git, as on the Switch: 0.<commit count>.<sha7>
COUNT=$(git -C "$REPO" -c safe.directory='*' rev-list --count HEAD 2>/dev/null || echo 0)
SHA=$(git -C "$REPO" -c safe.directory='*' rev-parse --short=7 HEAD 2>/dev/null || echo nogit)
VERSION="0.$COUNT.$SHA"

echo "== libmain.so (lifted code, ~30-60 min the first time)"
cmake -S "$REPO" -B "$BUILD_DIR" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-30 -DANDROID_STL=c++_static \
    -DSDL2_DIR="$DEPS/sdl2-android/lib/cmake/SDL2" \
    -Dglslang_DIR="$DEPS/glslang-android/lib/cmake/glslang" \
    -DNFSU2_VULKAN=ON -DNFSU2_GEN_DIR="$GEN" -DXBOXRECOMP_DIR="$REPO/xboxrecomp" >/dev/null
ninja -C "$BUILD_DIR" -j"$JOBS"

echo "== APK $VERSION"
rm -rf "$STAGE/classes" "$STAGE/dex" "$STAGE/res" "$STAGE/assets" "$STAGE/lib" "$STAGE"/*.apk "$STAGE/compiled.zip"
mkdir -p "$STAGE/classes" "$STAGE/dex" "$STAGE/res/drawable" "$STAGE/assets" "$STAGE/lib/arm64-v8a"

# Native libraries: stripped in the APK, unstripped kept for symbolising crash reports.
mkdir -p "$OUT/android/symbols"
cp "$BUILD_DIR/libmain.so" "$OUT/android/symbols/libmain.so"
"$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" --strip-unneeded \
    -o "$STAGE/lib/arm64-v8a/libmain.so" "$BUILD_DIR/libmain.so"
cp "$DEPS/sdl2-android/lib/libSDL2.so" "$STAGE/lib/arm64-v8a/"

# Java: SDL's activity and ours.
find "$SDL_SRC/android-project/app/src/main/java" "$REPO/android/java" -name '*.java' > "$STAGE/sources.txt"
# core-lambda-stubs.jar: android.jar has no LambdaMetafactory; d8 desugars the lambdas.
javac -nowarn -source 8 -target 8 -bootclasspath "$PLATFORM" -classpath "$PLATFORM:$BT/core-lambda-stubs.jar" \
    -d "$STAGE/classes" @"$STAGE/sources.txt" 2>&1 | grep -v "^warning: \[options\]\|^Note:\|^[0-9] warning" || true
[ -f "$STAGE/classes/org/clx/recomp/ClxActivity.class" ] || fail "javac failed"
"$BT/d8" --release --min-api 30 --lib "$PLATFORM" --output "$STAGE/dex" \
    $(find "$STAGE/classes" -name '*.class')

# Resources: the icon (made from your XBE by tools/make_logo.py) and the default settings.
if [ -f "$REPO/assets/icon.jpg" ]; then
    cp "$REPO/assets/icon.jpg" "$STAGE/res/drawable/icon.jpg"
else
    echo "warning: assets/icon.jpg missing (tools/make_logo.py makes it): a blank icon" >&2
    python3 -c "import zlib,struct,sys
def c(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d))
sys.stdout.buffer.write(b'\x89PNG\r\n\x1a\n'+c(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+c(b'IDAT',zlib.compress(b'\0\x40\x40\x40'))+c(b'IEND',b''))" \
        > "$STAGE/res/drawable/icon.png"
fi
cp "$REPO/android/clx_options.txt" "$REPO/android/clx_env.txt" "$STAGE/assets/"
"$BT/aapt2" compile --dir "$STAGE/res" -o "$STAGE/compiled.zip"
"$BT/aapt2" link -o "$STAGE/unsigned.apk" -I "$PLATFORM" \
    --manifest "$REPO/android/AndroidManifest.xml" -A "$STAGE/assets" "$STAGE/compiled.zip" \
    --min-sdk-version 30 --target-sdk-version 34 \
    --version-code "${COUNT:-1}" --version-name "$VERSION" --replace-version

# classes.dex and lib/ go in with python's zipfile (no zip tool needed).
python3 - "$STAGE/unsigned.apk" "$STAGE/dex/classes.dex" "$STAGE/lib" <<'EOF'
import os, sys, zipfile
apk, dex, lib = sys.argv[1:]
with zipfile.ZipFile(apk, "a", zipfile.ZIP_DEFLATED) as z:
    z.write(dex, "classes.dex")
    for root, _, files in os.walk(lib):
        for f in files:
            p = os.path.join(root, f)
            z.write(p, "lib/" + os.path.relpath(p, lib))
EOF
"$BT/zipalign" -p -f 4 "$STAGE/unsigned.apk" "$STAGE/aligned.apk"

if [ ! -f "$KEYSTORE" ]; then
    echo "== making a signing key: $KEYSTORE (keep it: an update must be signed with the same key)"
    keytool -genkeypair -keystore "$KEYSTORE" -storepass android -keypass android \
        -alias clx -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=clx-recomp local build" >/dev/null 2>&1
fi
mkdir -p "$OUT/android"
"$BT/apksigner" sign --ks "$KEYSTORE" --ks-pass pass:android --ks-key-alias clx \
    --out "$OUT/android/clx.apk" "$STAGE/aligned.apk"
rm -f "$OUT/android/clx.apk.idsig"
echo "Android output: $OUT/android/clx.apk ($VERSION)"
