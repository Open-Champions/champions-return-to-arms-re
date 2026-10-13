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
//   - the warning that another player's copy has another patch set (a sheet);
//   - the way to go online at all, for a person who started the program without options:
//     an "Online" menu in the menu bar - Go Online (the lobby's list of games), Host a Game
//     (a code is made up and shown in the window's title), Join a Game with a Code...
//     (asked for in a sheet), Stop Going Online - with the server it goes to in its first
//     line.  Each is the script's `app online start ...` line, handed to the game's thread
//     (rtanet::request).
//
// A test window ("AGENT TEST - ...") is left alone: nobody is there to answer, its title
// stays as it is, and the name comes from --opt online-name.  A program without a window
// (no running NSApplication) asks on the terminal, as net/online.cpp does by itself.
//
// Tests: with --opt online-test-window=1 the question, the note and the warnings are shown
// on a test window as on any other (the title keeps its "AGENT TEST" head), and the script
// command `app online sheet ...` (net/online.cpp; also through --opt online-commands=FILE)
// reads and works the sheet without a screen: `info` prints what is up (the sheet, its
// texts, its field, its buttons, the window's title), `type TEXT` puts text in the field,
// `press N` clicks button N (0 "Play online", 1 "Not now") - the button's own action, so
// the sheet ends and its handler runs exactly as after a click - and `picture FILE.png`
// has the sheet draw itself into a file.
#import <AppKit/AppKit.h>

#include "netdrv.h"

#include <string>

namespace {

NSString* g_base_title = nil;
NSAlert* g_sheet = nil;             // the question or warning that is up, for `app online sheet`
NSTextField* g_sheet_field = nil;
bool show_on_test_window() {
    const char* value = rtanet::option("online-test-window");
    return value && std::string(value) == "1";
}

NSWindow* game_window() {
    if (NSApp == nil) return nil;
    for (NSWindow* window in [NSApp windows])
        if ([window isVisible] && ![window isKindOfClass:[NSPanel class]]) return window;
    return nil;
}
bool test_window(NSWindow* window) { return window == nil || ([[window title] hasPrefix:@"AGENT TEST"] && !show_on_test_window()); }
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
    g_sheet = alert;
    g_sheet_field = field;
    [alert beginSheetModalForWindow:window completionHandler:^(NSModalResponse response) {
        g_sheet = nil;
        g_sheet_field = nil;
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
        if (g_sheet != nil) return;         // one sheet at a time: the name question, or an earlier warning, is up
        g_sheet = alert;
        [alert beginSheetModalForWindow:window completionHandler:^(NSModalResponse) { g_sheet = nil; }];
    });
}

NSMenu* g_menu = nil;
void menu_test(const std::string& rest);

// tests: the sheet read and worked without a screen (the head of this file)
void sheet_test(const std::string& given) {
    if (NSApp == nil || ![NSApp isRunning]) { rtanet::say("sheet: no window program is running"); return; }
    std::string text = given;
    while (!text.empty() && text[0] == ' ') text.erase(0, 1);
    dispatch_async(dispatch_get_main_queue(), ^{
        std::string verb = text.substr(0, text.find(' '));
        std::string rest = text.find(' ') == std::string::npos ? "" : text.substr(text.find(' ') + 1);
        if (verb == "menu") { menu_test(rest); return; }
        NSWindow* window = game_window();
        NSWindow* attached = window ? [window attachedSheet] : nil;
        if (verb == "info" || verb.empty()) {
            std::string buttons;
            if (g_sheet) for (NSButton* button in [g_sheet buttons]) buttons += std::string(buttons.empty() ? "" : "|") + ([[button title] UTF8String] ?: "");
            rtanet::say("sheet: up=%d attached=%d visible=%d on-screen-window=%d message=\"%s\" informative-length=%lu field=\"%s\" buttons=\"%s\" window-title=\"%s\" reason=\"%s\"",
                        g_sheet != nil, attached != nil && g_sheet != nil && attached == [g_sheet window], attached != nil && [attached isVisible],
                        window != nil && [window isVisible] && ([window occlusionState] & NSWindowOcclusionStateVisible) != 0,
                        g_sheet ? ([[g_sheet messageText] UTF8String] ?: "") : "", g_sheet ? (unsigned long)[[g_sheet informativeText] length] : 0ul,
                        g_sheet_field ? ([[g_sheet_field stringValue] UTF8String] ?: "") : "", buttons.c_str(), window ? ([[window title] UTF8String] ?: "") : "",
                        // the first line of the informative text when the question came back with a reason
                        g_sheet ? ([[[[g_sheet informativeText] componentsSeparatedByString:@"\n"] firstObject] UTF8String] ?: "") : "");
        } else if (verb == "type") {
            if (!g_sheet_field) { rtanet::say("sheet: no question with a field is up"); return; }
            [g_sheet_field setStringValue:text_of(rest)];
            rtanet::say("sheet: %lu characters put in the field", (unsigned long)[[g_sheet_field stringValue] length]);
        } else if (verb == "press") {
            NSArray<NSButton*>* buttons = g_sheet ? [g_sheet buttons] : nil;
            NSUInteger index = (NSUInteger)atoi(rest.c_str());
            if (!buttons || index >= [buttons count]) { rtanet::say("sheet: no such button"); return; }
            rtanet::say("sheet: button %lu \"%s\" clicked", (unsigned long)index, [[buttons[index] title] UTF8String] ?: "");
            [buttons[index] performClick:nil];
        } else if (verb == "picture") {
            NSView* view = attached ? [attached contentView] : nil;
            if (!view) { rtanet::say("sheet: nothing is attached to the window"); return; }
            NSBitmapImageRep* rep = [view bitmapImageRepForCachingDisplayInRect:[view bounds]];
            [view cacheDisplayInRect:[view bounds] toBitmapImageRep:rep];
            NSData* png = [rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
            bool ok = [png writeToFile:text_of(rest) atomically:YES];
            rtanet::say("sheet: its picture (%ld x %ld) %s", (long)[rep pixelsWide], (long)[rep pixelsHigh], ok ? "written" : "could NOT be written");
        } else rtanet::say("sheet: info, type TEXT, press N or picture FILE");
    });
}

// The code of a friend's game, asked for on the window; `wrong`: why it is asked again.
void ask_code(const std::string& wrong) {
    NSWindow* window = game_window();
    if (window == nil || g_sheet != nil) return;
    NSAlert* alert = [[NSAlert alloc] init];
    alert.messageText = @"Join a game with a code";
    NSString* explain = @"Type the code your friend's game shows in its window's title (4 to 8 letters and digits). The game goes online by itself, "
                        @"finds the game with that code and joins it.";
    alert.informativeText = wrong.empty() ? explain : [NSString stringWithFormat:@"%@\n\n%@", text_of(wrong), explain];
    NSTextField* field = [[NSTextField alloc] initWithFrame:NSMakeRect(0, 0, 200, 24)];
    field.placeholderString = @"Code";
    alert.accessoryView = field;
    [alert addButtonWithTitle:@"Join"];
    [alert addButtonWithTitle:@"Cancel"];
    [alert.window setInitialFirstResponder:field];
    g_sheet = alert;
    g_sheet_field = field;
    [alert beginSheetModalForWindow:window completionHandler:^(NSModalResponse response) {
        g_sheet = nil;
        g_sheet_field = nil;
        if (response != NSAlertFirstButtonReturn) return;
        std::string code = [[[field stringValue] uppercaseString] UTF8String] ?: "";
        bool fits = code.size() >= 4 && code.size() <= 8;
        for (char ch : code) if (!isalnum((unsigned char)ch)) fits = false;
        if (fits) rtanet::request("online start join:" + code);
        else dispatch_async(dispatch_get_main_queue(), ^{ ask_code("A code has 4 to 8 letters and digits."); });
    }];
}

}  // namespace

@interface RtaOnlineMenu : NSObject <NSMenuDelegate>
- (void)goOnline:(id)sender;
- (void)host:(id)sender;
- (void)join:(id)sender;
- (void)stop:(id)sender;
@end
@implementation RtaOnlineMenu
- (void)goOnline:(id)sender { rtanet::request("online start lobby"); }
- (void)host:(id)sender { rtanet::request("online start host"); }
- (void)join:(id)sender { ask_code(""); }
- (void)stop:(id)sender { rtanet::request("online stop"); }
- (void)menuNeedsUpdate:(NSMenu*)menu {
    // the first line says where "online" is, as the program knows it now
    if ([menu numberOfItems] > 0) [menu itemAtIndex:0].title = text_of("Lobby server: " + rtanet::info().server_text);
}
@end

namespace {

RtaOnlineMenu* g_menu_target = nil;

void install_menu() {
    if (NSApp == nil || g_menu != nil) return;
    g_menu_target = [[RtaOnlineMenu alloc] init];
    g_menu = [[NSMenu alloc] initWithTitle:@"Online"];
    g_menu.autoenablesItems = NO;
    g_menu.delegate = g_menu_target;
    NSMenuItem* where = [[NSMenuItem alloc] initWithTitle:@"Lobby server:" action:nil keyEquivalent:@""];
    where.enabled = NO;
    [g_menu addItem:where];
    [g_menu addItem:[NSMenuItem separatorItem]];
    struct { NSString* title; SEL action; } items[] = {
        {@"Go Online (the list of games)", @selector(goOnline:)},
        {@"Host a Game (a code for your friends is made up)", @selector(host:)},
        {@"Join a Game with a Code\u2026", @selector(join:)},
        {nil, nil},
        {@"Stop Going Online", @selector(stop:)}};
    for (auto& one : items) {
        if (!one.title) { [g_menu addItem:[NSMenuItem separatorItem]]; continue; }
        NSMenuItem* item = [[NSMenuItem alloc] initWithTitle:one.title action:one.action keyEquivalent:@""];
        item.target = g_menu_target;
        [g_menu addItem:item];
    }
    NSMenu* bar = [NSApp mainMenu];
    if (!bar) { bar = [[NSMenu alloc] initWithTitle:@""]; [NSApp setMainMenu:bar]; }
    NSMenuItem* head = [[NSMenuItem alloc] initWithTitle:@"Online" action:nil keyEquivalent:@""];
    head.submenu = g_menu;
    // before Help, when the window program has put one there
    NSInteger help = [bar indexOfItemWithTitle:@"Help"];
    if (help >= 0) [bar insertItem:head atIndex:help]; else [bar addItem:head];
}

// tests: "menu info" lists the menu, "menu click N" does what a click on line N does
void menu_test(const std::string& rest) {
    install_menu();
    if (g_menu == nil) { rtanet::say("menu: there is none"); return; }
    [g_menu_target menuNeedsUpdate:g_menu];
    std::string verb = rest.substr(0, rest.find(' '));
    if (verb == "click") {
        NSInteger index = atoi(rest.c_str() + (rest.find(' ') == std::string::npos ? rest.size() : rest.find(' ') + 1));
        if (index < 0 || index >= [g_menu numberOfItems] || ![g_menu itemAtIndex:index].action) { rtanet::say("menu: no such line to click"); return; }
        NSMenuItem* item = [g_menu itemAtIndex:index];
        rtanet::say("menu: \"%s\" chosen", [[item title] UTF8String] ?: "");
        [NSApp sendAction:item.action to:item.target from:item];
        return;
    }
    std::string lines;
    for (NSInteger k = 0; k < [g_menu numberOfItems]; k++) {
        NSMenuItem* item = [g_menu itemAtIndex:k];
        char one[200];
        snprintf(one, sizeof one, "%s%ld=\"%s\"", lines.empty() ? "" : " ", (long)k, item.isSeparatorItem ? "-" : ([[item title] UTF8String] ?: ""));
        lines += one;
    }
    NSMenu* bar = [NSApp mainMenu];
    rtanet::say("menu: in the menu bar=%d; %s", bar != nil && [bar indexOfItemWithSubmenu:g_menu] >= 0, lines.c_str());
}

struct Install {
    Install() {
        rtanet::window_test = sheet_test;
        rtanet::ask_name = ask;
        rtanet::show_note = note;
        rtanet::show_code = code;
        rtanet::show_warning = warning;
        // once the application's own loop runs (a program without one never gets there)
        dispatch_async(dispatch_get_main_queue(), ^{ install_menu(); });
    }
} g_install;

}  // namespace
