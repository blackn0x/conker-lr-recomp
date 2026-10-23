# Troubleshooting

## The game hangs on the loading logo (0 fps)

**Cause.** The first start copies the disc's sound banks into a cache folder. If you quit during
that copy, the next start can hang.

**Fix.** Delete the cache folder, then start again. Let the first start finish.

| Platform | Delete |
|---|---|
| Switch | `sdmc:/switch/clx/save/Cache` |
| Windows | the `CACHE` folder in the disc folder, and `%LOCALAPPDATA%\xboxrecomp` |
| Linux | the `CACHE` folder in the disc folder, and `~/.local/share/xboxrecomp` |

## The Switch app crashes at start, or says there is not enough memory

Start it with **title takeover**. Hold **R** while you open any game, then pick the app in
hbmenu. Album (applet) mode does not have enough memory.

## My gamepad is not found, or a button is wrong

Plug the pad in (or pair it) and open the settings menu (Esc). The **Controller** line shows the
name of the pad on port 1, or NONE. If you have more than one pad, left/right makes the next
one pad 1. Use **Remap controller** to set each button, and **Reset controls** to go back to
the defaults. The keyboard has its own **Remap keyboard** line.

## I want to quit the game

Open the settings menu and choose **Exit game** (press A twice), or close the window.

## The first minutes stutter

The game compiles shaders as it meets them. It saves them, so later starts are smooth.
On the Switch the caches are `progcache.bin` (OpenGL) and `vk*.bin` (Vulkan) in
`sdmc:/switch/clx/`. On a PC they are in the shader cache folder (see [Building](building.md)).

## "Failed to load default.xbe" or the usage message on a PC

The disc folder is wrong. It must be the folder that has `default.xbe`. Give it on the command
line (`clx.sh <folder>` or `clx.bat <folder>`) or write `game=<folder>` in `clx_options.txt`.
The folder must be one you may write to: the game saves into it.

## No window, a black window, or a crash on a PC

You need a GPU and a driver with OpenGL 3.3. Update the graphics driver. On Windows, read
`clx_log.txt` and `clx_err.txt` next to `clx.bat`. On Linux, read the terminal.

## No sound on a PC

PC sound is not tested well yet. Check `volume` in the settings menu (Esc) and in
`clx_options.txt`. To see the sound level in the log, set `RECOMP_AUDIO_PEAK=1`: it prints the
level before and after the volume stage.

## The build stops

| Message | What to do |
|---|---|
| `has SHA-1 ... this port needs the retail NTSC default.xbe` | Your XBE is another version. Use the retail NTSC (North America) disc. |
| `python3 needs capstone and Pillow` | `pip3 install capstone==5.0.7 Pillow` |
| `devkitPro not found` | Install devkitPro, or use Docker. See [Building](building.md). |
| The lift is killed, or the build runs out of memory | The lift needs about 15 GB of RAM. Close other programs. Set `JOBS=4` for the compile. |
| `run this in an MSYS2 UCRT64 shell` | Use `build_from_xbe.ps1`, or open the **MSYS2 UCRT64** shell. |
| A tool is missing on Windows | Run `build_from_xbe.ps1` again with `-Install`. |
| Docker: permission errors in `out/` | Run the container with `--user "$(id -u):$(id -g)" -e HOME=/tmp`. |

If the lifted code is old after you change the tools, run with `REGEN=1`.

## The 16:9 picture looks stretched

16:9 widens the 3D view. The HUD, the menus and the movies are stretched. This is a known issue.

## I found a bug

Open an issue. Say the platform, the version, and your `clx_options.txt`. Add the log:
`sdmc:/switch/clx/clx_log.txt` on the Switch, `clx_log.txt` next to `clx.bat` on Windows, the
terminal output on Linux. Do not attach built programs or game files.
