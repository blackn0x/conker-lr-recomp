# Windows input/menu test, 2026-10-31

This branch preserves the source used for the exact Windows diagnostic build
confirmed by the player. It is based on v0.53 plus the slingshot and mouse
cleanup changes (#8/#9), before the Android merge. It is not v0.54.

Regenerate from your own retail NTSC default.xbe using tools/regen.sh, then
build with Windows/MinGW. The regeneration script applies windows_bisect_test.py
to the private generated directory: x87 LAHF switches (slingshot always on),
bounded callback logging, and renaming the original input function for the
opt-in native bridge. No generated game code is stored in this repository.

Use pc/Start-Conker-Graphics-Native-Input-Test.bat and the matching ps1 beside
clx-graphics-native-test.exe, the normal DLLs, default settings and your game/
folder. The launcher uses one virtual pad, enables CLX_NATIVE_PAD, skips only
the new LAHF behavior in 003F57D0, and clears all synthetic input scripts.

The graphics exception is a temporary workaround, not an established renderer
root-cause fix. A clean draft PR against current upstream carries the minimal
experimental implementation. Physical keyboard/controller, menu textures and
scripted in-game camera movement were checked. Multiple pads, repeated cold
boots, mouse behavior with this bridge and other platforms remain unverified.
