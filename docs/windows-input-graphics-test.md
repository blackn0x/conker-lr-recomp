# Experimental Windows input and menu compatibility test

This is a draft workaround for the Windows startup-input failure and the rainbow
bottles/candles/fireplace observed after regenerating with the x87 LAHF fix.
The general lifter correction and slingshot yaw remain enabled.

## What was established

- Guest controller reports stopped refreshing after startup, even with SDL focus.
  Changing the virtual controller's port alone did not restore input.
- The opt-in bridge refreshes the existing host report at XInputGetState and uses
  the title's open-handle table. The original guest implementation remains the
  fallback when CLX_NATIVE_PAD is unset or 0.
- Report sampling/hooks are serialized between the guest and USB scheduler.
- Live A/B testing isolated the menu regression to LAHF in 0x003F57D0. Disabling
  only that site's new behavior restores normal menu textures. The exact
  downstream graphics defect is still unknown. This exception intentionally
  preserves old behavior in that one path; it is not a general CPU fix.

## Build the opt-in test from your own retail NTSC XBE

1. Generate C normally using tools/regen.sh into a **separate private directory**.
2. Run `python tools/windows_input_compat.py <generated-directory>`.
3. Configure the Windows/MinGW build with
   `-DNFSU2_GEN_DIR=<generated-directory> -DCLX_EXPERIMENTAL_INPUT_COMPAT=ON`.
4. Build normally. Copy the resulting executable as
   `clx-graphics-native-test.exe` beside the normal Windows distribution and
   copy both `pc/Start-Conker-Graphics-Native-Input-Test.*` files there.
5. Run `Start-Conker-Graphics-Native-Input-Test.bat`.

The launcher selects HC0, four ports, one pad at port 2 (logical player 1),
enables CLX_NATIVE_PAD=1 and CLX_GFX_LAHF_SKIP=003F57D0, and clears synthetic
input scripts. It preserves the normal executable and existing settings.
Do not use the patched generated directory for a normal build; CMake checks it.
Generated game code and game data must not be committed.

## Validation and limits

A Windows test based on v0.53 plus #8/#9 loaded a save, accepted automated menu
commands and camera rotation, and returned to the Options menu with normal
bottles, candles and fireplace. The player then confirmed physical keyboard
and controller input work. Repeated cold-start reliability, the mouse in this
specific bridge build, other platforms and multiple-controller behavior have
not been established. The attached tested executable predates the Android
merge; it is not a v0.54 build. The PR is based on current main for review.

Headless tests use no game code:

- `python tests/test_windows_input_compat.py`: exact-site selection, preserving
  slingshot, idempotency and rejecting an unexpected translation without writes.
- Compile `tests/test_native_pad.c` with includes for the private generated
  directory and `xboxrecomp/include`: handles, fresh packets, 22-byte layout,
  invalid inputs and stdcall ABI.
- Compile `tests/test_report_concurrency.c` with includes for `xboxrecomp/src`
  and `xboxrecomp/src/platform`: 20,000 real reports from four threads, hook
  serialization, bytes and output canary. These C tests target Windows/MinGW.

This is intentionally opt-in pending a real fix for stalled USB polling and
understanding of the graphics cache path. It should not be merged as an
unqualified replacement for the normal input/rendering implementation.
