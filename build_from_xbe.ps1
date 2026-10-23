# Build Conker: Live & Reloaded for Windows from your own default.xbe.
#
#   .\build_from_xbe.ps1 C:\path\to\default.xbe [-Install]
#
# Runs build_from_xbe.sh (VARIANTS=windows) inside MSYS2's UCRT64 shell.
# Needs MSYS2 (https://www.msys2.org, default folder C:\msys64). With -Install
# the missing MSYS2 packages are installed first (pacman, about 1 GB).
# Output: out\windows\ (clx.exe, DLLs, clx.bat, clx_options.txt).
# The first build lifts the XBE (about 15 minutes) and compiles (about 5).
param(
    [Parameter(Mandatory = $true)][string]$Xbe,
    [string]$Msys = "C:\msys64",
    [switch]$Install
)
$ErrorActionPreference = "Stop"
$bash = Join-Path $Msys "usr\bin\bash.exe"
if (-not (Test-Path $bash)) { throw "MSYS2 not found in $Msys (install it from https://www.msys2.org, or pass -Msys)" }
if (-not (Test-Path $Xbe)) { throw "no file $Xbe" }
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path

# C:\a\b -> /c/a/b for the MSYS2 shell
function To-Msys([string]$p) {
    $full = (Resolve-Path $p).Path
    "/" + $full.Substring(0, 1).ToLower() + ($full.Substring(2) -replace '\\', '/')
}

# Windows PowerShell 5.1 turns a native program's stderr lines into errors; do not stop on them
# (the exit codes are checked).
$ErrorActionPreference = "Continue"

$pkgs = "mingw-w64-ucrt-x86_64-clang mingw-w64-ucrt-x86_64-SDL2 mingw-w64-ucrt-x86_64-cmake " +
        "mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-pkgconf mingw-w64-ucrt-x86_64-python " +
        "mingw-w64-ucrt-x86_64-python-pillow mingw-w64-ucrt-x86_64-python-capstone git"
if ($Install) {
    & $bash -lc "export MSYSTEM=UCRT64; source /etc/profile; pacman -S --noconfirm --needed $pkgs"
    if ($LASTEXITCODE -ne 0) { throw "pacman failed" }
}
$sh = "export MSYSTEM=UCRT64; source /etc/profile; cd '$(To-Msys $repo)'; " +
      "VARIANTS=windows ./build_from_xbe.sh '$(To-Msys $Xbe)'"
& $bash -lc $sh
if ($LASTEXITCODE -ne 0) {
    Write-Host "The build failed. If tools are missing, run again with -Install." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "Done: $repo\out\windows\clx.bat" -ForegroundColor Green
