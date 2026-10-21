# setup-windows.ps1 - the work and the window of "Champions Setup.exe" (tools/install/setup/windows/stub.c starts it).
#
# One window with a progress bar:
#   1. finds YOUR disc image of Champions: Return to Arms (US, SLUS-20973, v2.00) in Downloads, Desktop, Documents and
#      on the other drives (an .iso of 1 to 9 GB whose SLUS_209.73 has PCSX2's checksum 4028A55F), else one file window;
#   2. fetches Python (the official "embeddable" build from python.org) and the compiler llvm-mingw (its official
#      GitHub release) into %LOCALAPPDATA%\Champions\tools - pinned versions, size and SHA-256 checked, nothing
#      installed into Windows, no administrator rights;
#   3. unpacks our source code (source.zip beside this script: the repository, nothing of the game) into
#      %LOCALAPPDATA%\Champions\workspace and runs tools\install\fromdisc.py: the game's executable out of the disc
#      image, translated and built on this PC;
#   4. "Champions" on the desktop and in the Start menu, and starts it.
#   With the Godot version in the payload (godot\RtaGodot.exe, .pck and the extension's DLL: our application, no game
#   inside - build_setups.py puts it there), step 3 also builds its game library (fromdisc.py --godot:
#   tools/godot/build_lib_win.py, into %APPDATA%\Open Champions\RTA Godot) and step 4 puts the Godot version into
#   %LOCALAPPDATA%\Champions\godot with a "Champions Godot" shortcut beside the other.
# setup.ini beside this script may hold "service = HOST:PORT", the room service the program uses (written by whoever
# hands out the setup; there is none in the repository).
# Options for a test from a console:  -Disc FILE  -Console (no window: lines on the console)  -NoStart
param([string]$Payload = $PSScriptRoot, [string]$Disc = "", [switch]$Console, [switch]$NoStart)
$ErrorActionPreference = "Stop"

$PythonVersion = "3.13.9"
$Python = @{
    "x86_64"  = @{ Url = "https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip"; Size = 10926675; Sha = "91d828c2da3a029b41699e918674a0cb379c02cf20dab9c501306885f837402a" }
    "aarch64" = @{ Url = "https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-arm64.zip"; Size = 10328622; Sha = "cba392bd5c7aed68b26d1b523822cc3d80802c085481dfde79262ebfc7179d26" }
}
$LlvmTag = "20261006"
$Llvm = @{
    "x86_64"  = @{ Url = "https://github.com/mstorsjo/llvm-mingw/releases/download/20261006/llvm-mingw-20261006-ucrt-x86_64.zip"; Size = 190836485; Sha = "317492c456aa27ee607a5919f1d2d38dcdc1112516a24d0bf4b00d078f52d17a" }
    "aarch64" = @{ Url = "https://github.com/mstorsjo/llvm-mingw/releases/download/20261006/llvm-mingw-20261006-ucrt-aarch64.zip"; Size = 185727081; Sha = "9a835d5179c9f3a5a783c11a7f14062a249b4765dd11add64a66786864e82ab2" }
}

$Base = Join-Path $env:LOCALAPPDATA "Champions"
$Tools = Join-Path $Base "tools"
$Work = Join-Path $Base "workspace"
$LogFile = Join-Path $Base "setup-log.txt"
New-Item -ItemType Directory -Force -Path $Base, $Tools | Out-Null
"Champions Setup $(Get-Date -Format s)" | Set-Content -Encoding UTF8 $LogFile

# ---- helpers in C#: the disc check, downloads and unpacking on their own threads (the window keeps answering) ----
Add-Type -ReferencedAssemblies System.IO.Compression, System.IO.Compression.FileSystem -TypeDefinition @"
using System;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Threading;
public static class ChampionsDisc {
    static uint U32(byte[] b, int at) { return (uint)(b[at] | b[at + 1] << 8 | b[at + 2] << 16 | b[at + 3] << 24); }
    public static bool IsRight(string path) {
        try {
            using (var f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite)) {
                var pvd = new byte[2048];
                f.Seek(16 * 2048, SeekOrigin.Begin);
                if (f.Read(pvd, 0, 2048) != 2048 || pvd[1] != 'C' || pvd[2] != 'D' || pvd[3] != '0' || pvd[4] != '0' || pvd[5] != '1') return false;
                uint lba = U32(pvd, 158), size = U32(pvd, 166);
                if (size == 0 || size > (1 << 20)) return false;
                var dir = new byte[size];
                f.Seek((long)lba * 2048, SeekOrigin.Begin);
                if (f.Read(dir, 0, (int)size) != size) return false;
                int at = 0;
                while (at < dir.Length) {
                    int len = dir[at];
                    if (len == 0) { at = (at / 2048 + 1) * 2048; continue; }
                    if (at + 33 > dir.Length || at + len > dir.Length) break;
                    int n = dir[at + 32];
                    string name = System.Text.Encoding.ASCII.GetString(dir, at + 33, Math.Min(n, dir.Length - at - 33)).ToUpperInvariant();
                    if ((dir[at + 25] & 2) == 0 && name.Split(';')[0] == "SLUS_209.73") {
                        uint elba = U32(dir, at + 2), esize = U32(dir, at + 10);
                        if (esize < 1000000 || esize > 20000000) return false;
                        var elf = new byte[esize];
                        f.Seek((long)elba * 2048, SeekOrigin.Begin);
                        int got = 0;
                        while (got < elf.Length) { int r = f.Read(elf, got, elf.Length - got); if (r <= 0) return false; got += r; }
                        if (elf[0] != 0x7F || elf[1] != 'E' || elf[2] != 'L' || elf[3] != 'F') return false;
                        uint crc = 0;
                        for (int i = 0; i + 4 <= elf.Length; i += 4) crc ^= U32(elf, i);
                        return crc == 0x4028A55F;
                    }
                    at += len;
                }
            }
        } catch (Exception) { }
        return false;
    }
}
public class ChampionsJob {
    public long Done, Total;
    public volatile bool Finished;
    public volatile string Error = "";
    Thread thread;
    public static ChampionsJob Download(string url, string file) {
        var job = new ChampionsJob();
        job.thread = new Thread(() => {
            try {
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
                var request = (HttpWebRequest)WebRequest.Create(url);
                request.UserAgent = "Champions-Setup";
                request.AllowAutoRedirect = true;
                using (var response = (HttpWebResponse)request.GetResponse())
                using (var input = response.GetResponseStream())
                using (var output = new FileStream(file, FileMode.Create, FileAccess.Write)) {
                    job.Total = response.ContentLength;
                    var buffer = new byte[1 << 16];
                    int n;
                    while ((n = input.Read(buffer, 0, buffer.Length)) > 0) { output.Write(buffer, 0, n); Interlocked.Add(ref job.Done, n); }
                }
            } catch (Exception e) { job.Error = e.Message; }
            job.Finished = true;
        });
        job.thread.IsBackground = true;
        job.thread.Start();
        return job;
    }
    public static ChampionsJob Unzip(string zip, string folder) {
        var job = new ChampionsJob();
        job.thread = new Thread(() => {
            try {
                string root = Path.GetFullPath(folder);
                using (var archive = ZipFile.OpenRead(zip)) {
                    job.Total = archive.Entries.Count;
                    foreach (var entry in archive.Entries) {
                        string target = Path.GetFullPath(Path.Combine(root, entry.FullName));
                        if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new Exception("a path outside the folder: " + entry.FullName);
                        if (entry.FullName.EndsWith("/")) { Directory.CreateDirectory(target); }
                        else { Directory.CreateDirectory(Path.GetDirectoryName(target)); entry.ExtractToFile(target, true); }
                        Interlocked.Increment(ref job.Done);
                    }
                }
            } catch (Exception e) { job.Error = e.Message; }
            job.Finished = true;
        });
        job.thread.IsBackground = true;
        job.thread.Start();
        return job;
    }
}
"@

# ---- the window (or the console with -Console) ----
$script:Ui = $null
function Log([string]$line) {
    Add-Content -Encoding UTF8 -Path $LogFile -Value $line
    if ($Console) { Write-Host $line } elseif ($script:Ui) { $script:Ui.Log.AppendText($line + "`r`n") }
}
function Show([string]$text, [int]$percent = -1, [string]$detail = $null) {
    if ($Console) {
        $p = if ($percent -ge 0) { "[$percent%] " } else { "" }
        Write-Host "== $p$text$(if ($detail) { " - $detail" })"
    } elseif ($script:Ui) {
        $script:Ui.Message.Text = $text
        if ($percent -ge 0) { $script:Ui.Bar.Value = [Math]::Max(0, [Math]::Min(100, $percent)) }
        if ($null -ne $detail) { $script:Ui.Detail.Text = $detail }
    }
    Pump
}
function Pump { if (-not $Console) { [System.Windows.Forms.Application]::DoEvents() } }
function Wait-Job2($job, [scriptblock]$each) {
    while (-not $job.Finished) { & $each; Pump; Start-Sleep -Milliseconds 120; if ($script:Cancelled) { throw "Setup was stopped." } }
    & $each
    if ($job.Error) { throw $job.Error }
}
$script:Cancelled = $false

if (-not $Console) {
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Champions Setup"
    $form.ClientSize = New-Object System.Drawing.Size(560, 230)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
    $heading = New-Object System.Windows.Forms.Label
    $heading.Text = "Champions Setup"; $heading.Font = New-Object System.Drawing.Font("Segoe UI", 15, [System.Drawing.FontStyle]::Bold)
    $heading.SetBounds(20, 14, 520, 34)
    $message = New-Object System.Windows.Forms.Label
    $message.SetBounds(20, 52, 520, 58)
    $bar = New-Object System.Windows.Forms.ProgressBar
    $bar.SetBounds(20, 114, 520, 22); $bar.Minimum = 0; $bar.Maximum = 100
    $detail = New-Object System.Windows.Forms.Label
    $detail.SetBounds(20, 140, 520, 20); $detail.ForeColor = [System.Drawing.Color]::DimGray; $detail.AutoEllipsis = $true
    $log = New-Object System.Windows.Forms.TextBox
    $log.Multiline = $true; $log.ScrollBars = "Vertical"; $log.ReadOnly = $true; $log.Visible = $false
    $log.Font = New-Object System.Drawing.Font("Consolas", 8.5); $log.SetBounds(20, 166, 520, 200)
    $details = New-Object System.Windows.Forms.Button
    $details.Text = "Show details"; $details.SetBounds(20, 186, 120, 30)
    $primary = New-Object System.Windows.Forms.Button
    $primary.Text = "Close"; $primary.SetBounds(400, 186, 140, 30); $primary.Visible = $false
    $details.Add_Click({
        $log.Visible = -not $log.Visible
        $grow = if ($log.Visible) { 210 } else { -210 }
        $form.ClientSize = New-Object System.Drawing.Size(560, ($form.ClientSize.Height + $grow))
        $details.Top += $grow; $primary.Top += $grow
        $details.Text = if ($log.Visible) { "Hide details" } else { "Show details" }
    })
    $form.Controls.AddRange(@($heading, $message, $bar, $detail, $log, $details, $primary))
    $form.Add_FormClosing({ param($s, $e)
        if (-not $script:Finished) {
            $answer = [System.Windows.Forms.MessageBox]::Show("Champions is being set up. Stop now? The next start of Champions Setup goes on from where it was.", "Champions Setup", "YesNo", "Question")
            if ($answer -ne "Yes") { $e.Cancel = $true; return }
            $script:Cancelled = $true
            if ($script:Build -and -not $script:Build.HasExited) { try { & taskkill.exe /T /F /PID $script:Build.Id | Out-Null } catch { } }
        }
    })
    $script:Ui = @{ Form = $form; Message = $message; Bar = $bar; Detail = $detail; Log = $log; Primary = $primary }
    $form.Show()
    $form.Activate()
    Pump
}
$script:Finished = $false

function Finish-Window([string]$button, [scriptblock]$action) {
    $script:Finished = $true
    if ($Console) { return }
    $script:Ui.Primary.Text = $button
    $script:Ui.Primary.Visible = $true
    $script:Ui.Primary.Add_Click($action)
    while ($script:Ui.Form.Visible) { Pump; Start-Sleep -Milliseconds 60 }
}

# ---- the steps ----
function Native-Arch {
    $a = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" -ErrorAction SilentlyContinue).PROCESSOR_ARCHITECTURE
    if (-not $a) { $a = $env:PROCESSOR_ARCHITECTURE }
    if ($a -eq "ARM64") { return "aarch64" } else { return "x86_64" }
}

function Find-Disc {
    $places = @()
    foreach ($d in @("Downloads", "Desktop", "Documents")) { $places += (Join-Path $env:USERPROFILE $d) }
    if ($env:OneDrive) { $places += (Join-Path $env:OneDrive "Desktop"); $places += (Join-Path $env:OneDrive "Documents") }
    foreach ($drive in [System.IO.DriveInfo]::GetDrives()) {
        if ($drive.IsReady -and $drive.Name -ne ($env:SystemDrive + "\")) { $places += $drive.Name }
    }
    $seen = @{}
    foreach ($top in $places) {
        if (-not (Test-Path -LiteralPath $top -PathType Container)) { continue }
        Show "Looking for your disc image ..." 1 $top
        $files = @(Get-ChildItem -LiteralPath $top -Filter *.iso -File -Recurse -Depth 2 -Force -ErrorAction SilentlyContinue |
                   Where-Object { $_.Length -gt 1000000000 -and $_.Length -lt 9000000000 })
        foreach ($f in $files) {
            if ($seen.ContainsKey($f.FullName)) { continue }
            $seen[$f.FullName] = 1
            Pump
            if ([ChampionsDisc]::IsRight($f.FullName)) { return $f.FullName }
            Log "not the US v2.00 disc image: $($f.FullName)"
        }
    }
    return $null
}

function Pick-Disc {
    while ($true) {
        if ($Console) { $path = Read-Host "Path of your disc image (.iso)" }
        else {
            $dialog = New-Object System.Windows.Forms.OpenFileDialog
            $dialog.Title = "Your disc image of Champions: Return to Arms (.iso)"
            $dialog.Filter = "Disc images (*.iso)|*.iso|All files (*.*)|*.*"
            $dialog.InitialDirectory = Join-Path $env:USERPROFILE "Downloads"
            if ($dialog.ShowDialog($script:Ui.Form) -ne [System.Windows.Forms.DialogResult]::OK) { throw "No disc image was chosen." }
            $path = $dialog.FileName
        }
        if ($path -and (Test-Path -LiteralPath $path -PathType Leaf) -and [ChampionsDisc]::IsRight($path)) { return $path }
        Show "That file is not the US release, version 2.00, of Champions: Return to Arms (SLUS-20973). Choose another disc image." 1 $path
        if (-not $Console) { [System.Windows.Forms.MessageBox]::Show("That file is not the US release, version 2.00, of Champions: Return to Arms (SLUS-20973).", "Champions Setup") | Out-Null }
    }
}

function Fetch($what, $item, [string]$file, [int]$from, [int]$to) {
    if ((Test-Path -LiteralPath $file) -and (Get-Item -LiteralPath $file).Length -eq $item.Size -and
        (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash -eq $item.Sha.ToUpper()) { return }
    Log "downloading $($item.Url)"
    $job = [ChampionsJob]::Download($item.Url, $file + ".part")
    $mb = [Math]::Round($item.Size / 1MB)
    Wait-Job2 $job { Show "Getting the tools (downloads from the official sites, nothing is installed into Windows) ..." ($from + [int](($to - $from) * $job.Done / [Math]::Max(1, $item.Size))) ("$what  $([Math]::Round($job.Done / 1MB)) of $mb MB") }
    $got = (Get-Item -LiteralPath ($file + ".part")).Length
    if ($got -ne $item.Size) { throw "The download of $what is not complete ($got of $($item.Size) bytes); start Champions Setup again." }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath ($file + ".part")).Hash
    if ($hash -ne $item.Sha.ToUpper()) { throw "The download of $what is not the official file (SHA-256 $hash)." }
    Move-Item -Force -LiteralPath ($file + ".part") -Destination $file
    Log "$what`: $got bytes, SHA-256 $hash"
}

function Unpack($what, [string]$zip, [string]$folder, [int]$from, [int]$to) {
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $job = [ChampionsJob]::Unzip($zip, $folder)
    Wait-Job2 $job { Show "Unpacking $what ..." ($from + [int](($to - $from) * $job.Done / [Math]::Max(1, $job.Total))) "$($job.Done) of $($job.Total) files" }
}

function Make-Shortcut([string]$link, [string]$target, [string]$arguments, [string]$folder) {
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
    $s.TargetPath = $target; $s.Arguments = $arguments; $s.WorkingDirectory = $folder
    $s.Description = "Champions: Return to Arms, built from your own disc"
    $s.Save()
}

try {
    Show "You need your own disc image of Champions: Return to Arms (US, v2.00). Setup looks for it now and does the rest (15 to 45 minutes)." 0 ""
    $arch = Native-Arch
    Log "Windows $([Environment]::OSVersion.Version), processor $arch, folder $Base"
    $service = ""
    $ini = Join-Path $Payload "setup.ini"
    if (Test-Path -LiteralPath $ini) {
        foreach ($line in Get-Content -LiteralPath $ini) { if ($line -match '^\s*service\s*=\s*([^\s#]+)') { $service = $Matches[1] } }
    }

    # 1. the disc image
    if (-not $Disc) { $Disc = Find-Disc }
    if (-not $Disc) {
        Show "Setup did not find your disc image of Champions: Return to Arms (US, SLUS-20973, v2.00) in Downloads, Desktop, Documents or on another drive. Choose the .iso file." 1 ""
        $Disc = Pick-Disc
    } elseif (-not [ChampionsDisc]::IsRight($Disc)) { throw "Not the US v2.00 disc image: $Disc" }
    Log "disc image: $Disc"
    $drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($Base))
    if ($drive.AvailableFreeSpace -lt 5GB) { throw "Not enough free disk space on $($drive.Name): about 5 GB are needed." }

    # 2. the tools
    $py = $Python[$arch]; $ll = $Llvm[$arch]
    $pyDir = Join-Path $Tools "python-$PythonVersion-$arch"
    $pyExe = Join-Path $pyDir "python.exe"
    if (-not (Test-Path -LiteralPath $pyExe)) {
        $zip = Join-Path $Tools ([IO.Path]::GetFileName($py.Url))
        Fetch "Python $PythonVersion (python.org)" $py $zip 2 5
        Unpack "Python" $zip ($pyDir + ".part") 5 6
        Get-ChildItem -LiteralPath ($pyDir + ".part") -Filter "python*._pth" | Remove-Item -Force   # a normal Python: the script's own folder on its path
        if (Test-Path -LiteralPath $pyDir) { Remove-Item -Recurse -Force -LiteralPath $pyDir }
        Rename-Item -LiteralPath ($pyDir + ".part") -NewName ([IO.Path]::GetFileName($pyDir))
        Remove-Item -Force -LiteralPath $zip
    }
    $llDir = Join-Path $Tools "llvm-mingw-$LlvmTag-ucrt-$arch"
    $cxx = Join-Path $llDir "bin\x86_64-w64-mingw32-clang++.exe"
    if (-not (Test-Path -LiteralPath $cxx)) {
        $zip = Join-Path $Tools ([IO.Path]::GetFileName($ll.Url))
        Fetch "the compiler llvm-mingw $LlvmTag (github.com/mstorsjo/llvm-mingw)" $ll $zip 6 18
        $tmp = Join-Path $Tools "llvm.part"
        if (Test-Path -LiteralPath $tmp) { Remove-Item -Recurse -Force -LiteralPath $tmp }
        Unpack "the compiler" $zip $tmp 18 24
        if (Test-Path -LiteralPath $llDir) { Remove-Item -Recurse -Force -LiteralPath $llDir }
        Move-Item -LiteralPath (Join-Path $tmp "llvm-mingw-$LlvmTag-ucrt-$arch") -Destination $llDir
        Remove-Item -Recurse -Force -LiteralPath $tmp
        Remove-Item -Force -LiteralPath $zip
    }
    if (-not (Test-Path -LiteralPath $cxx)) { throw "The compiler is not where it should be: $cxx" }

    # 3. the source code and the build
    Unpack "the source code" (Join-Path $Payload "source.zip") $Work 24 25
    $desktop = Join-Path $env:USERPROFILE "Desktop"
    if (-not (Test-Path -LiteralPath $desktop)) { $desktop = [Environment]::GetFolderPath("Desktop") }
    $env:PATH = (Join-Path $llDir "bin") + ";" + $env:PATH
    $env:PYTHONIOENCODING = "utf-8"
    $q = { param($s) '"' + ($s -replace '"', '\"') + '"' }
    $arguments = @("-u", "-B", (& $q (Join-Path $Work "tools\install\fromdisc.py")), "--platform", "windows", "--disc", (& $q $Disc),
                   "--progress", "--desktop", (& $q $desktop), "--launcher-name", "Champions")
    if ($service) { $arguments += @("--service", $service) }
    $godotFrom = Join-Path $Payload "godot"
    $withGodot = (Test-Path -LiteralPath (Join-Path $godotFrom "RtaGodot.pck")) -and (Test-Path -LiteralPath (Join-Path $godotFrom "RtaGodot.exe"))
    if ($withGodot) { $arguments += @("--godot") }
    Log "the Godot version: $(if ($withGodot) { 'in this setup' } else { 'not in this setup' })"
    $out = Join-Path $Base "build-output.txt"
    Show "Building Champions from your disc image: 10 to 40 minutes; you can keep using the PC." 25 "Starting"
    $script:Build = Start-Process -FilePath $pyExe -ArgumentList $arguments -WorkingDirectory $Work -RedirectStandardOutput $out `
                                  -RedirectStandardError (Join-Path $Base "build-errors.txt") -WindowStyle Hidden -PassThru
    $null = $script:Build.Handle      # keeps the process handle: without it Windows PowerShell 5.1 forgets the exit code
    $reader = $null
    while ($true) {
        if (-not $reader -and (Test-Path -LiteralPath $out)) {
            $reader = New-Object System.IO.StreamReader([System.IO.FileStream]::new($out, "Open", "Read", "ReadWrite"))
        }
        $exited = $script:Build.HasExited
        if ($reader) {
            while ($null -ne ($line = $reader.ReadLine())) {
                if ($line -match '^@progress (\d+) (.*)$') {
                    Show "Building Champions from your disc image: 10 to 40 minutes; you can keep using the PC." (25 + [int]([int]$Matches[1] * 0.73)) $Matches[2]
                } else { Log $line }
            }
        }
        if ($exited) { break }
        if ($script:Cancelled) { throw "Setup was stopped." }
        Pump; Start-Sleep -Milliseconds 150
    }
    if ($reader) { $reader.Close() }
    $script:Build.WaitForExit()
    $errors = Join-Path $Base "build-errors.txt"
    if ((Test-Path -LiteralPath $errors) -and (Get-Item -LiteralPath $errors).Length -gt 0) { Get-Content -LiteralPath $errors | ForEach-Object { Log $_ } }
    if ($script:Build.ExitCode -ne 0) { throw "The build did not finish (exit code $($script:Build.ExitCode)); the details are in $LogFile" }

    # 4. the shortcuts and the start
    $program = Join-Path $Work "local\recomp-out\win\rta-windows\rta_app.exe"
    if (-not (Test-Path -LiteralPath $program)) { throw "The program was not made: $program" }
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
    $arg = '--disc "' + $Disc + '"'
    Make-Shortcut (Join-Path $startMenu "Champions.lnk") $program $arg (Split-Path $program)
    if (-not (Test-Path -LiteralPath (Join-Path $desktop "Champions.lnk"))) { Make-Shortcut (Join-Path $desktop "Champions.lnk") $program $arg (Split-Path $program) }
    Log "shortcuts: $(Join-Path $desktop 'Champions.lnk'), $(Join-Path $startMenu 'Champions.lnk')"
    # the Godot version: its game library was built by fromdisc.py --godot; the application itself comes from the payload
    # (local\install.txt names it when this build made it: a library of an earlier setup does not count)
    $godotLibrary = ""
    $installTxt = Join-Path $Work "local\install.txt"
    if (Test-Path -LiteralPath $installTxt) {
        foreach ($line in Get-Content -LiteralPath $installTxt) { if ($line -match '^godot_library=(.+)$') { $godotLibrary = $Matches[1].Trim() } }
    }
    $godotMade = $withGodot -and $godotLibrary -and (Test-Path -LiteralPath $godotLibrary)
    if ($godotMade) {
        Show "Putting the Godot version in place ..." 99 ""
        $godotDir = Join-Path $Base "godot"
        if (Test-Path -LiteralPath $godotDir) { Remove-Item -Recurse -Force -LiteralPath $godotDir }
        New-Item -ItemType Directory -Force -Path $godotDir | Out-Null
        Get-ChildItem -LiteralPath $godotFrom -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $godotDir -Force }
        $godotExe = Join-Path $godotDir "RtaGodot.exe"
        $godotArg = '-- --disc "' + $Disc + '"'
        Make-Shortcut (Join-Path $startMenu "Champions Godot.lnk") $godotExe $godotArg $godotDir
        if (-not (Test-Path -LiteralPath (Join-Path $desktop "Champions Godot.lnk"))) { Make-Shortcut (Join-Path $desktop "Champions Godot.lnk") $godotExe $godotArg $godotDir }
        Log "the Godot version: $godotExe (game library $godotLibrary); shortcuts: Champions Godot"
    } elseif ($withGodot) {
        Log "the Godot version is left out: its game library was not built (the lines above say why); Champions itself is ready"
    }
    $ready = if ($godotMade) { "Champions and Champions Godot are ready: on your desktop and in the Start menu. Starting Champions now." } else { "Champions is ready: on your desktop and in the Start menu. Starting it now." }
    Show $ready 100 "Done"
    Log "@done $program"
    if (-not $NoStart) { Start-Process -FilePath $program -ArgumentList $arg -WorkingDirectory (Split-Path $program) }
    Finish-Window "Close" { $script:Ui.Form.Close() }
    exit 0
} catch {
    $text = $_.Exception.Message
    Log "@error $text"
    if ($script:Cancelled) { exit 1 }
    Show "Setup did not finish: $text" -1 "The details: Show details, or $LogFile"
    if (-not $Console -and -not $script:Ui.Log.Visible) { $details.PerformClick() }
    Finish-Window "Close" { $script:Ui.Form.Close() }
    exit 1
}
