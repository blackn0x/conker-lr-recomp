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
        }
    }
}

if (-not $Game -or -not (Test-Path (Join-Path $Game "default.xbe"))) {
    Write-Host "usage: clx.bat C:\path\to\unpacked\disc   (the folder with default.xbe)"
    Write-Host "or put game=C:\path\to\disc in $optFile"
    exit 1
}
New-Item -ItemType Directory -Force $env:RECOMP_CACHE_DIR | Out-Null
$env:NFSU2_GAME_DIR = (Resolve-Path $Game).Path
$p = Start-Process -FilePath (Join-Path $here "clx.exe") -WorkingDirectory $here -Wait -PassThru `
        -RedirectStandardOutput (Join-Path $here "clx_log.txt") `
        -RedirectStandardError (Join-Path $here "clx_err.txt")
exit $p.ExitCode
