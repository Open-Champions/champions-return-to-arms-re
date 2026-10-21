# install-windows.ps1 - build the native Champions: Return to Arms from YOUR OWN disc, on this Windows PC.
# Double-click install-windows.bat beside this file (it starts this script).  One step:
#   1. the tools: Python 3 (if it is missing: installed with winget from python.org, after you say yes) and a
#      portable compiler, llvm-mingw, downloaded from its official GitHub release
#      (https://github.com/mstorsjo/llvm-mingw/releases) into this folder's local\toolchain - nothing is
#      installed into Windows for it;
#   2. asks for your disc image (.iso) of the US release, SLUS-20973 v2.00, in a file window;
#   3. copies SLUS_209.73 out of it, translates the game's code to C++ and builds rta_app.exe
#      (tools\install\fromdisc.py; 10 to 40 minutes);
#   4. puts "Champions RTA Native" on your desktop.
# Nothing of the game comes with this repository and nothing of yours leaves this PC: the program is built
# here, into this folder's local\ (never share that folder).
# Options (PowerShell):  -Disc FILE  -Desktop DIR  -Yes  -LlvmMingwTag 20xxxxxx (a release of your choice)
#                        -Godot (also the game library of the Godot version: tools\godot\build_lib_win.py)
# The program is x86-64; on Windows on ARM it runs under Windows' own x86-64 emulation (the aarch64 build of
# llvm-mingw is fetched there and asked for x86-64 code).
param([string]$Disc = "", [string]$Desktop = "", [switch]$Yes, [string]$LlvmMingwTag = "", [switch]$Godot)
$ErrorActionPreference = "Stop"
$Work = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Work
function Say($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Ask($question) {
    if ($Yes) { return $true }
    $a = Read-Host "$question [Y/n]"
    return -not ($a -match '^[nN]')
}
function Fail($text) { Write-Host $text -ForegroundColor Red; exit 1 }

Say "Champions: Return to Arms - the native build from your own disc ($Work)"

# 1a. Python 3
function Find-Python {
    foreach ($line in @("py -3", "python", "python3")) {
        $c = $line -split ' '
        $exe = $c[0]; $rest = @($c | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $v = & $exe @rest -c "import sys; print('%d.%d' % sys.version_info[:2]); sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) { return ,(@($exe) + $rest) }
        } catch { }
    }
    return $null
}
$Py = Find-Python
if (-not $Py) {
    Say "Python 3 is not installed (the build scripts are Python)."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Fail "Install Python 3 from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'), then run this again." }
    if (-not (Ask "Install Python 3.12 from python.org with winget now?")) { Fail "Install Python 3 from https://www.python.org, then run this again." }
    winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --source winget
    $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
    $Py = Find-Python
    if (-not $Py) { Fail "Python is still not found: open a new window and run this again." }
}
$PyExe = $Py[0]; $PyArgs = @($Py | Select-Object -Skip 1)
Write-Host ("python: " + (& $PyExe @PyArgs -c "import sys; print(sys.executable, sys.version.split()[0])"))

# 1b. llvm-mingw (portable: an archive unpacked into local\toolchain)
$Tools = Join-Path $Work "local\toolchain"
New-Item -ItemType Directory -Force -Path $Tools | Out-Null
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64" -or $env:PROCESSOR_ARCHITEW6432 -eq "ARM64") { "aarch64" } else { "x86_64" }
$Llvm = Get-ChildItem -Path $Tools -Directory -Filter "llvm-mingw-*-ucrt-$Arch" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
if ($LlvmMingwTag -and $Llvm -and $Llvm.Name -notlike "llvm-mingw-$LlvmMingwTag-*") { $Llvm = $null }
if (-not $Llvm -or -not (Test-Path (Join-Path $Llvm.FullName "bin\x86_64-w64-mingw32-clang++.exe"))) {
    Say "The compiler (llvm-mingw, about 150 MB) is downloaded from https://github.com/mstorsjo/llvm-mingw/releases"
    if (-not (Ask "Download it into local\toolchain now?")) { Fail "The program cannot be built without a compiler." }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $api = if ($LlvmMingwTag) { "https://api.github.com/repos/mstorsjo/llvm-mingw/releases/tags/$LlvmMingwTag" } else { "https://api.github.com/repos/mstorsjo/llvm-mingw/releases/latest" }
    $release = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "rta-native-installer" }
    $asset = $release.assets | Where-Object { $_.name -match "^llvm-mingw-\d+-ucrt-$Arch\.zip$" } | Select-Object -First 1
    if (-not $asset) { Fail "The release $($release.tag_name) has no llvm-mingw-...-ucrt-$Arch.zip" }
    if ($asset.browser_download_url -notlike "https://github.com/mstorsjo/llvm-mingw/releases/download/*") { Fail "Unexpected download address: $($asset.browser_download_url)" }
    $zip = Join-Path $Tools $asset.name
    Write-Host "downloading $($asset.name) ($([math]::Round($asset.size / 1MB)) MB) of release $($release.tag_name)"
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing
    if ((Get-Item $zip).Length -ne $asset.size) { Fail "The download is not complete; run this again." }
    Write-Host ("SHA-256 " + (Get-FileHash -Algorithm SHA256 $zip).Hash)
    Write-Host "unpacking ..."
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $Tools)
    Remove-Item $zip
    $Llvm = Get-ChildItem -Path $Tools -Directory -Filter "llvm-mingw-*-ucrt-$Arch" | Sort-Object Name | Select-Object -Last 1
    if (-not $Llvm) { Fail "The archive did not unpack into local\toolchain\llvm-mingw-...-ucrt-$Arch" }
}
$env:PATH = (Join-Path $Llvm.FullName "bin") + ";" + $env:PATH
Write-Host ("compiler: " + (& x86_64-w64-mingw32-clang++ --version | Select-Object -First 1) + " (" + $Llvm.Name + ")")

# 2. the disc image
if (-not $Disc) {
    Say "Choose your disc image of Champions: Return to Arms (US, SLUS-20973, v2.00) in the window that opens."
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Your disc image of Champions: Return to Arms (.iso)"
    $dialog.Filter = "Disc images (*.iso)|*.iso|All files (*.*)|*.*"
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { Fail "No disc image was chosen." }
    $Disc = $dialog.FileName
}
if (-not (Test-Path -LiteralPath $Disc -PathType Leaf)) { Fail "Not a file: $Disc" }

# 3. and 4. the translation, the build and the shortcut
Say "Building (10 to 40 minutes)"
$a = @("-B", "tools\install\fromdisc.py", "--platform", "windows", "--disc", $Disc)
if ($Desktop) { $a += @("--desktop", $Desktop) }
if ($Godot) { $a += @("--godot") }
& $PyExe @PyArgs @a
if ($LASTEXITCODE -ne 0) { Fail "The build did not finish; the lines above say why." }
Say "Done. Start the game with 'Champions RTA Native' on your desktop, or play.bat in local\recomp-out\win\rta-windows\ (the log: rta-data\rta_app-log.txt there)."
