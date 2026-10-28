# Run Conker: Live & Reloaded (Xbox recompilation) on Windows.
#
#   clx.bat [path\to\unpacked\disc]
#
# The disc folder is the one with default.xbe. Give it here, or as game=... in
# clx_options.txt (next to this script), or in NFSU2_GAME_DIR.
# The game writes its cache and its own save folders into that folder, and
# the console save partitions to %LOCALAPPDATA%\xboxrecomp.
#
# The game reads clx_options.txt itself (aspect, fps, camera, volume, render
# scale, ...; see docs/settings-and-controls.md). This script reads only the keys
# the game does not: game, skip_intro, start_single. A variable you set yourself
# wins over the file. The program's messages go to clx_log.txt next to this script.
param([string]$Game = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$optFile = if ($env:CLX_OPTIONS) { $env:CLX_OPTIONS } else { Join-Path $here "clx_options.txt" }

# Give the game window the keyboard focus after launch. Being started by a
# launcher is not enough on Windows: the game's SDL window can stay behind the
# launcher/desktop and then no key or controller button reaches it
# (SDL_RaiseWindow alone is often blocked by the foreground lock).
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ConkerFocus {
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] static extern IntPtr SetActiveWindow(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr SetFocus(IntPtr h);
    public static bool IsForeground(IntPtr h) { return GetForegroundWindow() == h; }
    public static void Focus(IntPtr h) {
        IntPtr fg = GetForegroundWindow();
        uint p1 = 0, p2 = 0;
        uint t1 = GetWindowThreadProcessId(fg, out p1);
        uint t2 = GetWindowThreadProcessId(h, out p2);
        ShowWindow(h, 5);
        if (t1 != 0 && t1 != t2) AttachThreadInput(t1, t2, true);
        BringWindowToTop(h);
        SetForegroundWindow(h);
        SetActiveWindow(h);
        SetFocus(h);
        if (t1 != 0 && t1 != t2) AttachThreadInput(t1, t2, false);
    }
}
'@
if (-not $Game) { $Game = $env:NFSU2_GAME_DIR }

function Set-Default([string]$name, [string]$value) {
    if (-not [Environment]::GetEnvironmentVariable($name)) {
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

# Defaults for playing on a PC
Set-Default "CLX_START_SINGLE" "1"       # title cursor on Game 1
Set-Default "RECOMP_PAD_MASK" "0x20"     # BACK opens the Xbox Live sign-up: off (until the game masks it itself)
Set-Default "RECOMP_QUIET" "1"
Set-Default "RECOMP_CACHE_DIR" ((Join-Path $env:LOCALAPPDATA "clx") + "\")
Set-Default "CLX_OPTIONS" $optFile
Set-Default "CLX_MOUSE_OPTIONS" (Join-Path $here "clx_mouse_options.txt")

if (Test-Path $optFile) {
    foreach ($line in Get-Content $optFile) {
        $line = ($line -replace '#.*$', '').Trim()
        if (-not $line -or $line -notmatch '=') { continue }
        $k, $v = $line -split '=', 2
        $k = $k.Trim(); $v = $v.Trim()
        switch ($k) {
            "game"         { if (-not $Game) { $Game = $v } }
            "skip_intro"   { if ($v -eq "1") { Set-Default "CLX_SKIP_INTRO" "1" } }
            "start_single" { Set-Default "CLX_START_SINGLE" $v }
            "fullscreen"   {
                if ($v -eq "borderless" -or $v -eq "fullscreen" -or $v -eq "1") {
                    Set-Default "CLX_BORDERLESS" "1"
                } else {
                    Set-Default "CLX_BORDERLESS" "0"
                }
            }
            "mouse"        {
                if ($v -eq "0" -or $v -eq "off") { Set-Default "CLX_NATIVE_MOUSE" "0" }
                else { Set-Default "CLX_NATIVE_MOUSE" "1" }
            }
        }
    }
}
# Mouse and borderless are the defaults for this build; an option in the
# file (or a variable you set yourself) still wins.
Set-Default "CLX_NATIVE_MOUSE" "1"
Set-Default "CLX_BORDERLESS" "1"

if (-not $Game -or -not (Test-Path (Join-Path $Game "default.xbe"))) {
    Write-Host "usage: clx.bat C:\path\to\unpacked\disc   (the folder with default.xbe)"
    Write-Host "or put game=C:\path\to\disc in $optFile"
    exit 1
}
New-Item -ItemType Directory -Force $env:RECOMP_CACHE_DIR | Out-Null
$env:NFSU2_GAME_DIR = (Resolve-Path $Game).Path
$exe = Join-Path $here "clx.exe"
$p = Start-Process -FilePath $exe -WorkingDirectory $here -PassThru `
        -RedirectStandardOutput (Join-Path $here "clx_log.txt") `
        -RedirectStandardError (Join-Path $here "clx_err.txt")
if ($p) {
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $p.Refresh()
        if ($p.HasExited) { break }
        if ($p.MainWindowHandle -ne 0) {
            for ($i = 0; $i -lt 12; $i++) {
                [ConkerFocus]::Focus($p.MainWindowHandle)
                Start-Sleep -Milliseconds 250
                if ([ConkerFocus]::IsForeground($p.MainWindowHandle)) { break }
            }
            if ([ConkerFocus]::IsForeground($p.MainWindowHandle)) { break }
        }
        Start-Sleep -Milliseconds 300
    }
    $p.WaitForExit()
    exit $p.ExitCode
}
exit 1
