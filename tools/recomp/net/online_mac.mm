// online_mac.mm - the one-step online's questions and notes in a window program (macOS).
//
// Linked into rta_app beside net/online.cpp.  It takes the three things a person has to
// see or answer and puts them on the game's window, without touching the window program:
//
//   - the player name, asked once (a sheet on the window with one text field; the name is
//     checked by the same rule as everywhere and asked again with the reason when it does
//     not fit).  The password is not the player's business and appears nowhere.
//   - the note of the one-step driver (where it is, the code of a hosted game) and the
//     server, in the window's title after the program's own;
//   - the warning that another player's copy has another patch set (a sheet).
//
// A test window ("AGENT TEST - ...") is left alone: nobody is there to answer, its title
// stays as it is, and the name comes from --opt online-name.  A program without a window
// (no running NSApplication) asks on the terminal, as net/online.cpp does by itself.
#import <AppKit/AppKit.h>

#include "netdrv.h"

#include <string>

namespace {

NSString* g_base_title = nil;

NSWindow* game_window() {
    if (NSApp == nil) return nil;
    for (NSWindow* window in [NSApp windows])
        if ([window isVisible] && ![window isKindOfClass:[NSPanel class]]) return window;
    return nil;
}
bool test_window(NSWindow* window) { return window == nil || [[window title] hasPrefix:@"AGENT TEST"]; }
NSString* text_of(const std::string& text) { return [NSString stringWithUTF8String:text.c_str()] ?: @""; }

void ask_on_window(const std::string& why);

void ask(const std::string& why) {
    if (NSApp == nil || ![NSApp isRunning]) { rtanet::ask_name_on_terminal(why); return; }
    std::string reason = why;
    dispatch_async(dispatch_get_main_queue(), ^{ ask_on_window(reason); });
}

void ask_on_window(const std::string& why) {
    NSWindow* window = game_window();
    if (test_window(window)) {
        rtanet::say("online: a test window - the name comes from --opt online-name");
        return;
    }
    NSAlert* alert = [[NSAlert alloc] init];
    alert.messageText = @"Your player name";
    NSString* explain = @"Choose the name other players will see: 3 to 15 letters and digits. You are asked only once: the application "
                        @"makes your account on the lobby server and logs in by itself from then on.";
    alert.informativeText = why.empty() ? explain : [NSString stringWithFormat:@"%@\n\n%@", text_of(why), explain];
    NSTextField* field = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 0, 260, 24)];
    field.placeholderString = @"Name";
    alert.accessoryView = field;
    [alert addButtonWithTitle:@"Play online"];
    [alert addButtonWithTitle:@"Not now"];
    [alert.window setInitialFirstResponder:field];
    [alert beginSheetModalForWindow:window completionHandler:^(NSModalResponse response) {
        if (response != NSAlertFirstButtonReturn) { rtanet::decline_name(); return; }
        std::string name = [[field stringValue] UTF8String] ?: "";
        std::string wrong = rtanet::check_name(name);
        if (wrong.empty()) rtanet::give_name(name);
        else dispatch_async(dispatch_get_main_queue(), ^{ ask_on_window(wrong); });
    }];
}

void note(const std::string& text) {
    if (NSApp == nil || ![NSApp isRunning]) return;
    std::string copy = text;
    dispatch_async(dispatch_get_main_queue(), ^{
        NSWindow* window = game_window();
        if (test_window(window)) return;
        if (g_base_title == nil) g_base_title = [[window title] copy];
        NSString* server = text_of("server " + rtanet::info().server_text);
        window.title = copy.empty() ? [NSString stringWithFormat:@"%@ - %@", g_base_title, server]
                                    : [NSString stringWithFormat:@"%@ - %@ - %@", g_base_title, server, text_of(copy)];
    });
}

void code(const std::string& text) {
    printf("Your game's code: %s - friends choose Join and give this code.\n", text.c_str());
    fflush(stdout);
}

void warning(const std::string& text) {
    if (NSApp == nil || ![NSApp isRunning]) return;
    std::string copy = text;
    dispatch_async(dispatch_get_main_queue(), ^{
        NSWindow* window = game_window();
        if (test_window(window)) return;
        NSAlert* alert = [[NSAlert alloc] init];
        alert.alertStyle = NSAlertStyleWarning;
        alert.messageText = @"The players' games differ";
        alert.informativeText = text_of(copy);
        [alert addButtonWithTitle:@"OK"];
        [alert beginSheetModalForWindow:window completionHandler:^(NSModalResponse) {}];
    });
}

struct Install {
    Install() {
        rtanet::ask_name = ask;
        rtanet::show_note = note;
        rtanet::show_code = code;
        rtanet::show_warning = warning;
    }
} g_install;

}  // namespace
