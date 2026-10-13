// online_win.cpp - the one-step online's questions and notes in the Windows program: the
// counterpart of online_mac.mm, in plain Win32.
//
// Linked into rta_app.exe beside net/online.cpp.  It puts on the game's window the three
// things a person has to see or answer:
//
//   - the player name, asked once: a small dialogue with one text field, "Play online" and
//     "Not now".  The name is checked by the same rule as everywhere; a name that does not
//     fit leaves the dialogue open with the reason above the field.  The password is not
//     the player's business and appears nowhere.
//   - the note of the one-step driver (where it is, the code of a hosted game) and the
//     server, in the window's title after the program's own;
//   - the warning that another player's copy has another patch set (or other arithmetic):
//     a box with the text and OK.
//
// The driver calls from the game's thread; a window belongs to the thread that made it.
// So each call posts a message to the game's window (app/win_main.cpp hands every message
// from WM_APP on to onlinewin::window_message), and the dialogue is made there.  It is
// modeless - the window's loop goes on, the game keeps running and being drawn behind it,
// as behind the sheet on macOS: the lobby server drops a client it has not heard from for
// two minutes.  The loop offers every message to onlinewin::dialog_message first (Tab,
// Enter and Escape in the dialogue).
//
// A test window ("AGENT TEST - ...", or one that is never shown) is left alone: nobody is
// there to answer, its title stays, and the name comes from --opt online-name.  Without a
// window the name is asked on the console, as net/online.cpp does by itself.
//
// Also here: the two file calls net/posix_win.h gives RtaOnline.cpp (the saved login).
//
// Written and compiled on a Mac with a cross-compiler and read; NOT RUN
// (docs/issues/native-windows.md).
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <aclapi.h>
#include <io.h>

#include "netdrv.h"
#include "online_win.h"

#include <cstdio>
#include <string>
#include <vector>

namespace {

enum { MSG_ASK = WM_APP + 0x61, MSG_NOTE, MSG_WARNING };
enum { ID_TEXT = 100, ID_NAME = 101 };

HWND g_window = nullptr;                // the game's window; null: none, or a test's
std::wstring g_base_title;
std::vector<HWND> g_dialogs;            // open ones, for the loop (window thread only)

std::wstring wide(const std::string& text, UINT code_page = CP_UTF8) {
    int n = MultiByteToWideChar(code_page, 0, text.c_str(), (int)text.size(), nullptr, 0);
    std::wstring out((size_t)(n > 0 ? n : 0), L'\0');
    if (n > 0) MultiByteToWideChar(code_page, 0, text.c_str(), (int)text.size(), &out[0], n);
    return out;
}

const wchar_t* EXPLAIN = L"Choose the name other players will see: 3 to 15 letters and digits. You are asked only once: the program "
                         L"makes your account on the lobby server and logs in by itself from then on.";

// ---- a dialogue made in memory (no resource file) ------------------------------------------
// DLGTEMPLATE, then for every control a DLGITEMTEMPLATE on a 4-byte boundary; sizes are in
// dialogue units (a quarter of the font's average character wide, an eighth of its height high).
struct Template {
    std::vector<WORD> words;
    void word(WORD w) { words.push_back(w); }
    void dword(DWORD d) { words.push_back((WORD)(d & 0xFFFF)); words.push_back((WORD)(d >> 16)); }
    void text(const wchar_t* t) { for (; *t; t++) words.push_back((WORD)*t); words.push_back(0); }
    void align() { if (words.size() & 1) words.push_back(0); }
    void head(const wchar_t* title, short width, short height) {
        dword(WS_POPUP | WS_CAPTION | WS_SYSMENU | DS_MODALFRAME | DS_SETFONT);
        dword(0);                       // extended style
        word(0);                        // number of controls: counted in item()
        word(0); word(0); word((WORD)width); word((WORD)height);
        word(0);                        // no menu
        word(0);                        // the dialogue's own window class
        text(title);
        word(9); text(L"Segoe UI");     // DS_SETFONT: point size, face
    }
    // atoms of the built-in classes: 0x0080 button, 0x0081 edit, 0x0082 static
    void item(WORD atom, DWORD style, short x, short y, short width, short height, WORD id, const wchar_t* title) {
        align();
        dword(style | WS_CHILD | WS_VISIBLE);
        dword(0);
        word((WORD)x); word((WORD)y); word((WORD)width); word((WORD)height);
        word(id);
        word(0xFFFF); word(atom);
        text(title);
        word(0);                        // no creation data
        words[4]++;                     // cdit of the head (after the two style words)
    }
};

struct Box {
    bool ask = false;                   // the name question; otherwise a text with OK
    std::wstring text;
};

void forget(HWND dialog) {
    for (size_t k = 0; k < g_dialogs.size(); k++)
        if (g_dialogs[k] == dialog) { g_dialogs.erase(g_dialogs.begin() + (long)k); break; }
}

INT_PTR CALLBACK box_proc(HWND dialog, UINT message, WPARAM wp, LPARAM lp) {
    Box* box = (Box*)GetWindowLongPtrW(dialog, GWLP_USERDATA);
    switch (message) {
    case WM_INITDIALOG: {
        box = (Box*)lp;
        SetWindowLongPtrW(dialog, GWLP_USERDATA, (LONG_PTR)box);
        SetDlgItemTextW(dialog, ID_TEXT, box->text.c_str());
        if (box->ask) SendDlgItemMessageW(dialog, ID_NAME, EM_SETLIMITTEXT, 15, 0);
        // over the middle of the game's window
        RECT owner, own;
        if (g_window && GetWindowRect(g_window, &owner) && GetWindowRect(dialog, &own))
            SetWindowPos(dialog, nullptr, owner.left + ((owner.right - owner.left) - (own.right - own.left)) / 2,
                         owner.top + ((owner.bottom - owner.top) - (own.bottom - own.top)) / 2, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
        if (box->ask) { SetFocus(GetDlgItem(dialog, ID_NAME)); return FALSE; }      // FALSE: the focus was set here
        return TRUE;
    }
    case WM_COMMAND:
        if (!box) return FALSE;
        if (LOWORD(wp) == IDOK && box->ask) {
            wchar_t typed[64] = L"";
            GetDlgItemTextW(dialog, ID_NAME, typed, 64);
            std::string name;
            for (const wchar_t* p = typed; *p; p++) name += (*p < 128) ? (char)*p : '?';     // the rule allows letters and digits only
            std::string wrong = rtanet::check_name(name);
            if (!wrong.empty()) {       // stays open, with the reason
                SetDlgItemTextW(dialog, ID_TEXT, (wide(wrong) + L"\r\n\r\n" + EXPLAIN).c_str());
                SetFocus(GetDlgItem(dialog, ID_NAME));
                SendDlgItemMessageW(dialog, ID_NAME, EM_SETSEL, 0, -1);
                return TRUE;
            }
            rtanet::give_name(name);
            box->ask = false;           // answered: closing no longer declines
            DestroyWindow(dialog);
            return TRUE;
        }
        if (LOWORD(wp) == IDOK || LOWORD(wp) == IDCANCEL) {
            if (box->ask) rtanet::decline_name();
            box->ask = false;
            DestroyWindow(dialog);
            return TRUE;
        }
        return FALSE;
    case WM_CLOSE:
        if (box && box->ask) rtanet::decline_name();
        if (box) box->ask = false;
        DestroyWindow(dialog);
        return TRUE;
    case WM_NCDESTROY:
        forget(dialog);
        SetWindowLongPtrW(dialog, GWLP_USERDATA, 0);
        delete box;
        return FALSE;
    default:
        return FALSE;
    }
}

// window thread
void open_box(bool ask, const wchar_t* title, const std::wstring& text) {
    Template t;
    if (ask) {
        // the text: the reason a name did not fit (two lines at most), an empty line, the explanation (four)
        t.head(title, 220, 122);
        t.item(0x0082, SS_LEFT, 7, 7, 206, 66, ID_TEXT, L"");
        t.item(0x0081, WS_BORDER | WS_TABSTOP | ES_AUTOHSCROLL, 7, 78, 206, 14, ID_NAME, L"");
        t.item(0x0080, WS_TABSTOP | BS_DEFPUSHBUTTON, 92, 101, 62, 14, IDOK, L"Play online");
        t.item(0x0080, WS_TABSTOP | BS_PUSHBUTTON, 159, 101, 54, 14, IDCANCEL, L"Not now");
    } else {
        t.head(title, 220, 94);
        t.item(0x0082, SS_LEFT, 7, 7, 206, 60, ID_TEXT, L"");
        t.item(0x0080, WS_TABSTOP | BS_DEFPUSHBUTTON, 163, 73, 50, 14, IDOK, L"OK");
    }
    t.align();
    Box* box = new Box;
    box->ask = ask;
    box->text = text;
    HWND dialog = CreateDialogIndirectParamW(GetModuleHandleW(nullptr), (LPCDLGTEMPLATEW)t.words.data(), g_window, box_proc, (LPARAM)box);
    if (!dialog) {
        // no dialogue: the question goes to the console, a warning stays in the log
        delete box;
        if (ask) rtanet::ask_name_on_terminal("");
        return;
    }
    g_dialogs.push_back(dialog);
    ShowWindow(dialog, SW_SHOW);
}

// game's thread: hand a text to the window's thread
bool post(UINT message, const std::string& text) {
    if (!g_window) return false;
    std::wstring* copy = new std::wstring(wide(text));
    if (PostMessageW(g_window, message, 0, (LPARAM)copy)) return true;
    delete copy;
    return false;
}

void ask(const std::string& why) {
    if (!g_window) {
        if (onlinewin::quiet()) rtanet::say("online: a test window - the name comes from --opt online-name");
        else rtanet::ask_name_on_terminal(why);
        return;
    }
    if (!post(MSG_ASK, why)) rtanet::ask_name_on_terminal(why);
}
void note(const std::string& text) { post(MSG_NOTE, text); }
void code(const std::string& text) {
    printf("Your game's code: %s - friends choose Join and give this code.\n", text.c_str());
    fflush(stdout);
}
void warning(const std::string& text) { post(MSG_WARNING, text); }

bool g_quiet = false;

struct Install {
    Install() {
        rtanet::ask_name = ask;
        rtanet::show_note = note;
        rtanet::show_code = code;
        rtanet::show_warning = warning;
    }
} g_install;

}  // namespace

namespace onlinewin {

bool quiet() { return g_quiet; }

void attach(void* window, bool test) {
    g_quiet = test;
    g_window = test ? nullptr : (HWND)window;
    if (g_window) {
        wchar_t title[512] = L"";
        GetWindowTextW(g_window, title, 512);
        g_base_title = title;
    }
}

bool window_message(void* window, unsigned message, uintptr_t, intptr_t lp) {
    if (message != MSG_ASK && message != MSG_NOTE && message != MSG_WARNING) return false;
    std::wstring* text = (std::wstring*)lp;
    if (!text) return true;
    if ((HWND)window == g_window) {
        if (message == MSG_ASK) {
            open_box(true, L"Your player name", text->empty() ? std::wstring(EXPLAIN) : *text + L"\r\n\r\n" + EXPLAIN);
        } else if (message == MSG_WARNING) {
            open_box(false, L"The players' games differ", *text);
        } else {
            std::wstring title = g_base_title + L" - server " + wide(rtanet::info().server_text);
            if (!text->empty()) title += L" - " + *text;
            SetWindowTextW(g_window, title.c_str());
        }
    }
    delete text;
    return true;
}

bool dialog_message(void* msg) {
    if (g_dialogs.empty()) return false;
    std::vector<HWND> open = g_dialogs;     // a dialogue that closes on this message takes itself out of the list
    for (HWND dialog : open)
        if (IsWindow(dialog) && IsDialogMessageW(dialog, (MSG*)msg)) return true;
    return false;
}

}  // namespace onlinewin

// ---- the saved login's file (net/posix_win.h) ---------------------------------------------------
// fchmod(fd, 0600) of RtaOnline.cpp: the file - just made, still empty - gets an access list
// with one entry, full access for the user the program runs as, and no longer inherits its
// folder's.  A handle with the right to change the list is opened beside the one the C
// library holds (the owner of a file always may).  When any step fails the file keeps the
// access its folder gives it and is saved all the same.
int rta_win_private_file(int fd) {
    HANDLE file = (HANDLE)_get_osfhandle(fd);
    if (file == INVALID_HANDLE_VALUE) return 0;
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 0;
    unsigned char user_bytes[sizeof(TOKEN_USER) + SECURITY_MAX_SID_SIZE];
    DWORD size = 0;
    BOOL have = GetTokenInformation(token, TokenUser, user_bytes, sizeof user_bytes, &size);
    CloseHandle(token);
    if (!have) return 0;
    PSID user = ((TOKEN_USER*)user_bytes)->User.Sid;
    unsigned char acl_bytes[sizeof(ACL) + sizeof(ACCESS_ALLOWED_ACE) + SECURITY_MAX_SID_SIZE];
    PACL acl = (PACL)acl_bytes;
    if (!InitializeAcl(acl, sizeof acl_bytes, ACL_REVISION) || !AddAccessAllowedAce(acl, ACL_REVISION, FILE_ALL_ACCESS, user)) return 0;
    HANDLE again = ReOpenFile(file, WRITE_DAC | READ_CONTROL, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, 0);
    if (again == INVALID_HANDLE_VALUE) return 0;
    SetSecurityInfo(again, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION, nullptr, nullptr, acl, nullptr);
    CloseHandle(again);
    return 0;
}

// rename(from, to) of RtaOnline.cpp: the new file takes the old one's place in one step
int rta_win_replace_file(const char* from, const char* to) {
    // file names are in the process code page, like every name the C library is given
    std::wstring a = wide(from, CP_ACP), b = wide(to, CP_ACP);
    return MoveFileExW(a.c_str(), b.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) ? 0 : -1;
}
#endif  // _WIN32
