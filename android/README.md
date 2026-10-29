# Android

An arm64 APK. It uses the Vulkan renderer, the same one as `clx-vulkan.nro` on the Switch.
SDL2 provides the window, the sound and the game controllers. Each start writes a log
to the phone's **Download** folder. If the game crashes, the crash report goes in the same log.

**Status: experimental.** The APK builds. Nothing has been tested on a phone yet.

## What the phone needs

- arm64 (`arm64-v8a`) and Android 11 or newer.
- A GPU driver with **Vulkan 1.3**, `VK_KHR_push_descriptor` and
  `VK_EXT_vertex_input_dynamic_state`. Recent Adreno (Snapdragon 8 Gen 1 and newer), Mali and
  Xclipse drivers usually have them. Older drivers do not. If one is missing, the log names it.
- 8 GB of RAM is recommended. The game reserves a 4 GB address range for the Xbox memory.
- About 5 GB free for the game folder.
- Touch controls are built in. A **gamepad** (Bluetooth or USB) is better; the touch controls
  hide while one is connected, and a tap on the screen brings them back.

## Build

You build on Linux. You need these, installed in your home folder (no root needed):

| What | Version | Where `android/build.sh` looks |
|---|---|---|
| Android SDK command-line tools | any | `$ANDROID_HOME` (default `~/Android/Sdk`) |
| SDK packages | `platforms;android-34`, `build-tools;34.0.0`, `ndk;27.2.12479018` | in the SDK |
| JDK | 17 | `$JAVA_HOME`, or `javac` on the PATH |
| Host tools | cmake, ninja, python3 (capstone, Pillow), curl, git | PATH |

```bash
# JDK 17 (Temurin) and the SDK command-line tools
mkdir -p ~/Android && cd ~/Android
curl -fL -o jdk.tar.gz "https://api.adoptium.net/v3/binary/version/jdk-17.0.13%2B11/linux/x64/jdk/hotspot/normal/eclipse"
tar xzf jdk.tar.gz && rm jdk.tar.gz
curl -fLO https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
mkdir -p Sdk/cmdline-tools && unzip -q commandlinetools-linux-*_latest.zip -d Sdk/cmdline-tools
mv Sdk/cmdline-tools/cmdline-tools Sdk/cmdline-tools/latest
export JAVA_HOME=~/Android/jdk-17.0.13+11
yes | Sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=$HOME/Android/Sdk --licenses
Sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=$HOME/Android/Sdk \
    "platforms;android-34" "build-tools;34.0.0" "ndk;27.2.12479018"

# Build (from the repository)
VARIANTS=android ./build_from_xbe.sh ~/conker-disc/default.xbe
```

The first build lifts the XBE (about 15 minutes). It then builds SDL2 2.30.9 and glslang 14.3.0
for Android (`android/build_deps.sh`, a few minutes). Compiling the game takes about 40 minutes.
The build makes no Gradle project: `android/build.sh` calls javac, d8, aapt2, zipalign and
apksigner directly.

Output, in `out/android/`:

| File | What it is |
|---|---|
| `clx.apk` | The app. It contains code made from your XBE: do not share it. |
| `symbols/libmain.so` | The same library, unstripped. Use it to read the crash reports (see below). |

The APK is signed with a key made on the first build, `out/work/android/debug.keystore`. Keep
this file. A later APK installs over an earlier one only if both are signed with the same key.

## Install

1. `adb install -r out/android/clx.apk`, or copy the APK to the phone and open it.
2. Copy your unpacked disc to the phone so that `/sdcard/ConkerLR/game/default.xbe` exists:

   ```bash
   adb push conker-disc/. /sdcard/ConkerLR/game/
   ```

3. Open **Conker LR**. Tap **Allow all files access** and turn the switch on. The game needs it
   to read the game folder and to write the logs to Download.
4. Connect a gamepad and tap **Start**.

The first start compiles shaders, so the first minutes stutter.

## Files on the phone

| Path | What it is |
|---|---|
| `/sdcard/ConkerLR/game/` | your unpacked disc |
| `/sdcard/ConkerLR/save/` | saves |
| `/sdcard/ConkerLR/cache/` | shader and pipeline caches (safe to delete) |
| `/sdcard/ConkerLR/clx_options.txt` | picture, frame rate, camera ([settings](../docs/settings-and-controls.md)) |
| `/sdcard/ConkerLR/clx_env.txt` | advanced switches, with a comment for each |
| `/sdcard/Download/ConkerLR-logs/<date_time>/` | **one folder for each start** |

The two settings files are copied from the APK on the first start. After that, your edits are
kept.

## Logs and bug reports

Each start makes a new folder in `Download/ConkerLR-logs/`. The 20 newest folders are kept.

- `clx_log.txt` has everything the game prints. It starts with the phone's model, SoC, Android
  version, page size and memory. The Vulkan lines follow: GPU, driver version and any missing
  extension.
- On a crash, `clx_log.txt` ends with a `[CRASH]` report. It has the signal, the fault address,
  the CPU registers, the guest's registers and stack, and the host stack as `library+offset`.
- `xbox_kernel.log` is the kernel's own log.
- A Java exception (in the launcher or the game screen) goes to
  `ConkerLR-logs/<date_time>_java_crash.txt`.

For a bug report, attach the newest folder. To turn the `libmain.so+0x...` frames of a crash
report into function names, run:

```bash
~/Android/Sdk/ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-addr2line \
    -f -C -e out/android/symbols/libmain.so 0x1234abc
```

For more detail in the log, set these in `clx_env.txt`: `RECOMP_QUIET=0` (periodic lines),
`RECOMP_FRAME_STATS=1` (frame cost each second) and `RECOMP_VK_TRACE=200` (each Vulkan step of
the first 200 draws, for a crash inside the GPU driver).

Without "All files access", the logs go to the app's own folder instead:
`Android/data/org.clx.recomp/files/logs/`.

## Known limits

- The touch controls are a fixed layout: left stick (left side of the screen), camera (drag
  anywhere on the right side), d-pad, A B X Y, black, white, LT, RT, L3, R3, Back and Start.
  They cannot be moved or resized yet. A keyboard also works (the PC keys, see
  [settings](../docs/settings-and-controls.md)).
- The renderer needs the Vulkan features listed above. There is no OpenGL ES renderer.
- When you switch away from the app, the game pauses. When you come back, the renderer makes a
  new surface. If the game does not come back, send the log.
- Phones that use 16 KB memory pages (an Android 15 developer option) are not tested. The log
  shows the page size.
