/* stub.c - the program part of "Champions Setup.exe".
 *
 * The .exe is this small program with a zip archive appended to it (tools/install/setup/build_setups.py): our source
 * code, setup-windows.ps1 and, from whoever hands out the setup, setup.ini.  Nothing of the game is in it.
 * The program copies the archive to %LOCALAPPDATA%\Champions\Setup\payload.zip and starts Windows PowerShell (part of
 * Windows 10 and 11) without a console window: it unpacks the archive there and runs setup-windows.ps1, which shows the
 * setup's own window.  Command-line arguments are handed on to setup-windows.ps1 (e.g. -Disc FILE, -Console).
 *
 * The end of the file:  ... zip archive ... | "CHSETUP1" | archive size, 8 bytes little-endian
 * Built with MinGW-w64 (x86-64; runs on Windows on ARM under Windows' own emulation).
 */
#define WIN32_LEAN_AND_MEAN
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shlobj.h>
#include <stdint.h>

static void complain(const wchar_t* text) {
    MessageBoxW(NULL, text, L"Champions Setup", MB_OK | MB_ICONERROR);
}

static wchar_t* append(wchar_t* to, const wchar_t* text) {
    while (*text) *to++ = *text++;
    *to = 0;
    return to;
}

/* text with every ' doubled, for a PowerShell string in single quotes */
static wchar_t* append_quoted(wchar_t* to, const wchar_t* text) {
    *to++ = L'\'';
    for (; *text; text++) {
        if (*text == L'\'') *to++ = L'\'';
        *to++ = *text;
    }
    *to++ = L'\'';
    *to = 0;
    return to;
}

static const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR arguments, int show) {
    (void)instance; (void)previous; (void)show;
    static wchar_t self[32768], folder[32768], zip[32768], script[65536], command[200000];
    if (!GetModuleFileNameW(NULL, self, 32768)) { complain(L"Cannot find this program's own file."); return 1; }

    HANDLE in = CreateFileW(self, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (in == INVALID_HANDLE_VALUE) { complain(L"Cannot read this program's own file."); return 1; }
    LARGE_INTEGER size, at;
    GetFileSizeEx(in, &size);
    unsigned char tail[16];
    DWORD got = 0;
    at.QuadPart = size.QuadPart - 16;
    if (size.QuadPart < 16 || !SetFilePointerEx(in, at, NULL, FILE_BEGIN) || !ReadFile(in, tail, 16, &got, NULL) || got != 16 ||
        memcmp(tail, "CHSETUP1", 8) != 0) {
        CloseHandle(in);
        complain(L"This copy of Champions Setup is damaged (its archive is missing). Download it again.");
        return 1;
    }
    uint64_t length = 0;
    for (int i = 7; i >= 0; i--) length = length << 8 | tail[8 + i];
    if (length == 0 || (int64_t)length > size.QuadPart - 16) { CloseHandle(in); complain(L"This copy of Champions Setup is damaged."); return 1; }

    /* %LOCALAPPDATA%\Champions\Setup */
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", folder, 32000);
    if (!n || n >= 32000) {
        PWSTR known = NULL;
        if (SHGetKnownFolderPath(&FOLDERID_LocalAppData, 0, NULL, &known) != S_OK) { CloseHandle(in); complain(L"No folder for the setup's files."); return 1; }
        lstrcpynW(folder, known, 32000);
        CoTaskMemFree(known);
    }
    lstrcatW(folder, L"\\Champions");
    CreateDirectoryW(folder, NULL);
    lstrcatW(folder, L"\\Setup");
    CreateDirectoryW(folder, NULL);
    lstrcpyW(zip, folder);
    lstrcatW(zip, L"\\payload.zip");

    HANDLE out = CreateFileW(zip, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (out == INVALID_HANDLE_VALUE) { CloseHandle(in); complain(L"Cannot write the setup's files into %LOCALAPPDATA%\\Champions\\Setup."); return 1; }
    at.QuadPart = size.QuadPart - 16 - (int64_t)length;
    SetFilePointerEx(in, at, NULL, FILE_BEGIN);
    static unsigned char buffer[1 << 16];
    uint64_t left = length;
    while (left) {
        DWORD want = left > sizeof buffer ? sizeof buffer : (DWORD)left, wrote = 0;
        if (!ReadFile(in, buffer, want, &got, NULL) || got == 0 || !WriteFile(out, buffer, got, &wrote, NULL) || wrote != got) {
            CloseHandle(in); CloseHandle(out);
            complain(L"Cannot copy the setup's files (is the disk full?).");
            return 1;
        }
        left -= got;
    }
    CloseHandle(out);
    CloseHandle(in);

    /* the PowerShell script that unpacks the archive and starts setup-windows.ps1 */
    wchar_t* p = script;
    p = append(p, L"$ErrorActionPreference = 'Stop'; $d = ");
    p = append_quoted(p, folder);
    p = append(p, L"; try { Add-Type -AssemblyName System.IO.Compression.FileSystem; "
                  L"$z = [IO.Compression.ZipFile]::OpenRead((Join-Path $d 'payload.zip')); "
                  L"foreach ($e in $z.Entries) { $t = Join-Path $d $e.FullName; "
                  L"if ($e.FullName.EndsWith('/')) { [void][IO.Directory]::CreateDirectory($t) } else { "
                  L"[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($t)); "
                  L"[IO.Compression.ZipFileExtensions]::ExtractToFile($e, $t, $true) } }; $z.Dispose(); "
                  L"& (Join-Path $d 'setup-windows.ps1') -Payload $d ");
    if (arguments && *arguments) p = append(p, arguments);
    p = append(p, L"; exit $LASTEXITCODE } catch { Add-Type -AssemblyName System.Windows.Forms; "
                  L"[void][Windows.Forms.MessageBox]::Show('Champions Setup could not start: ' + $_.Exception.Message, 'Champions Setup'); exit 1 }");

    /* -EncodedCommand: the script as UTF-16LE in base64, so that no path needs quoting on the command line */
    wchar_t* c = command;
    wchar_t system[MAX_PATH];
    GetSystemDirectoryW(system, MAX_PATH);
    c = append(c, L"\"");
    c = append(c, system);
    c = append(c, L"\\WindowsPowerShell\\v1.0\\powershell.exe\" -NoProfile -ExecutionPolicy Bypass -STA -EncodedCommand ");
    const unsigned char* bytes = (const unsigned char*)script;
    size_t count = (size_t)(p - script) * 2;
    for (size_t i = 0; i < count; i += 3) {
        uint32_t v = (uint32_t)bytes[i] << 16 | (i + 1 < count ? (uint32_t)bytes[i + 1] << 8 : 0) | (i + 2 < count ? bytes[i + 2] : 0);
        *c++ = B64[v >> 18 & 63];
        *c++ = B64[v >> 12 & 63];
        *c++ = i + 1 < count ? B64[v >> 6 & 63] : L'=';
        *c++ = i + 2 < count ? B64[v & 63] : L'=';
    }
    *c = 0;

    int console = arguments && (wcsstr(arguments, L"-Console") || wcsstr(arguments, L"-console"));
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof si);
    si.cb = sizeof si;
    if (!CreateProcessW(NULL, command, NULL, NULL, FALSE, console ? CREATE_NEW_CONSOLE : CREATE_NO_WINDOW, NULL, folder, &si, &pi)) {
        complain(L"Cannot start Windows PowerShell, which the setup needs (it is part of Windows 10 and 11).");
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return (int)code;
}
